"""Protocolo builder cerrado; paths reales sólo en registro del host."""
from typing import Literal
from uuid import UUID
from pydantic import Field,StrictInt,model_validator
from app.schemas.common import Contrato

PROTOCOL='nap-build-runner/1'


class BuildRequest(Contrato):
    protocol: Literal['nap-build-runner/1']
    operation_id: str=Field(pattern=r'^[a-zA-Z0-9-]{1,100}$')
    ensayo_id: UUID
    generation: StrictInt=Field(ge=1)
    action: Literal['resolve','build','status','stage','cancel','cleanup']
    recipe_id: Literal['drawio-tomcat11-ubuntu-24.04-v1']|None=None
    recipe_revision: str|None=Field(default=None,pattern=r'^[a-f0-9]{40}$')
    input_sha256: str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    input_ref: str|None=Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,100}$')

    definition_id: UUID | None = None
    definition_key: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{2,63}$')
    definition_version: str | None = Field(default=None, pattern=r'^[1-9][0-9]*\.[0-9]+\.[0-9]+$')
    validated_manifest: dict | None = None

    @model_validator(mode='after')
    def inputs(self):
        if self.action in {'resolve','build','stage'} and not all([self.recipe_id,self.recipe_revision,self.input_sha256,self.input_ref]):
            raise ValueError('Faltan entradas fijadas')
        if self.validated_manifest is not None:
            if self.action != 'stage': raise ValueError('Manifiesto sólo al distribuir validación')
            from app.schemas.definicion import validar_manifest
            validar_manifest(self.validated_manifest)
        return self
