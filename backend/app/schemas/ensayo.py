from uuid import UUID
from pydantic import Field,StrictInt,StrictBool,model_validator
from app.schemas.common import Contrato,Recursos
from app.schemas.biblioteca_common import RevisionEsperada
from app.schemas.tamanos import Tamano, validar_tamano


class RevisionBiblioteca(RevisionEsperada):
    codigo: str=Field(pattern=r'^[a-z][a-z0-9-]{2,63}$')
    version: str=Field(pattern=r'^[1-9][0-9]*\.[0-9]+\.[0-9]+$')
    base_definicion_id: UUID|None=None


class EnsayoCreate(RevisionEsperada):
    incorporacion_id: UUID
    perfil_ensayo_id: str=Field(min_length=1,max_length=100)
    plazo_horas: StrictInt|None=Field(default=None,ge=1,le=168)


class ConfirmarFuncionamiento(Contrato):
    funciona: StrictBool


class ConfirmarEntradas(RevisionEsperada):
    entradas_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')


class ComprobarEnsayo(RevisionEsperada):
    evidencia_id: UUID
    evidencia_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')


class DescartarEnsayo(RevisionEsperada):
    motivo: str=Field(min_length=1,max_length=500)


class PerfilOferta(Contrato):
    tamano: Tamano|None=None
    template_id: StrictInt|None=None
    revision_esperada: StrictInt|None=None
    nombre: str=Field(min_length=1,max_length=100)
    descripcion: str=Field(max_length=4000)
    default_vcpus: StrictInt=Field(ge=1)
    default_ram_mb: StrictInt=Field(ge=128)
    default_disk_gb: StrictInt=Field(ge=1)

    @model_validator(mode='after')
    def tamano_coherente(self):
        validar_tamano(self.tamano, {key: getattr(self, 'default_' + key) for key in ['vcpus', 'ram_mb', 'disk_gb']})
        return self


class PublicarOferta(RevisionEsperada):
    ensayo_id: UUID
    perfil: PerfilOferta
