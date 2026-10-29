"""Contrato interno de aplicaciones; no acepta instrucciones de ejecución libres.

Los errores públicos son constantes: Pydantic no debe devolver entradas privadas.
El esquema exportado se comprueba también en el nodo antes de admitir un trabajo.
"""

from hashlib import sha256
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.utils.errors import error


MAX_DOCUMENT_BYTES = 65536
HASH = r'^[a-f0-9]{64}$'
DIGEST = r'^sha256:[a-f0-9]{64}$'
NAME = r'^[A-Za-z_][A-Za-z0-9_]{0,63}$'
PROFILE_ID = r'^[a-z][a-z0-9-]{0,63}$'
RESERVED = frozenset({
    'PATH', 'HOME', 'SHELL', 'ENV', 'BASH_ENV', 'SHELLOPTS', 'BASHOPTS', 'IFS', 'CDPATH',
    'PYTHONPATH', 'PYTHONHOME', 'FUNCTIONS_FILE_PATH', 'COMMUNITY_SCRIPTS_CORE_URL',
    'DIAGNOSTICS', 'TELEMETRY_URL', 'DEV_MODE_TRACE', 'SSH_ROOT', 'INSTALL_LOG',
    'TMPDIR', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT',
    'DOCKER_CONFIG', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
})
FORBIDDEN_TARGETS = ('/proc', '/sys', '/dev', '/run', '/var/run', '/etc/pve', '/etc/nap',
                     '/var/lib/lxc', '/var/lib/docker', '/root', '/boot')


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)


class Perfil(Closed):
    id: str = Field(pattern=PROFILE_ID)
    revision: int = Field(ge=1, le=2**31-1)
    sha256: str = Field(pattern=HASH)


class BaseLinux(Closed):
    os: Literal['ubuntu', 'debian']
    version: str = Field(pattern=r'^[0-9]{1,2}(?:\.[0-9]{1,2})?$')
    arquitectura: Literal['amd64', 'arm64']
    volumen_lxc: str = Field(max_length=200, pattern=r'^[a-zA-Z][a-zA-Z0-9_-]*:vztmpl/[a-zA-Z0-9][a-zA-Z0-9_.-]*\.tar\.(?:zst|gz|xz)$')
    sha256: str = Field(pattern=HASH)


class Minimos(Closed):
    vcpus: int = Field(ge=1, le=2)
    ram_mb: int = Field(ge=1, le=1024)
    disk_gb: int = Field(ge=1, le=8)


class ProbeHTTP(Closed):
    tipo: Literal['http']
    path: str = Field(min_length=1, max_length=512, pattern=r'^/(?:[A-Za-z0-9._~-][A-Za-z0-9/._~-]*)?$')
    estados: list[Annotated[int, Field(ge=200, le=299)]] = Field(min_length=1, max_length=10)
    timeout_segundos: int = Field(ge=1, le=30)

    @model_validator(mode='after')
    def normalizado(self):
        if any(p in {'.', '..'} for p in self.path.split('/')) or len(set(self.estados)) != len(self.estados):
            raise ValueError('Probe inválido')
        return self


class ProbeMariaDB(Closed):
    tipo: Literal['mariadb_select_1']
    timeout_segundos: int = Field(ge=1, le=30)


class AccesoWeb(Closed):
    tipo: Literal['web']
    puerto: int = Field(ge=1, le=65535)
    politica: Literal['web-managed']
    upstream: Literal['http', 'https']
    probe: ProbeHTTP
    websocket: bool


class AccesoTCP(Closed):
    tipo: Literal['tcp']
    puerto: int = Field(ge=1, le=65535)
    politica: Literal['mariadb-tls']
    probe: ProbeMariaDB


class DeclaracionSecreto(Closed):
    nombre: str = Field(pattern=NAME)
    etiqueta: str = Field(min_length=1, max_length=100, pattern=r'^[^\x00-\x1f\x7f]+$')
    modo: Literal['generado', 'por_pedido']


