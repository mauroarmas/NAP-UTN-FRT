"""Doble sin SSH del protocolo cerrado nap-guest-runner/1."""

from copy import deepcopy
import hashlib
import json


class FakeGuestRunner:
    def __init__(self, clock):
        self.clock = clock
        self.identities = {}
        self.results = {}
        self.requests = []
        self.failure = None

    def register(self, request_identity, *, result=None):
        self.identities[request_identity['resource_uuid']] = deepcopy(request_identity)
        self.results[request_identity['resource_uuid']] = result or {'ready': True}

    async def execute(self, request):
        if self.failure:
            raise self.failure
        action = request.get('action')
        if action not in {'inspect', 'bootstrap', 'verify'}:
            raise ValueError('INVALID_REQUEST')
        identity = self.identities.get(request.get('resource_uuid'))
        fields = ['cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool', 'nonce', 'definition_sha256', 'bundle_sha256']
        if not identity or any(identity.get(k) != request.get(k) for k in fields):
            raise ValueError('IDENTITY_MISMATCH')
        # Comparar reintentos sin guardar ni imprimir valores secretos.
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        key = (request['operation_id'], action)
        previous = next((x for x in self.requests if x['key'] == key), None)
        if previous and previous['digest'] != digest:
            raise ValueError('IDEMPOTENCY_CONFLICT')
        if not previous:
            self.requests.append({'key': key, 'digest': digest})
        return {
            'protocol': 'nap-guest-runner/1', 'operation_id': request['operation_id'],
            'action': action, 'resource_uuid': request['resource_uuid'], 'status': 'succeeded',
            'phase': 'verified', 'observed_at': self.clock.now().isoformat(), 'identity_verified': True,
            'result': deepcopy(self.results[request['resource_uuid']]),
        }
