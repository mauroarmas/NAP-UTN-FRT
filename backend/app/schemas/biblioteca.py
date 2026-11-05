from pydantic import Field, field_validator, model_validator
from app.schemas.common import Contrato
from app.schemas.biblioteca_common import RevisionEsperada, Paginacion


class Busqueda(Paginacion):
    q: str | None = Field(default=None, max_length=100)
    categoria: str | None = Field(default=None, max_length=100)

    @field_validator('q','categoria')
    @classmethod
    def trim(cls, value):
        return value.strip() if value else None

    @model_validator(mode='after')
    def filtro(self):
        if not self.q and not self.categoria:
            raise ValueError('Indicá nombre o categoría')
        return self


class IncorporacionCreate(Contrato):
    identidad_externa: str = Field(pattern=r'^ct/[a-z0-9][a-z0-9_-]{0,120}\.sh$')
    revision_fuente: str = Field(pattern=r'^[a-f0-9]{40}$')


class IncorporacionEdit(RevisionEsperada):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = Field(default=None, max_length=4000)
    categorias: list[str] | None = Field(default=None, max_length=20)
    aliases: list[str] | None = Field(default=None, max_length=20)

    @field_validator('categorias','aliases')
    @classmethod
    def etiquetas(cls, value):
        if value is not None and any(not t.strip() or len(t)>100 for t in value):
            raise ValueError('Etiqueta inválida')
        return value
