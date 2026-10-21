import json
import ssl

import pytest

from infra.laboratorio import configurar_api_ensayo as setup


class PVE:
    def __init__(self):
        self.writes = []
        self.users = []
        self.roles = []
        self.pools = []
        self.fail_token = False

    def __call__(self, method, route, **params):
        if method == 'get':
            return {'/access/users': self.users, '/access/roles': self.roles,
                '/pools': self.pools, '/cluster/resources': [
                    {'type': 'lxc', 'vmid': 101, 'status': 'stopped'},
                    {'type': 'lxc', 'vmid': 103, 'status': 'stopped'}]}[route]
        self.writes.append((method, route, params))
        if method == 'create' and route.endswith('/token/ensayos'):
            if self.fail_token: raise RuntimeError('fixture token failure')
            return {'value': 'fixture-secret', 'full-tokenid': setup.TOKEN,
                'info': {'privsep': 1, 'expire': params['expire']}}
        return None


def test_default_plan_is_readonly_and_scoped():
    pve = PVE()
    plan = setup.configure(pve, ca='fixture-ca')
    assert not pve.writes
    assert plan['estado'] == 'plan_sin_cambios'
    assert plan['pool'] == 'nap009-staging'
    assert 'VM.Allocate' in plan['roles']['NAP009LabGuest']
    assert plan['grants']['/'] == 'NAP009LabAudit'
    assert not any(p.startswith('VM.Config') or p in {'Sys.Modify', 'VM.Console',
        'VM.Allocate', 'Permissions.Modify'} for p in plan['roles']['NAP009LabAudit'])
    assert '/vms' not in plan['grants']


@pytest.mark.parametrize('existing', ['user', 'role', 'pool'])
def test_collision_aborts_before_any_write(existing, tmp_path):
    pve = PVE()
    if existing == 'user': pve.users = [{'userid': setup.USER}]
    if existing == 'role': pve.roles = [{'roleid': 'NAP009LabGuest'}]
    if existing == 'pool': pve.pools = [{'poolid': setup.POOL}]
    with pytest.raises(ValueError):
        setup.configure(pve, ca='fixture-ca', apply=True, secret_path=tmp_path/'secret.json')
    assert not pve.writes and not (tmp_path/'secret.json').exists()


def test_apply_preserves_existing_guests_and_keeps_token_out_of_report(tmp_path):
    pve = PVE(); secret = tmp_path/'secret.json'
    result = setup.configure(pve, ca='fixture-ca', apply=True, secret_path=secret, now=1000)
    assert 'fixture-secret' not in json.dumps(result)
    assert secret.stat().st_mode & 0o777 == 0o600
    data = json.loads(secret.read_text())
    assert data['proxmox_token_value'] == 'fixture-secret'
    assert data['proxmox_verify_ssl'] is True and data['expire'] == 1000 + 30*86400
    assert not any('/nodes/' in path or '/vms/' in path for _, path, _ in pve.writes)
    assert pve.writes[0][1:] == ('/access/users', {
        'userid': setup.USER, 'enable': 0, 'expire': data['expire'], 'comment': setup.COMMENT})
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 1})
    grants = [params for _, path, params in pve.writes if path == '/access/acl']
    assert len(grants) == 8
    assert all(params.get('tokens') == setup.TOKEN or params.get('users') == setup.USER for params in grants)


def test_cli_numeric_strings_are_validated_without_losing_token(tmp_path):
    pve = PVE()
    def cli(method, route, **params):
        value = pve(method, route, **params)
        if isinstance(value, dict) and 'info' in value:
            value['info'] = {'privsep': '1', 'expire': str(params['expire'])}
        return value
    secret = tmp_path/'secret.json'
    report = setup.configure(cli, ca='fixture-ca', apply=True, secret_path=secret, now=1000)
    assert report['estado'] == 'configurado_pendiente_verificacion_api'
    assert json.loads(secret.read_text())['proxmox_token_value'] == 'fixture-secret'


