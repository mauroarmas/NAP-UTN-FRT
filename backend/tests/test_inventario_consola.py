import pytest

from scripts.importar_identidades_consola import validate_inventory


@pytest.mark.parametrize('entries', [
    [{'usuario_id': 1, 'estado': 'asignada', 'identidad': 'root@pam'}],
    [{'usuario_id': True, 'estado': 'sin_identidad', 'identidad': None}],
    [{'usuario_id': 1, 'estado': 'asignada', 'identidad': 'user@pve'},
     {'usuario_id': 2, 'estado': 'asignada', 'identidad': 'user@pve'}],
    [{'usuario_id': 1, 'estado': 'sin_identidad', 'identidad': None},
     {'usuario_id': 1, 'estado': 'sin_identidad', 'identidad': None}],
    [{'usuario_id': 1, 'estado': 'sin_identidad', 'identidad': 'user@pve'}],
    [{'usuario_id': 1, 'estado': 'sin_identidad', 'identidad': None, 'password': 'forbidden'}],
])
def test_inventory_refuses_ambiguous_shared_or_secret_bearing_input(entries):
    with pytest.raises(ValueError):
        validate_inventory(entries)


def test_inventory_accepts_individual_identity_and_explicit_absence():
    entries = [{'usuario_id': 1, 'estado': 'asignada', 'identidad': 'docente@pve'},
               {'usuario_id': 2, 'estado': 'sin_identidad', 'identidad': None}]
    assert validate_inventory(entries) == entries
