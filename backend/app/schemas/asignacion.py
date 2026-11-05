from datetime import date
from typing import Literal
from uuid import UUID
import re

from pydantic import Field, StrictInt, StrictBool, SecretStr, field_validator, model_validator
from app.schemas.common import Contrato, Recursos, Destino
from app.schemas.calendario import ANIO_LECTIVO_MINIMO, FECHA_MINIMA
from app.schemas.tamanos import Tamano, validar_tamano


class VigenciaSolicitud(Contrato):
    tipo: Literal['primer_cuatrimestre', 'segundo_cuatrimestre', 'anual', 'personalizado']
    anio_lectivo: StrictInt | None = Field(default=None, ge=ANIO_LECTIVO_MINIMO, le=9998)
    desde: date | None = Field(default=None, ge=FECHA_MINIMA)
    hasta: date | None = Field(default=None, ge=FECHA_MINIMA)

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
    configuracion_despliegue_id: UUID | None = None
    tamano: Tamano | None = None

    @model_validator(mode='after')
    def tamano_coherente(self):
        if self.definicion_version_id and self.configuracion_despliegue_id:
            raise ValueError('Elegí un solo origen para la asignación')
        validar_tamano(self.tamano, self.model_dump())
        return self


class SeleccionEvaluacion(Contrato):
    asignacion: AsignacionEfectiva
    destino: Destino | None = None
    vigencia: VigenciaSolicitud


class AprobacionEfectiva(SeleccionEvaluacion):
    capacidad_token: str = Field(min_length=1, max_length=4096)
    justificacion_capacidad: str | None = Field(default=None, min_length=1, max_length=2000)
    desplegar_inmediatamente: StrictBool = False
    solicitar_despliegue: Literal['inmediato', 'programado', 'al_inicio'] | StrictBool | None = None
    valores_privados: dict[str, SecretStr] | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode='after')
    def validar_intencion_despliegue(self):
        if self.solicitar_despliegue is not None:
            if self.solicitar_despliegue is False and self.desplegar_inmediatamente:
                raise ValueError('Decisiones de despliegue contradictorias: solicitar_despliegue=False con desplegar_inmediatamente=True')
            if self.solicitar_despliegue in ('programado', 'al_inicio') and self.desplegar_inmediatamente:
                raise ValueError('Decisiones de despliegue contradictorias: despliegue programado con desplegar_inmediatamente=True')
        return self

    @field_validator('valores_privados', mode='before')
    @classmethod
    def entrada_privada(cls, value):
        if value is None: return None
        from app.utils.errors import error
        def invalid(): return error(422,'secretos_despliegue_invalidos','Completá los datos privados requeridos para este pedido')
        if type(value) is not dict or len(value)>20: raise invalid()
        result={}
        for name, secret in value.items():
            secret=secret.get_secret_value() if isinstance(secret,SecretStr) else secret
            try:
                if (type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name)
                    or type(secret) is not str or not secret or '\x00' in secret or len(secret.encode())>4096):raise ValueError()
            except (ValueError,UnicodeError):raise invalid() from None
            result[name]=SecretStr(secret)
        return result
