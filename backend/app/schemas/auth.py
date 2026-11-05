from uuid import UUID
from pydantic import Field, StrictStr, field_validator, model_validator
from app.schemas.common import Contrato
from app.utils.security import validar_password


class PasswordRequest(Contrato):
    password: StrictStr

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        validar_password(value)
        return value


class Setup2FARequest(Contrato):
    password: StrictStr | None = None

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        if value is not None:
            validar_password(value)
        return value


class PruebaTOTP(PasswordRequest):
    codigo_totp: StrictStr = Field(max_length=20)


class Verify2FARequest(Contrato):
    desafio_id: UUID
    codigo_totp: StrictStr = Field(max_length=20)


class CancelSetupRequest(Contrato):
    desafio_id: UUID


class RecoveryRequest(PasswordRequest):
    codigo_recuperacion: StrictStr = Field(min_length=1, max_length=200)


class AssistedRecoveryRequest(PasswordRequest):
    autorizacion_recuperacion: StrictStr = Field(min_length=1, max_length=200)


class Disable2FARequest(PasswordRequest):
    codigo_totp: StrictStr | None = Field(default=None, max_length=20)
    codigo_recuperacion: StrictStr | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def exactly_one(self):
        if bool(self.codigo_totp) == bool(self.codigo_recuperacion):
            raise ValueError('Presentá exactamente una prueba de segundo factor')
        return self


class CambiarPasswordInicialRequest(Contrato):
    nueva_password: StrictStr

    @field_validator('nueva_password')
    @classmethod
    def nueva_password_bytes(cls, value):
        validar_password(value, nueva=True)
        return value
