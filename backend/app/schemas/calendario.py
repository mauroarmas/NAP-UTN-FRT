from datetime import date
import re
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator
from app.schemas.common import Contrato

ANIO_LECTIVO_MINIMO = 2026
FECHA_MINIMA = date(ANIO_LECTIVO_MINIMO, 1, 1)


class PeriodoEscritura(Contrato):
    tipo: Literal['primer_cuatrimestre', 'segundo_cuatrimestre', 'anual']
    desde: date = Field(ge=FECHA_MINIMA)
    hasta: date = Field(ge=FECHA_MINIMA)

    @field_validator('desde', 'hasta', mode='before')
    @classmethod
    def full_date(cls, value):
        if not (type(value) is date or isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)):
            raise ValueError('Indicá fecha completa YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def ordered(self):
        if self.desde > self.hasta:
            raise ValueError('La fecha final debe ser posterior o igual a la inicial')
        return self


class CalendarioEscritura(Contrato):
    revision_esperada: StrictInt = Field(ge=0)
    periodos: list[PeriodoEscritura] = Field(max_length=3)

    @model_validator(mode='after')
    def compatible(self):
        periods = {period.tipo: period for period in self.periodos}
        if len(periods) != len(self.periodos):
            raise ValueError('Cada modalidad aparece una sola vez')
        first, second = periods.get('primer_cuatrimestre'), periods.get('segundo_cuatrimestre')
        if first and second and max(first.desde, second.desde) <= min(first.hasta, second.hasta):
            raise ValueError('Los cuatrimestres no pueden solaparse')
        return self
