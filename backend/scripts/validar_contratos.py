"""Validar schemas y JSON de contratos sin iniciar app ni infraestructura."""

import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


def main():
    root = Path(__file__).resolve().parents[2]
    contracts = root / 'specs/009-remediar-hallazgos-cierre/contracts'
    for path in sorted(contracts.glob('*.schema.json')):
        Draft202012Validator.check_schema(json.loads(path.read_text()))
        packaged = root / 'backend/app/schemas' / path.name
        if packaged.exists() and packaged.read_bytes() != path.read_bytes():
            raise ValueError('Schema de runtime desactualizado: ' + path.name)
        print(f'Schema OK: {path.name}')
    for path in sorted((root/'backend/app/schemas').glob('service-definition-*.schema.json')):
        Draft202012Validator.check_schema(json.loads(path.read_text()))
        print(f'Schema OK: {path.name}')
    count = 0
    for path in sorted(contracts.glob('*.md')):
        for value in re.findall(r'(?:```|~~~)json\s*\n(.*?)\n(?:```|~~~)', path.read_text(), re.S):
            json.loads(value)
            count += 1
    print(f'Ejemplos JSON: {count}')


if __name__ == '__main__':
    main()
