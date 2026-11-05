from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from app.schemas.common import Contrato
from app.utils.clock import clock


class PruebaRestauracion(Contrato):
    restauracion_id: UUID
    referencia_corte: str = Field(min_length=1, max_length=200)
    referencia_ensayo: str = Field(min_length=1, max_length=200)
    entorno: Literal['real', 'simulado']
    estado_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    conjunto_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    inicio_at: datetime
    fin_at: datetime
    portal_keyring: StrictBool
    postgresql_dato: StrictBool
    bookstack_libro_imagen_adjunto_cuentas_permisos: StrictBool
    inventario_operaciones_capacidad_acceso_reconciliados: StrictBool

    @field_validator('portal_keyring', 'postgresql_dato',
                     'bookstack_libro_imagen_adjunto_cuentas_permisos',
                     'inventario_operaciones_capacidad_acceso_reconciliados')
    @classmethod
    def confirmed(cls, value):
        if value is not True: raise ValueError('Completar y comprobar todos los componentes del ensayo')
        return value

    @field_validator('referencia_corte', 'referencia_ensayo')
    @classmethod
    def reference(cls, value):
        from app.services.restauracion_service import referencia_valida
        return referencia_valida(value)

    @model_validator(mode='after')
    def separate_test(self):
        if self.referencia_corte == self.referencia_ensayo:
            raise ValueError('El ensayo separado debe tener su propia referencia')
        if any(value.tzinfo is None for value in [self.inicio_at, self.fin_at]):
            raise ValueError('Indicar instantes con zona horaria')
        if not self.inicio_at < self.fin_at <= clock.now():
            raise ValueError('El ensayo debe haber terminado y conservar sus tiempos observados')
        return self
