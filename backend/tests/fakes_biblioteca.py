"""Fuente pública determinista: ninguna operación ejecuta su contenido."""
from copy import deepcopy

REVISION = 'a' * 40
DRAWIO = {'identidad_externa': 'ct/drawio.sh', 'nombre': 'Draw.io', 'descripcion': None,
    'categorias': ['diagramas'], 'aliases': ['drawio', 'draw.io', 'diagramas'],
    'procedencia_datos': {'categorias': 'NAP', 'aliases': 'NAP'},
    'comando_origen': f'bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/{REVISION}/ct/drawio.sh)"',
    'url_origen': f'https://github.com/community-scripts/ProxmoxVE/blob/{REVISION}/ct/drawio.sh',
    'revision_fuente': REVISION, 'comando_sha256': 'b' * 64, 'version_externa': None,
    'requisitos': None, 'compatibilidad': 'adaptador_disponible', 'faltantes': ['version', 'requisitos', 'descripcion']}


class FakeFuente:
    def __init__(self, items=None):
        self.items = deepcopy(items if items is not None else [DRAWIO])
        self.failure = None
        self.calls = 0

    async def index(self):
        self.calls += 1
        if self.failure:
            raise self.failure
        return deepcopy(self.items), {'proveedor': 'community-scripts', 'revision': REVISION,
            'consultada_at': '2026-10-25T12:00:00+00:00', 'cache': False, 'estado': 'disponible'}
