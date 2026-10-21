from datetime import date
from typing import Literal
from uuid import UUID
import re

from pydantic import Field, StrictInt, StrictBool, field_validator, model_validator
from app.schemas.common import Contrato, Recursos, Destino


class VigenciaSolicitud(Contrato):
    tipo: Literal['primer_cuatrimestre', 'segundo_cuatrimestre', 'anual', 'personalizado']
    anio_lectivo: StrictInt | None = Field(default=None, ge=1900, le=9998)
    desde: date | None = None
    hasta: date | None = None

    @field_validator('desde', 'hasta', mode='before')
    @classmethod
    def full_date(cls, value):
        if value is not None and not (type(value) is date or isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)):
            raise ValueError('Indicá fecha completa YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def complete(self):
        if self.tipo == 'personalizado':
            if self.anio_lectivo is not None or not self.desde or not self.hasta or self.desde > self.hasta:
                raise ValueError('La vigencia personalizada exige fechas completas y ordenadas, sin año académico')
        elif self.anio_lectivo is None or self.desde is not None or self.hasta is not None:
            raise ValueError('La vigencia académica exige año lectivo y no admite fechas personalizadas')
        return self


class AsignacionEfectiva(Recursos):
    template_id: StrictInt = Field(ge=1)
    definicion_version_id: UUID | None = None


class SeleccionEvaluacion(Contrato):
    asignacion: AsignacionEfectiva
    destino: Destino | None = None
    vigencia: VigenciaSolicitud


class AprobacionEfectiva(SeleccionEvaluacion):
    capacidad_token: str = Field(min_length=1, max_length=4096)
    justificacion_capacidad: str | None = Field(default=None, min_length=1, max_length=2000)
    desplegar_inmediatamente: StrictBool = False
