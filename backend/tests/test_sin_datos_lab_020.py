"""SC-006 (spec 020): los archivos versionados de la consola no contienen datos del laboratorio."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALCANCE = ('docs/runbook-consola-nativa.md', 'docs/infraestructura-laboratorio/scripts/consola/',
           'specs/020-habilitar-consola-nativa/', 'infra/production/settings.example.json',
           'backend/app/services/consola_destino_service.py', 'backend/app/services/consola_gate_service.py',
           'backend/app/services/terminal_relay_service.py', 'backend/app/services/terminal_sesiones_service.py',
           'backend/app/services/identidad_consola_service.py', 'infra/runner/console_identity.py',
           'backend/app/schemas/console_identity.py', 'docs/runbook-terminal-portal.md')
PROHIBIDO = [
    (re.compile(r'\b(?:192\.168|172\.16|10\.\d{1,3})\.\d{1,3}\.\d{1,3}\b'), 'direccion privada'),
    (re.compile(r'0d69119f'), 'UUID del clúster del laboratorio'),
    (re.compile(r'PVEAPIToken=|token_value"\s*:\s*"[^"]+"|\bpassword\s*[=:]\s*["\']?[A-Za-z0-9]{6,}', re.I), 'secreto'),
]
IDENTIDAD = re.compile(r'\b([A-Za-z0-9._-]+)@(pve|pam)\b')
MARCADORES = {'usuario', 'nombre', 'persona', 'user', 'root', 'identidad', 'operador', 'ejemplo', 'x', 'nap-api'}


def _archivos():
    listado = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', *ALCANCE],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split('\n')
    return [ROOT / name for name in listado if name and (ROOT / name).is_file()]


def test_los_archivos_de_la_consola_no_contienen_datos_del_laboratorio():
    hallazgos = []
    for path in _archivos():
        text = path.read_text(errors='ignore')
        for pattern, label in PROHIBIDO:
            for match in pattern.finditer(text):
                hallazgos.append(f'{path.relative_to(ROOT)}: {label}: {match.group(0)[:30]}')
        for match in IDENTIDAD.finditer(text):
            if match.group(1).lower() not in MARCADORES:
                hallazgos.append(f'{path.relative_to(ROOT)}: identidad: {match.group(0)}')
    assert not hallazgos, '\n'.join(hallazgos)
