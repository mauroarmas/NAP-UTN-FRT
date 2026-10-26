"""Doble de trabajo remoto durable con confirmación perdida y cierre persistente."""
from copy import deepcopy


class FakeBuilder:
    def __init__(self):
        self.jobs = {}
        self.scopes = {}
        self.lose_confirmation = False
        self.fail_cleanup = False
        self.calls = []

    async def execute(self, request, *, host_id=None):
        self.calls.append(deepcopy(request))
        state = self.scopes.setdefault(request['ensayo_id'], {'max_generation': 0, 'closed': False})
        action = request['action']
        if action != 'status':
            if request['generation'] < state['max_generation']:
                raise ValueError('stale_generation')
            if state['closed'] and action not in {'cancel', 'cleanup'}:
                raise ValueError('ensayo_cerrado')
            state['max_generation'] = request['generation']
        if action == 'cancel':
            state['closed'] = True
        if action == 'cleanup' and (not state['closed'] or self.fail_cleanup):
            raise ValueError('limpieza_no_confirmada')
        key = request['operation_id']
        if action == 'status':
            result = self.jobs.get(request.get('job_id', key))
            return deepcopy(result or {'status': 'not_found', **state})
        result = self.jobs.setdefault(key, {'protocol': 'nap-build-runner/1', 'operation_id': key,
            'job_id': key, 'generation': request['generation'], 'status': 'cancelled' if action == 'cancel' else 'succeeded',
            'result': {}, **state})
        if self.lose_confirmation:
            self.lose_confirmation = False
            raise TimeoutError('confirmacion_perdida')
        return deepcopy(result)
