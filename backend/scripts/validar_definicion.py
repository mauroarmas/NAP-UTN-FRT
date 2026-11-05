"""Valida un archivo de manifiesto sin red, ejecución ni publicación."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from app.schemas.definicion import parse_manifest, validar_manifest, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        with args.manifest.open('rb') as source:
            raw = source.read(262145)
        # El archivo del builder contiene solo el manifiesto; la API usa sobre.
        if len(raw) > 262144:
            raise ValueError()
        value = parse_manifest(b'{"manifest":' + raw + b'}')
        validar_manifest(value)
    except (OSError, ValueError, HTTPException):
        parser.exit(1, 'Manifiesto inválido, incompleto o no legible. No se publicó ninguna versión.\n')
    print('Contrato válido. SHA-256: ' + digest(value))


if __name__ == '__main__':
    main()
