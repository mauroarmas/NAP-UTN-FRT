from pydantic_settings import BaseSettings
from pydantic import Field
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
    network_profiles: dict = Field(default_factory=dict)
    runner_nodes: dict = Field(default_factory=dict, repr=False)
    console_access_profile: dict = Field(default_factory=dict)

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
