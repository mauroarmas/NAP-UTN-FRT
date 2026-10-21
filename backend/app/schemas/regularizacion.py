from datetime import date
from typing import Literal

from pydantic import Field,field_validator,model_validator

from app.schemas.common import Contrato,Recursos


class EvaluarRegularizacion(Contrato):
    canonico_id: int|None=Field(default=None,gt=0)


class ReferenciaRegularizacion(Contrato):
    fuente_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    referencia: str=Field(min_length=1,max_length=200)
    motivo: str=Field(min_length=1,max_length=500)

    @field_validator('referencia','motivo')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Completá referencia y motivo')
        return value.strip()


class ConfirmarRegularizacion(ReferenciaRegularizacion):
    nombre: str=Field(min_length=1,max_length=150)
    modelo_servicio: Literal['iaas','paas','saas']
    asignacion: Recursos
    desde: date
    hasta: date

    @model_validator(mode='after')
    def ordered(self):
        if self.desde>self.hasta: raise ValueError('La fecha inicial debe ser anterior o igual a la final')
        if not self.nombre.strip(): raise ValueError('Indicá nombre del servicio')
        self.nombre=self.nombre.strip()
        return self


class ArchivarDuplicado(ReferenciaRegularizacion):
    canonico_id: int=Field(gt=0)
