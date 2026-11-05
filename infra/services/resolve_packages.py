"""Inventario exacto del contenedor descartable de resolución, no una imagen validada."""
import json
from pathlib import Path
import re
import subprocess
import sys


def inventory():
    output = subprocess.check_output(['/usr/bin/dpkg-query', '-W',
        '-f=${Package}\t${Version}\t${Architecture}\t${Status}\n'], text=True)
    packages = []
    for line in output.splitlines():
        name, version, architecture, status = line.split('\t')
        if status != 'install ok installed':
            continue
        if (not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,99}', name)
            or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,119}', version)
            or architecture not in {'amd64', 'all'}):
            raise ValueError('Paquete no compatible con el contrato del builder')
        packages.append({'name': name, 'version': version, 'architecture': architecture})
    return sorted(packages, key=lambda item: item['name'])


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'linux', 'postgresql', 'bookstack', 'drawio'}:
        raise SystemExit('Producto cerrado requerido')
    product = sys.argv[1]
    packages, components = inventory(), {}
    if product == 'drawio':
        java = subprocess.check_output(['/usr/bin/java', '-version'], stderr=subprocess.STDOUT, text=True)
        match = re.search(r'"(21(?:\.[0-9A-Za-z.+_-]+)*)"', java)
        if not match: raise ValueError('JRE 21 no confirmado')
        components['java'] = {'version': match[1]}
    if product == 'postgresql':
        version = subprocess.check_output(['/usr/lib/postgresql/16/bin/postgres', '--version'], text=True)
        match = re.search(r'\b(16\.[0-9]+)\b', version)
        if not match:
            raise ValueError('PostgreSQL 16 no confirmado')
        components['postgresql'] = {'version': match[1]}
    if product == 'bookstack':
        php = subprocess.check_output(['/usr/bin/php8.3', '-r', 'echo PHP_VERSION;'], text=True)
        maria = subprocess.check_output(['/usr/bin/mariadb', '--version'], text=True)
        match = re.search(r'(?:Distrib |from )(10\.11\.[0-9]+)', maria)
        if not re.fullmatch(r'8\.3\.[0-9]+', php) or not match:
            raise ValueError('Runtime BookStack no compatible')
        components = {'php': {'version': php}, 'mariadb': {'version': match[1]}}
    result = {'estado': 'resolucion_sin_saneamiento_ni_validacion', 'product': product,
        'runtime': {'packages': packages, 'components': components},
        'package_lock': {item['name']: item['version'] for item in packages}}
    target = Path('/opt/nap-resolution') / (product + '.json')
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'product': product, 'packages': len(packages), 'components': components}))


if __name__ == '__main__':
    main()
