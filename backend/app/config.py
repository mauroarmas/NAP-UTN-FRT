from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from app.schemas.biblioteca_config import FuenteBiblioteca, BuilderHost, PerfilEnsayo
from app.schemas.application_profiles import ProfileRegistry, ProfileError
from functools import lru_cache
import json
import os
from pathlib import Path
import stat


class Settings(BaseSettings):
    # Proxmox VE
    proxmox_host: str = "172.16.36.100"
    proxmox_port: int = 8006
    proxmox_user: str = "root@pam"
    proxmox_token_name: str = "ps-dev"
    proxmox_token_value: str = Field(default='', repr=False)
    proxmox_verify_ssl: bool = False
    proxmox_ca_file: str = ''

    # PostgreSQL
    database_url: str = Field(default='postgresql+asyncpg://ps_user:ps_password@localhost:5432/ps_db', repr=False)

    # Auth
    secret_key: str = Field(default='dev-secret-key-change-in-production-please', repr=False)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    csrf_secret: str = Field(default='', repr=False)
    secret_keyring: dict[str, str] = Field(default_factory=dict, repr=False)
    secret_active_key: str = ''
    institutional_timezone: str = 'America/Argentina/Tucuman'
    auth_allowed_origins: list[str] = Field(default_factory=list)
    trusted_proxy_networks: list[str] = Field(default_factory=list)
    infrastructure_profile: dict = Field(default_factory=dict)
    service_artifacts: dict = Field(default_factory=dict)
    artifact_registry_directory: str = ""
    network_profiles: dict = Field(default_factory=dict)
    iaas_network_profile_id: str = ''
    iaas_template_storage: str = 'local'
    runner_nodes: dict = Field(default_factory=dict, repr=False)
    console_access_profile: dict = Field(default_factory=dict)
    application_gateway_domain: str = ''
    application_gateway_port: int = Field(default=443, ge=1, le=65535)
    application_gateway_ca_file: str = ''
    application_profiles: dict = Field(default_factory=dict)
    application_network_profiles: dict = Field(default_factory=dict)
    application_registry_profiles: dict = Field(default_factory=lambda:{'docker-hub':{
        'registry':{'host':'registry-1.docker.io','allow_public':True},
        'reference_hosts':['docker.io'],'repository_prefixes':[''],
        'token_endpoint':{'host':'auth.docker.io','allow_public':True},'token_service':'registry.docker.io',
        'blob_endpoints':[{'host':'production.cloudfront.docker.com','allow_public':True}]}},repr=False)

    biblioteca_fuente: FuenteBiblioteca = Field(default_factory=FuenteBiblioteca)
    builder_hosts: dict[str, BuilderHost] = Field(default_factory=dict, repr=False)
    perfiles_ensayo: dict[str, PerfilEnsayo] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validar_biblioteca(self):
        try:
            ProfileRegistry(self.application_profiles)
        except ProfileError:
            raise ValueError('Registro institucional de aplicaciones inválido') from None
        try:
            from app.schemas.oci_registry import RegistryProfile
            import re
            if len(self.application_registry_profiles)>50:raise ValueError()
            references=set()
            for name,value in self.application_registry_profiles.items():
                if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',name):raise ValueError()
                profile=RegistryProfile.model_validate(value)
                for host in profile.reference_hosts:
                    if host in references:raise ValueError()
                    references.add(host)
        except (ValueError,TypeError,AttributeError):
            raise ValueError('Registro institucional de imágenes inválido') from None
        if self.artifact_registry_directory and (not Path(self.artifact_registry_directory).is_absolute() or ".." in Path(self.artifact_registry_directory).parts):
            raise ValueError("El registro de artefactos requiere directorio institucional absoluto")
        scopes = {}
        for host in self.builder_hosts.values():
            if host.job_bytes > host.limit_bytes:
                raise ValueError("Presupuesto de trabajo superior al scope")
            signature = (host.revision, host.limit_bytes)
            if host.scope_id in scopes and scopes[host.scope_id] != signature:
                raise ValueError("Los hosts de un scope deben compartir presupuesto y revisión")
            scopes[host.scope_id] = signature
        for profile in self.perfiles_ensayo.values():
            if profile.builder_id not in self.builder_hosts or profile.network_profile_id not in self.network_profiles:
                raise ValueError("Perfil de ensayo sin builder o red institucional")
        return self

    # App
    app_name: str = "Portal de Gestión - Nube Privada UTN FRT"
    app_env: str = "development"
    app_debug: bool = True
    app_frontend_url: str = "http://localhost:5173"
    restauracion_referencia: str = ''

    # SMTP & Notificaciones
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = Field(default='', repr=False)
    smtp_from: str = "noreply@frt.utn.edu.ar"
    smtp_tls: bool = True
    smtp_ssl: bool = False

    model_config = {
        "env_file": str(Path(__file__).resolve().parents[2] / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    path=os.environ.get('NAP_SETTINGS_FILE')
    if path:
        return settings_from_file(path)
    return Settings()


def settings_from_file(path) -> Settings:
    """Archivo privado montado, sin valores en argv/env ni errores de validación."""
    try:
        def unique(items):
            result={}
            for key,value in items:
                if key in result: raise ValueError()
                result[key]=value
            return result
        def invalid_constant(_): raise ValueError()
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'r',encoding='utf-8') as handle:
            info=os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or info.st_mode&0o077 or info.st_size>1024*1024): raise ValueError()
            value=json.load(handle,object_pairs_hook=unique,parse_constant=invalid_constant)
        if not isinstance(value,dict) or not value.keys()<=Settings.model_fields.keys(): raise ValueError()
        return Settings(_env_file=None,**value)
    except Exception:
        raise RuntimeError('Configuración privada inválida; revisar archivo, permisos, campos y formato') from None
