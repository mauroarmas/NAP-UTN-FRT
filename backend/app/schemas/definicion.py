"""Manifiesto cerrado; un borrador incompleto nunca habilita publicación."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydantic import Field, model_validator

from app.schemas.common import Contrato
from app.schemas.evidencia import canonical
from app.utils.errors import error


class DefinicionCreate(Contrato):
    codigo: str = Field(pattern=r'^[a-z][a-z0-9-]{2,63}$')
    version: str = Field(pattern=r'^[1-9][0-9]*\.[0-9]+\.[0-9]+$')
    producto: Literal['linux', 'postgresql', 'bookstack', 'drawio']
    modelo_servicio: Literal['iaas', 'paas', 'saas']

    @model_validator(mode='after')
    def compatible(self):
        if self.modelo_servicio != {'linux': 'iaas', 'postgresql': 'paas', 'bookstack': 'saas', 'drawio': 'saas'}[self.producto]:
            raise ValueError('Producto y modelo incompatibles')
        return self


class AccionDefinicion(Contrato):
    pass


class RetirarDefinicion(Contrato):
    motivo: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def motivo_presente(self):
        if not self.motivo.strip():
            raise ValueError('Indicá un motivo')
        self.motivo = self.motivo.strip()
        return self


@lru_cache
def validator(parcial=False, schema_version='1.0'):
    if schema_version not in {'1.0', '1.1'}:
        raise ValueError('Versión de esquema desconocida')
    name = 'service-definition-1.1.schema.json' if schema_version == '1.1' else 'service-definition.schema.json'
    schema = json.loads(Path(__file__).with_name(name).read_text())
    if parcial:
        def relax(value):
            if isinstance(value, list):
                return [relax(item) for item in value]
            if not isinstance(value, dict):
                return value
            return {('anyOf' if key == 'oneOf' else key): relax(item) for key, item in value.items() if key != 'required'}
        schema = relax(schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validar_manifest(value, *, parcial=False):
    try:
        def strict_numbers(item):
            if isinstance(item, float):
                raise ValueError('Número fraccionario')
            if isinstance(item, dict):
                for element in item.values():
                    strict_numbers(element)
            elif isinstance(item, list):
                for element in item:
                    strict_numbers(element)
        strict_numbers(value)
        # Los hashes y esquemas nunca evalúan referencias o código del documento.
        canonical(value)
        validator(parcial, value.get('schema_version', '1.0')).validate(value)
        if not parcial:
            UUID(value['validation']['evidence_id'])
            packages = value['runtime']['packages']
            if len({(p['name'], p['architecture']) for p in packages}) != len(packages):
                raise ValueError('Paquete duplicado')
            components = value['runtime']['components']
            for component, package in [('java', 'openjdk-21-jre-headless'), ('postgresql', 'postgresql-16'), ('php', 'php8.3-fpm'), ('mariadb', 'mariadb-server')]:
                if component in components:
                    expected = components[component]['version']
                    versions = [re.sub(r'^\d+:', '', p['version']) for p in packages if p['name'] == package]
                    if not any(v == expected or v.startswith(expected + '-') or v.startswith(expected + '+') for v in versions):
                        raise ValueError('Inventario incompatible con componente')
        return value
    except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
        raise error(422, 'manifiesto_invalido', 'El manifiesto no cumple el esquema y la compatibilidad del producto') from None


def parse_manifest(raw):
    if len(raw) > 262144:
        raise error(413, 'contenido_demasiado_grande', 'El manifiesto supera 256 KiB')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid_number(value):
        raise ValueError()
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=invalid_number, parse_constant=invalid_number)
        if not isinstance(value, dict) or set(value) != {'manifest'} or not isinstance(value['manifest'], dict):
            raise ValueError()
        validar_manifest(value['manifest'], parcial=True)
        return value['manifest']
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise error(422, 'manifiesto_invalido', 'Enviá un objeto manifest cerrado, sin duplicados ni números fraccionarios') from None


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()
