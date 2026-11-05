"""El acceso SSH a Linux IaaS (feature 017) no debe alterar el policy_digest del motor Docker.

Los perfiles Docker validados quedan atados a ese digest: tocar cualquiera de sus entradas obliga a una
revisión de perfil y a un gate real en cada nodo. Esta prueba registra qué archivos entran al digest y falla
si alguno pertenece al acceso SSH.
"""
from pathlib import Path

from infra.applications.docker import runtime

FEATURE_017 = {'iaas_access.py', 'iaas_protocol.py', 'ssh_keys.py', 'nap_guest_runner.py',
               'console_identity.py', 'console_identity_protocol.py'}   # feature 022: identidades de consola


def test_los_archivos_del_acceso_ssh_no_entran_al_policy_digest(monkeypatch):
    leidos = []
    monkeypatch.setattr(runtime, 'trusted_bytes', lambda path: leidos.append(Path(path)) or b'x')
    runtime.policy_digest()
    assert leidos, 'policy_digest dejó de leer archivos'
    assert not {path.name for path in leidos} & FEATURE_017
    assert not any(path.name == 'schemas' and path.parent.name == 'app' for path in leidos)
    assert not any('iaas_access' in str(path) for path in leidos)
