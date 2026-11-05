from pydantic import Field, StrictBool, StrictInt, model_validator
from app.schemas.common import Contrato


class PerfilNodo(Contrato):
    margen_vcpus: StrictInt = Field(ge=0)
    margen_ram_mb: StrictInt = Field(ge=0)
    storages: list[str] = Field(min_length=1)


class PerfilStorage(Contrato):
    shared: StrictBool
    pool_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9._-]+$')
    margen_logico_bytes: StrictInt = Field(ge=0)
    margen_fisico_bytes: StrictInt = Field(ge=0)
    capacidad_logica_bytes: StrictInt | None = Field(default=None, ge=1)


class PerfilInfraestructura(Contrato):
    version: StrictInt = Field(ge=1, le=1)
    cluster_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9._-]+$')
    nodos: dict[str, PerfilNodo] = Field(min_length=1)
    almacenamientos: dict[str, PerfilStorage] = Field(min_length=1)

    @model_validator(mode='after')
    def references(self):
        import re
        if any(not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', key) for key in [*self.nodos, *self.almacenamientos]):
            raise ValueError('Nombre de destino inválido')
        if any(set(node.storages) - set(self.almacenamientos) or len(node.storages) != len(set(node.storages)) for node in self.nodos.values()):
            raise ValueError('Almacenamiento no definido o repetido')
        return self
