"""Registro histórico para pruebas de auditoría y recuperación de Draw.io."""

REVISION = 'a' * 40
DRAWIO = {'identidad_externa': 'ct/drawio.sh', 'nombre': 'Draw.io', 'descripcion': None,
    'categorias': ['diagramas'], 'aliases': ['drawio', 'draw.io', 'diagramas'],
    'procedencia_datos': {'categorias': 'NAP', 'aliases': 'NAP'},
    'comando_origen': f'bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/{REVISION}/ct/drawio.sh)"',
    'url_origen': f'https://github.com/community-scripts/ProxmoxVE/blob/{REVISION}/ct/drawio.sh',
    'revision_fuente': REVISION, 'comando_sha256': 'b' * 64, 'version_externa': None,
    'requisitos': None, 'compatibilidad': 'adaptador_disponible', 'faltantes': ['version', 'requisitos', 'descripcion']}
