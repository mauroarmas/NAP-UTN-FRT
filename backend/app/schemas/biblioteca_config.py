"""Perfiles institucionales: fuentes fijas y recursos elegibles, nunca shell libre."""
from pathlib import PurePosixPath
from pydantic import Field, StrictInt, field_validator
from app.schemas.common import Contrato


class FuenteBiblioteca(Contrato):
    enabled: bool = True
    cache_seconds: StrictInt = Field(default=900, ge=1, le=3600)
    deadline_seconds: StrictInt = Field(default=10, ge=1, le=10)
    max_entries: StrictInt = Field(default=10000, ge=1, le=10000)
    max_bytes: StrictInt = Field(default=8388608, ge=1024, le=8388608)
    token: str = Field(default='', repr=False)


class BuilderHost(Contrato):
    host: str = Field(pattern=r'^[A-Za-z0-9.-]+$')
    port: StrictInt = Field(default=22, ge=1, le=65535)
    user: str = Field(pattern=r'^[a-z_][a-z0-9_-]*$')
    private_key_path: str = Field(repr=False)
    known_hosts_path: str
    scope_id: str = Field(pattern=r'^[a-z][a-z0-9-]{2,63}$')
    revision: StrictInt = Field(default=1, ge=1)
    limit_bytes: StrictInt = Field(ge=1)
    job_bytes: StrictInt = Field(ge=1)

    @field_validator('private_key_path', 'known_hosts_path')
    @classmethod
    def absolute(cls, value):
        if not value.startswith('/') or '..' in PurePosixPath(value).parts:
            raise ValueError('Se requiere ruta institucional absoluta')
        return value


class PerfilEnsayo(Contrato):
    builder_id: str
    nodo: str = Field(pattern=r'^[A-Za-z0-9._-]+$')
    storage: str = Field(pattern=r'^[A-Za-z0-9._-]+$')
    pool: str = Field(pattern=r'^[A-Za-z0-9._-]+$')
    network_profile_id: str
    vcpus: StrictInt = Field(ge=1)
    ram_mb: StrictInt = Field(ge=128)
    disk_gb: StrictInt = Field(ge=1)
    plazo_horas: StrictInt | None = Field(default=None, ge=1, le=168)
