"""Instalación SSH: no reutilizar identidades y comprobar antes de recargar."""
import base64
from pathlib import Path

import pytest


def public_key():
    blob = b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + bytes(range(32))
    return 'ssh-ed25519 ' + base64.b64encode(blob).decode() + ' worker-test'


def test_plan_only_grants_the_fixed_wrapper_to_one_source():
    from infra.runner.configure_access import access_files
    files = access_files('172.16.36.1', public_key())
    key, _ = files['/etc/nap/runner/authorized_keys']
    ssh, _ = files['/etc/ssh/sshd_config.d/00-naprunner.conf']
    sudo, mode = files['/etc/sudoers.d/naprunner']
    assert 'from="172.16.36.1/32"' in key and 'restrict,' in key
    assert 'ForceCommand /usr/bin/sudo -n /usr/local/sbin/nap-guest-runner' in ssh
    assert 'AuthorizedKeysCommand none' in ssh and 'TrustedUserCAKeys none' in ssh
    assert 'DisableForwarding yes' in ssh and 'PasswordAuthentication no' in ssh
    assert sudo.count('NOPASSWD:') == 1 and sudo.endswith('nap-guest-runner ""\n')
    assert '!log_input' in sudo and '!log_output' in sudo and mode == 0o440


@pytest.mark.parametrize('ip', ['0.0.0.0', '::', '127.0.0.1', '224.0.0.1',
    '172.16.36.0/24', '172.16.36.1\nMatch all', 'host.example'])
def test_rejects_ambiguous_source_before_any_mutation(ip):
    from infra.runner.configure_access import access_files
    with pytest.raises(ValueError):
        access_files(ip, public_key())


@pytest.mark.parametrize('key', ['ssh-ed25519 AAAA', 'command="sh" ' + public_key(),
    public_key() + '\n' + public_key(), '-----BEGIN OPENSSH PRIVATE KEY-----'])
def test_rejects_options_multiple_keys_and_private_material(key):
    from infra.runner.configure_access import access_files
    with pytest.raises(ValueError):
        access_files('172.16.36.1', key)


def test_existing_config_or_symlink_never_gets_overwritten(tmp_path):
    from infra.runner.configure_access import ensure_new_paths
    folder = tmp_path / 'etc'
    folder.mkdir()
    config = folder / 'config'
    config.write_text('existing')
    with pytest.raises(ValueError):
        ensure_new_paths([config])
    assert config.read_text() == 'existing'
    config.unlink()
    config.symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError):
        ensure_new_paths([config])
    config.unlink()
    folder.rename(tmp_path / 'real')
    folder.symlink_to(tmp_path / 'real', target_is_directory=True)
    with pytest.raises(ValueError):
        ensure_new_paths([config])


def test_effective_configuration_must_match_all_restrictions():
    from infra.runner.configure_access import validate_effective, EXPECTED
    valid = '\n'.join(k + ' ' + v for k, v in EXPECTED.items())
    validate_effective(valid)
    for option in EXPECTED:
        with pytest.raises(ValueError):
            validate_effective('\n'.join(k + ' ' + v for k, v in EXPECTED.items() if k != option))
    with pytest.raises(ValueError):
        validate_effective(valid.replace('disableforwarding yes', 'disableforwarding no'))


def test_invalid_configuration_removes_new_files_and_never_reloads(tmp_path):
    from infra.runner.configure_access import commit_files
    target = tmp_path / 'new-config'
    calls = []
    def check():
        assert target.read_text() == 'candidate'
        calls.append('check')
        raise ValueError('bad ssh configuration')
    with pytest.raises(ValueError):
        commit_files({str(target): ('candidate', 0o600)}, check,
            lambda: calls.append('activate'))
    assert calls == ['check'] and not target.exists()


def test_failed_activation_rolls_back_and_reloads_previous_config(tmp_path):
    from infra.runner.configure_access import commit_files
    target = tmp_path / 'new-config'
    calls = []
    def activate():
        calls.append(target.exists())
        if target.exists():
            raise ValueError('reload failed')
    with pytest.raises(ValueError):
        commit_files({str(target): ('candidate', 0o600)}, lambda: None, activate)
    assert calls == [True, False] and not target.exists()