def test_token_failure_disables_only_new_account_and_retains_diagnostic_marker(tmp_path):
    pve = PVE(); pve.fail_token = True
    secret = tmp_path/'secret.json'
    with pytest.raises(RuntimeError): setup.configure(pve, ca='fixture-ca', apply=True, secret_path=secret)
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 0})
    assert json.loads(secret.read_text())['estado'] == 'incompleto_revisar'
    assert not any(method == 'delete' for method, _, _ in pve.writes)


def test_existing_secret_or_symlink_never_overwritten(tmp_path):
    for name, link in [('file', False), ('link', True)]:
        secret = tmp_path/name
        if link: secret.symlink_to(tmp_path/'absent')
        else: secret.write_text('keep')
        pve = PVE()
        with pytest.raises(FileExistsError):
            setup.configure(pve, ca='fixture-ca', apply=True, secret_path=secret)
        assert not pve.writes


def test_acl_failure_keeps_recoverable_secret_and_disables_account(tmp_path):
    pve = PVE(); secret = tmp_path/'secret.json'
    def fail(method, route, **params):
        if route == '/access/acl': raise RuntimeError('fixture ACL failure')
        return pve(method, route, **params)
    with pytest.raises(RuntimeError): setup.configure(fail, ca='fixture-ca', apply=True, secret_path=secret)
    assert json.loads(secret.read_text())['proxmox_token_value'] == 'fixture-secret'
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 0})
    assert not any(method == 'delete' for method, _, _ in pve.writes)


def test_cli_refuses_non_root_before_network_or_processes(monkeypatch):
    monkeypatch.setattr('sys.argv', ['setup', '--apply'])
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 1000)
    with pytest.raises(SystemExit) as exc: setup.main()
    assert exc.value.code == 2


def tls_error(code=64):
    error = ssl.SSLCertVerificationError(1, 'fixture')
    error.verify_code = code
    error.verify_message = 'fixture IP address mismatch'
    return error


def tls_case(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.socket, 'gethostname', lambda: 'proxmox')
    monkeypatch.setattr(setup.socket, 'getaddrinfo', lambda *args: [(None, None, None, None, (setup.HOST, 0))])
    node = tmp_path/'etc/pve/nodes/proxmox'; node.mkdir(parents=True)
    (tmp_path/'root').mkdir(mode=0o700)
    paths = {node/'pve-ssl.pem': 'old-cert', node/'pve-ssl.key': 'fixture-private-key',
        tmp_path/'etc/pve/pve-root-ca.pem': 'fixture-ca',
        tmp_path/'etc/ssh/ssh_host_ed25519_key.pub': 'fixture-public-hostkey'}
    for path, data in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data)
    return node, paths


def test_matching_tls_does_not_touch_files_or_services(tmp_path):
    result = setup.repair_default_tls('fixture-ca', root=tmp_path,
        probe=lambda ca: None, run=lambda _: pytest.fail('No command allowed'))
    assert result == {'renovado': False} and not list(tmp_path.iterdir())


@pytest.mark.parametrize('code', [10, 18, 20, 85])
def test_expired_or_untrusted_tls_never_triggers_renewal(tmp_path, code):
    def probe(ca): raise tls_error(code)
    with pytest.raises(ValueError):
        setup.repair_default_tls('fixture-ca', root=tmp_path, probe=probe,
            run=lambda _: pytest.fail('No command allowed'))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('condition', ['cluster', 'custom_cert', 'wrong_address'])
def test_renewal_refuses_unknown_environment_before_backup(tmp_path, monkeypatch, condition):
    node, _ = tls_case(tmp_path, monkeypatch)
    if condition == 'cluster': (tmp_path/'etc/pve/corosync.conf').write_text('fixture')
    if condition == 'custom_cert': (node/'pveproxy-ssl.pem').write_text('fixture')
    if condition == 'wrong_address':
        monkeypatch.setattr(setup.socket, 'getaddrinfo', lambda *args: [(None, None, None, None, ('192.168.1.2', 0))])
    def probe(ca): raise tls_error()
    with pytest.raises(ValueError):
        setup.repair_default_tls('fixture-ca', root=tmp_path, probe=probe,
            run=lambda _: pytest.fail('No command allowed'))
    assert not list((tmp_path/'root').iterdir())


