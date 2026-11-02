"""Pruebas automatizadas (sin Proxmox) de los scripts del laboratorio de Ivan (frt/pve91 + TrueNAS).

No sustituyen la validación real: sólo evitan que los scripts se desalineen del motor
(digest vigente), que pierdan revisiones históricas o que reintroduzcan borrados heurísticos.
"""
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT/'docs/infraestructura-laboratorio/scripts'


def heredoc_python(script, nth=0):
    """Cuerpo del n-ésimo heredoc `<<'PY'` de un script shell."""
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", (SCRIPTS/script).read_text(), flags=re.S)
    return blocks[nth]


def test_expected_digest_follows_current_engine():
    sys.path.insert(0, str(ROOT))
    from infra.applications.docker.runtime import policy_digest
    text = (SCRIPTS/'actualizar-nodos-011.sh').read_text()
    assert re.search(r'^DIGEST_ESPERADO=\$\{DIGEST_ESPERADO:-([0-9a-f]{64})\}$', text, flags=re.M).group(1) == policy_digest()


def test_orphan_table_script_no_longer_deletes_anything():
    text = (SCRIPTS/'limpiar-tablas-huerfanas-pve91.sh').read_text()
    assert 'nft delete' not in text and 'APLICAR' not in text
    assert 'cleanup' in text   # remite a la acción cerrada del motor


def test_destructive_cluster_script_is_labeled_as_independent_infrastructure():
    text = (SCRIPTS/'quitar-nodos-offline.sh').read_text()
    assert 'ADVERTENCIA' in text and 'pvecm delnode' in text


def _runner(tmp_path, revision_states):
    d = {'id': 'docker-ubuntu24', 'revision': 1, 'origen': 'imagen_docker',
         'base': {'volumen_lxc': 'local:vztmpl/old.tar.zst', 'sha256': 'a'*64},
         'cluster_uuid': '0d69119f-054a-40b3-b3c1-4b1b2c707917', 'nodes': ['pve91'],
         'platform': {'pve': '9.2.2', 'kernel': 'old', 'arquitectura': 'amd64'}, 'policy_bundle_sha256': '7'*64}
    profiles = {}
    for rev, estado in revision_states.items():
        entry = copy.deepcopy(d); entry['revision'] = rev
        profiles['docker-ubuntu24:%d' % rev] = {'definition': entry, 'sha256': 'h%d' % rev, 'estado': estado,
            'motivo_codigo': None, 'validacion': {'tipo': 'proxmox_real'} if estado == 'habilitado' else None}
    path = tmp_path/'actual.json'
    path.write_text(json.dumps({'node': 'pve91', 'profiles': profiles, 'networks': {}}))
    return path


def _generate(tmp_path, source, rev='2'):
    """Ejecuta en proceso el generador de runner.json; devuelve (código de salida, mensaje)."""
    code = heredoc_python('actualizar-nodos-011.sh')
    argv = ['-', str(source), str(tmp_path/'nuevo.json'), '4'*64, '9.2.3', 'kernel-nuevo', 'plantilla.tar.zst', rev, 'pve91']
    saved = sys.argv
    sys.argv = argv
    try:
        exec(compile(code, 'actualizar-nodos-011.sh:PY', 'exec'), {'__name__': '__main__'})
        return 0, ''
    except SystemExit as exc:
        return 1, str(exc.code)
    finally:
        sys.argv = saved


def test_update_adds_a_pending_revision_and_keeps_history_untouched(tmp_path):
    source = _runner(tmp_path, {1: 'habilitado'})
    code, message = _generate(tmp_path, source)
    assert code == 0, message
    new = json.loads((tmp_path/'nuevo.json').read_text())
    old = json.loads(source.read_text())
    assert new['profiles']['docker-ubuntu24:1'] == old['profiles']['docker-ubuntu24:1']
    entry = new['profiles']['docker-ubuntu24:2']
    assert (entry['estado'], entry['motivo_codigo'], entry['validacion']) == ('pendiente_validacion', 'VALIDATION_REQUIRED', None)
    assert entry['definition']['policy_bundle_sha256'] == '4'*64 and entry['definition']['nodes'] == ['pve91']
    canon = json.dumps(entry['definition'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert entry['sha256'] == hashlib.sha256(canon).hexdigest()
    assert 'APPLICATION_PROFILES=' in (tmp_path/'APPLICATION_PROFILES.env').read_text()


def test_update_refuses_to_rewrite_an_enabled_revision(tmp_path):
    source = _runner(tmp_path, {1: 'habilitado', 2: 'habilitado'})
    code, message = _generate(tmp_path, source)
    assert code != 0 and 'no se reescribe' in message
    assert not (tmp_path/'nuevo.json').exists()


def test_enable_script_requires_persistence_and_confirmed_job_evidence():
    text = (SCRIPTS/'habilitar-perfil-pve91.sh').read_text()
    for needle in ('evidencia-mariadb-rev', 'persistencia-mariadb-rev', 'autenticacion_tcp', 'recuperado_tras_reinicio',
                   'current.update(added)'):
        assert needle in text


def test_gate_launcher_does_not_treat_data_mount_as_persistence():
    text = (SCRIPTS/'gate-docker-pve91.sh').read_text()
    assert 'NO acredita' in text and 'persistencia)' in text
