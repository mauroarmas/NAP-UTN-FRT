"""Doble de Proxmox para el protocolo nap-console-identity/1 (feature 022): estado en memoria, contrato verificado."""
from app.schemas import console_identity
from app.schemas.guest_runner import RunnerError, canonical


class RunnerConsola:
    """Simula la identidad y las ACL de un clúster y registra cada pedido. Valida cada pedido contra el protocolo."""

    def __init__(self, *, pools=None):
        self.pools = set(pools if pools is not None else ())
        self.usuarios = {}             # identidad -> {'password': str, 'pools': set}
        self.pedidos = []              # [(nodo, accion, pedido)]
        self.terminadas = []           # [(nodo, vmids)]
        self.falla = {}                # accion -> cantidad de fallos que quedan (RunnerError UNCONFIRMED)
        self.error_definitivo = None   # código para devolver como fallo definitivo
        self.nodos_caidos = set()

    async def execute_console_identity(self, request, node):
        request = console_identity.parse_request(canonical(request).encode())
        self.pedidos.append((node, request['action'], request))
        if node in self.nodos_caidos:
            raise RunnerError('RUNNER_UNAVAILABLE')
        accion = request['action']
        if self.falla.get(accion):
            self.falla[accion] -= 1
            raise RunnerError('UNCONFIRMED')
        base = {'protocol': request['protocol'], 'operation_id': request['operation_id'], 'action': accion,
                'identidad': request['identidad'], 'phase': 'verified', 'identity_verified': True,
                'observed_at': '2026-11-04T00:00:00+00:00'}
        if self.error_definitivo:
            return base | {'status': 'failed', 'identity_verified': False,
                           'error': {'code': self.error_definitivo, 'retryable': False}}
        return base | {'status': 'succeeded', 'result': getattr(self, '_' + accion)(request)}

    def _ensure(self, r):
        ident = r['identidad']
        creada = ident not in self.usuarios
        nuevo = creada or self.usuarios[ident].get('revision') != r['revision']
        if creada:
            self.usuarios[ident] = {'password': None, 'pools': set(), 'revision': None}
        if nuevo:
            self.usuarios[ident]['password'] = r['password_consola']
            self.usuarios[ident]['revision'] = r['revision']
        self.usuarios[ident]['pools'] = {p for p in r['pools'] if p in self.pools}
        return {'pools_aplicados': sorted(self.usuarios[ident]['pools']),
                'pools_pendientes': sorted(p for p in r['pools'] if p not in self.pools),
                'creada': creada, 'password': 'aplicada' if nuevo else 'sin_cambios'}

    def _retire(self, r):
        ident = r['identidad']
        if 'pools' in r:
            quitados = sorted(p for p in r['pools'] if ident in self.usuarios and p in self.usuarios[ident]['pools'])
            if ident in self.usuarios:
                self.usuarios[ident]['pools'] -= set(r['pools'])
            return {'retirada': False, 'pools_quitados': quitados}
        quitados = sorted(self.usuarios.pop(ident, {'pools': set()})['pools'])
        return {'retirada': True, 'pools_quitados': quitados}

    def _end_sessions(self, r):
        self.terminadas.append(r['vmids'])
        return {'terminadas': 0}

    def _probe(self, r):
        u = self.usuarios.get(r['identidad'])
        return {'existe': u is not None, 'pools': sorted(u['pools']) if u else [], 'roles': ['NapConsola'] if u and u['pools'] else []}

    # utilidades de las pruebas
    def acciones(self, accion):
        return [p for _, a, p in self.pedidos if a == accion]

    def nodos_de(self, accion):
        return [n for n, a, _ in self.pedidos if a == accion]