def test_renewal_backs_up_identity_privately_and_rechecks_tls(tmp_path, monkeypatch):
    node, paths = tls_case(tmp_path, monkeypatch)
    calls = []; probes = []
    def probe(ca):
        probes.append(ca)
        if len(probes) == 1: raise tls_error()
    def run(argv):
        calls.append(argv)
        if 'updatecerts' in argv: (node/'pve-ssl.pem').write_text('renewed-cert')
    result = setup.repair_default_tls('fixture-ca', root=tmp_path, probe=probe, run=run)
    assert result['renovado'] and len(probes) == 2
    backup = setup.Path(result['respaldo_root'])
    assert backup.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in backup.iterdir())
    assert (backup/'pve-ssl.key').read_text() == 'fixture-private-key'
    assert 'fixture-private-key' not in json.dumps(result)
    assert calls == [['/usr/bin/pvecm', 'updatecerts', '--force'], ['/usr/bin/systemctl', 'reload', 'pveproxy']]
    assert paths[tmp_path/'etc/pve/pve-root-ca.pem'] == (tmp_path/'etc/pve/pve-root-ca.pem').read_text()


def test_failed_certificate_command_preserves_backup(tmp_path, monkeypatch):
    tls_case(tmp_path, monkeypatch)
    def probe(ca): raise tls_error()
    def failed(argv): raise RuntimeError('fixture failure')
    with pytest.raises(RuntimeError): setup.repair_default_tls('fixture-ca', root=tmp_path, probe=probe, run=failed)
    backups = list((tmp_path/'root').iterdir())
    assert len(backups) == 1 and (backups[0]/'pve-ssl.key').read_text() == 'fixture-private-key'


def test_tls_error_reports_stage_without_attempting_api_write(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['setup', '--apply'])
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(setup.Path, 'is_dir', lambda self: True)
    monkeypatch.setattr(setup.Path, 'read_text', lambda self: 'fixture-ca')
    def probe(ca): raise tls_error()
    monkeypatch.setattr(setup, 'verify_tls', probe)
    monkeypatch.setattr(setup, 'configure', lambda *args, **kw: pytest.fail('No API writes allowed'))
    assert setup.main() == 1
    output = capsys.readouterr()
    assert not output.out and 'verificar_tls' in output.err and 'tls_codigo' in output.err


class RecoveryPVE(PVE):
    def __init__(self):
        super().__init__()
        self.expire = 1000 + 30*86400
        self.users = [{'userid': setup.USER, 'enable': '0', 'expire': str(self.expire), 'comment': setup.COMMENT}]
        self.roles = [{'roleid': name, 'privs': ','.join(privs)} for name, privs in setup.ROLES.items()]
        self.members = []; self.acl = []

    def __call__(self, method, route, **params):
        if method == 'get' and route == '/pools/'+setup.POOL:
            return {'comment': setup.COMMENT, 'members': self.members}
        if method == 'get' and route == '/access/users/'+setup.USER+'/token':
            return [{'tokenid': setup.TOKEN_NAME, 'privsep': '1', 'expire': str(self.expire), 'comment': setup.COMMENT}]
        if method == 'get' and route == '/access/acl': return self.acl
        value = super().__call__(method, route, **params)
        if method == 'create' and route.endswith('/token/ensayos'):
            value['info'] = {'privsep': '1', 'expire': str(self.expire)}
        return value


def recovery_case(tmp_path, pve):
    secret = tmp_path/'secret.json'
    secret.write_text(json.dumps({'estado': 'incompleto_revisar', 'usuario': setup.USER})); secret.chmod(0o600)
    sha = setup.snapshot_sha(setup.recovery_snapshot(pve))
    return secret, sha


def test_reviewed_orphan_is_rotated_without_recreating_objects(tmp_path):
    pve = RecoveryPVE(); secret, sha = recovery_case(tmp_path, pve)
    result = setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert result['token_orfano_reemitido']
    assert json.loads(secret.read_text())['proxmox_token_value'] == 'fixture-secret'
    assert pve.writes[0][:2] == ('delete', '/access/users/'+setup.USER+'/token/ensayos')
    assert [r for r in pve.writes if r[0] == 'create'] == [('create', '/access/users/'+setup.USER+'/token/ensayos',
        {'privsep': 1, 'expire': pve.expire, 'comment': setup.COMMENT})]
    assert len([r for r in pve.writes if r[1] == '/access/acl']) == 8
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 1})
    assert 'fixture-secret' not in json.dumps(result)
    assert setup.Path(result['respaldo_root']).stat().st_mode & 0o777 == 0o700


