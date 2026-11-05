"""JSON institucional estricto y canónico, antes de validar referencias."""

from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from app.utils.errors import error

MAX_BYTES = 65536


@lru_cache
def validator():
    schema = json.loads(Path(__file__).with_name('evidence.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def canonical(document):
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def parse_document(raw):
    if len(raw) > MAX_BYTES:
        raise error(413, 'contenido_demasiado_grande', 'La evidencia supera 64 KiB')

    def reject_number(value):
        raise ValueError('Solo enteros JSON')

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('Clave duplicada')
            result[key] = value
        return result

    try:
        if raw.startswith(b'\xef\xbb\xbf'):
            raise ValueError()
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                              parse_float=reject_number, parse_constant=reject_number)
        validator().validate(document)
        endpoint = document['resultado'].get('endpoint')
        if endpoint and ('@' in endpoint or urlsplit(endpoint).username is not None):
            raise ValueError('Endpoint con credenciales')
        return document
    except (ValueError, TypeError, UnicodeError, ValidationError, RecursionError):
        raise error(422, 'evidencia_invalida', 'El documento de evidencia tiene formato o contenido inválido') from None
