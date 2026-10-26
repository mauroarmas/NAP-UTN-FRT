"""Producto Draw.io usa el mismo cercado de identidad y bundles del runner."""
import json
from copy import deepcopy
from infra.runner.tests.test_runner import runner_case


def test_drawio_idempotente_y_deniega_identidad_ajena(runner_case):
    runner,node,value,registry,_=runner_case
    entry=next(iter(registry.values()));entry['product']='drawio'
    value['parameters']={'display_name':'Diagramas'};value['secrets']={'access_password':'unique-drawio-password'}
    first=runner.handle(json.dumps(value).encode())
    assert first['status']=='succeeded' and node.calls==1
    assert runner.handle(json.dumps(value).encode())['status']=='succeeded' and node.calls==1
    node.mismatch=True
    wrong=deepcopy(value);wrong['operation_id']='22222222-2222-4222-8222-222222222222'
    result=runner.handle(json.dumps(wrong).encode())
    assert result['status']=='failed' and node.calls==1
    assert 'unique-drawio-password' not in json.dumps(result)