def test_previously_saved_token_is_preserved(tmp_path):
    pve = RecoveryPVE(); secret, sha = recovery_case(tmp_path, pve)
    with secret.open('w') as handle:
        setup.token_private({'value': 'existing-secret', 'full-tokenid': setup.TOKEN,
            'info': {'privsep': 1, 'expire': pve.expire}}, ca='fixture-ca', expire=pve.expire, handle=handle)
    result = setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert not result['token_orfano_reemitido']
    assert json.loads(secret.read_text())['proxmox_token_value'] == 'existing-secret'
    assert all(method == 'set' for method, _, _ in pve.writes)


@pytest.mark.parametrize('changed', ['user', 'privileges', 'members', 'acl', 'marker'])
def test_changed_or_unowned_state_blocks_all_mutations(tmp_path, changed):
    pve = RecoveryPVE(); secret, sha = recovery_case(tmp_path, pve)
    if changed == 'user': pve.users[0]['enable'] = 1
    if changed == 'privileges': pve.roles[0]['privs'] += ',Sys.Modify'
    if changed == 'members': pve.members = [{'vmid': 101}]
    if changed == 'acl': pve.acl = [{'ugid': setup.USER, 'path': '/', 'roleid': 'Administrator'}]
    if changed == 'marker': secret.write_text(json.dumps({'estado': 'unrelated', 'usuario': setup.USER}))
    before = secret.read_bytes()
    with pytest.raises(setup.PreparationError):
        setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert not pve.writes and secret.read_bytes() == before
    assert list(tmp_path.iterdir()) == [secret]


def test_reviewed_hash_does_not_override_semantic_safety(tmp_path):
    pve = RecoveryPVE(); pve.members = [{'vmid': 101}]
    secret, sha = recovery_case(tmp_path, pve)
    with pytest.raises(setup.PreparationError):
        setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert not pve.writes


def test_rotation_failure_records_pending_state_and_never_retries(tmp_path):
    pve = RecoveryPVE(); secret, sha = recovery_case(tmp_path, pve); pve.fail_token = True
    with pytest.raises(RuntimeError):
        setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert json.loads(secret.read_text())['estado'] == 'recuperacion_token_orfano_pendiente'
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 0})
    pve.writes.clear()
    with pytest.raises(setup.PreparationError):
        setup.resume_reviewed(pve, ca='fixture-ca', expected_sha=sha, secret_path=secret, now=1000)
    assert not pve.writes


def test_invalid_token_metadata_is_retained_privately_and_account_disabled(tmp_path):
    pve = PVE(); secret = tmp_path/'secret.json'
    def invalid(method, route, **params):
        value = pve(method, route, **params)
        if method == 'create' and route.endswith('/token/ensayos'): value['info']['privsep'] = '0'
        return value
    with pytest.raises(setup.PreparationError):
        setup.configure(invalid, ca='fixture-ca', apply=True, secret_path=secret)
    assert json.loads(secret.read_text())['token_response']['value'] == 'fixture-secret'
    assert pve.writes[-1] == ('set', '/access/users/'+setup.USER, {'enable': 0})


def test_pvesh_command_failure_exposes_only_operation_not_response(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(setup.subprocess, 'run', lambda *args, **kwargs:
        SimpleNamespace(returncode=1, stdout=b'fixture-secret'))
    with pytest.raises(setup.PVECommandError) as exc:
        setup.pvesh('create', '/access/users/'+setup.USER+'/token/ensayos')
    assert exc.value.operation == {'metodo': 'create',
        'ruta': '/access/users/'+setup.USER+'/token/ensayos', 'salida': 1}
    assert 'fixture-secret' not in str(exc.value)


@pytest.mark.parametrize('value', [1.0, '01', 'true', True])
def test_numeric_normalization_does_not_accept_ambiguous_values(value):
    with pytest.raises(setup.PreparationError): setup.integer(value)