class Imagen(Closed):
    # Registry explícito, sin URL, usuario, tag o digest dentro del repositorio.
    repositorio: str = Field(max_length=255, pattern=r'^(?:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::[1-9][0-9]{0,4})?/(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*$')
    tag_original: str | None = Field(default=None, max_length=128, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$')
    manifest_digest: str = Field(pattern=DIGEST)
    index_digest: str | None = Field(default=None, pattern=DIGEST)
    config_digest: str = Field(pattern=DIGEST)
    os: Literal['linux']
    arquitectura: Literal['amd64', 'arm64']
    registry_profile_id: str = Field(pattern=PROFILE_ID)


class FuenteCommunity(Closed):
    slug: str = Field(pattern=PROFILE_ID)
    identidad_externa: str = Field(pattern=r'^ct/[a-z][a-z0-9-]{0,63}\.sh$')
    instalador: str = Field(pattern=r'^install/[a-z][a-z0-9-]{0,63}-install\.sh$')
    proxmoxve_commit: str = Field(pattern=r'^[a-f0-9]{40}$')
    core_commit: str = Field(pattern=r'^[a-f0-9]{40}$')
    instalador_sha256: str = Field(pattern=HASH)
    core_sha256: str = Field(pattern=HASH)
    harness_sha256: str = Field(pattern=HASH)
    manifiesto_sha256: str = Field(pattern=HASH)
    politica_sha256: str = Field(pattern=HASH)
    dependencias_sha256: str = Field(pattern=HASH)
    respuestas: dict[str, str] = Field(max_length=20)
    postconfiguracion: Literal['mariadb-tls', 'caddy-web']
    depuracion: Literal['salida-cerrada-v1']

    @model_validator(mode='after')
    def origen_coherente(self):
        expected = {'mariadb': ('mariadb-tls', {'phpmyadmin': 'no'}),
                    'caddy': ('caddy-web', {'xcaddy': 'no'})}
        if (self.slug not in expected or self.identidad_externa != f'ct/{self.slug}.sh'
                or self.instalador != f'install/{self.slug}-install.sh'
                or (self.postconfiguracion, self.respuestas) != expected[self.slug]):
            raise ValueError('Paquete no admitido')
        return self


class Comun(Closed):
    schema_version: Literal['nap-deployment/1']
    modelo_servicio: Literal['paas', 'saas']
    perfil: Perfil
    base: BaseLinux
    minimum_resources: Minimos
    access: Annotated[AccesoWeb | AccesoTCP, Field(discriminator='tipo')]
    variables: dict[str, str] = Field(max_length=20)
    secretos: list[DeclaracionSecreto] = Field(max_length=20)
    persistencia: list[str] = Field(max_length=8)

    @model_validator(mode='after')
    def politica_comun(self):
        names = list(self.variables) + [s.nombre for s in self.secretos]
        if (len(names) > 20 or len(names) != len(set(names))
                or any(not re.fullmatch(NAME, n) or n in RESERVED or n.startswith(('LD_', 'NAP_', 'BASH_FUNC_')) for n in names)):
            raise ValueError('Variables no admitidas')
        if any('\x00' in v or len(v.encode('utf-8')) > 4096 for v in self.variables.values()):
            raise ValueError('Valor inválido')
        if len(set(self.persistencia)) != len(self.persistencia):
            raise ValueError('Destino duplicado')
        for path in self.persistencia:
            if (not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', path)
                    or len(path) > 255 or any(p in {'.', '..'} for p in path.split('/'))
                    or any(path == p or path.startswith(p + '/') for p in FORBIDDEN_TARGETS)):
                raise ValueError('Destino inválido')
        return self


class ConfiguracionDocker(Comun):
    origen: Literal['imagen_docker']
    imagen: Imagen

    @model_validator(mode='after')
    def plataforma_coherente(self):
        if ((self.base.os, self.base.version) != ('ubuntu', '24.04')
                or self.imagen.arquitectura != self.base.arquitectura):
            raise ValueError('Plataforma no admitida')
        if self.access.tipo=='tcp' and (
                self.imagen.repositorio!='docker.io/library/mariadb' or self.modelo_servicio!='paas'
                or self.access.puerto!=3306 or self.persistencia!=['/var/lib/mysql']
                or self.variables!={'MARIADB_DATABASE':'catedra','MARIADB_USER':'docente','MARIADB_ROOT_HOST':'localhost'}
                or {s.nombre for s in self.secretos}!={'MARIADB_PASSWORD','MARIADB_ROOT_PASSWORD'}
                or any(s.modo!='generado' for s in self.secretos)):
            raise ValueError('Configuración de base de datos no admitida')
        return self


class ConfiguracionCommunity(Comun):
    origen: Literal['community_scripts']
    community: FuenteCommunity

    @model_validator(mode='after')
    def plataforma_coherente(self):
        if ((self.base.os, self.base.version) != ('debian', '13')
                or self.minimum_resources != Minimos(vcpus=2, ram_mb=1024, disk_gb=8)
                or (self.community.slug == 'mariadb') != (self.access.tipo == 'tcp')):
            raise ValueError('Plataforma no admitida')
        return self


Configuracion = Annotated[ConfiguracionDocker | ConfiguracionCommunity, Field(discriminator='origen')]
adapter = TypeAdapter(Configuracion)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _strict_json(value, depth=0):
    if depth > 16 or type(value) not in (dict, list, str, int, bool, type(None)):
        raise ValueError('JSON inválido')
    if type(value) is dict:
        for k, v in value.items():
            if type(k) is not str: raise ValueError('Clave inválida')
            _strict_json(v, depth+1)
    elif type(value) is list:
        for v in value: _strict_json(v, depth+1)


def invalid_config():
    return error(422, 'configuracion_despliegue_invalida', 'Revisá la configuración y la compatibilidad de la aplicación')


def validar_documento(value):
    try:
        _strict_json(value)
        if len(canonical(value)) > MAX_DOCUMENT_BYTES: raise ValueError('Tamaño inválido')
        return adapter.validate_python(value).model_dump(mode='json', exclude_none=True)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise invalid_config() from None


def digest_configuracion(value):
    return sha256(canonical(validar_documento(value))).hexdigest()


def parse_documento(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Clave duplicada')
            result[key] = value
        return result
    def invalid(_): raise ValueError('Número inválido')
    try:
        if type(raw) is not bytes or len(raw) > MAX_DOCUMENT_BYTES: raise ValueError('Tamaño inválido')
        return validar_documento(json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                                           parse_float=invalid, parse_constant=invalid))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise invalid_config() from None
