import json

import pytest

from tests.test_guest_runner_client import request


@pytest.fixture
def linux_system(tmp_path):
    from infra.services.common import GuestSystem
    class System(GuestSystem):
        def __init__(self):
            super().__init__(root=tmp_path)
            self.users = {'root': {'uid': 0, 'shell': '/bin/bash'}}
            self.passwords = {'root': '!'}
            self.commands = []
            self.password_writes = 0
        def account(self, name):
            return self.users.get(name)
        def shadow(self, name):
            return self.passwords.get(name)
        def password_matches(self, name, secret):
            return self.passwords.get(name) == secret
        def run(self, argv, *, input=None, **kwargs):
            self.commands.append(list(argv))
            if argv[0].endswith('useradd'):
                self.users['napadmin'] = {'uid': 1000, 'shell': '/bin/bash'}
                self.passwords['napadmin'] = '!'
            if argv[0].endswith('chpasswd'):
                self.password_writes += 1
                self.passwords['napadmin'] = input.strip().split(':', 1)[1]
            if argv[:2] == ['/usr/bin/passwd', '--lock']:
                self.passwords['root'] = '!'
            if argv[:2] == ['/usr/bin/systemctl', 'show']:
                return '[Service]\nExecStart=-/sbin/agetty --noclear console\n'
            return ''
    return System()


def test_linux_creates_console_login_without_autologin_or_password_in_argv(linux_system):
    from infra.services.common import run_product
    from infra.services.linux.bootstrap import Linux
    value = request()
    result = run_product(Linux(), value, system=linux_system)
    assert result['ready'] and result['username'] == 'napadmin'
    assert linux_system.passwords['root'] == '!'
    assert 'private-test-only-value' not in repr(linux_system.commands) + json.dumps(result)
    assert linux_system.read('etc/sudoers.d/napadmin') == 'napadmin ALL=(ALL:ALL) ALL\n'
    assert '--autologin' not in linux_system.read('etc/systemd/system/console-getty.service.d/zz-nap-login.conf')


def test_retry_and_new_operation_never_reset_a_changed_guest_password(linux_system):
    from infra.services.common import run_product, GuestError
    from infra.services.linux.bootstrap import Linux
    from uuid import uuid4
    value = request()
    run_product(Linux(), value, system=linux_system)
    linux_system.passwords['napadmin'] = 'changed-by-the-owner'
    assert run_product(Linux(), value, system=linux_system)['ready']
    assert run_product(Linux(), {**value, 'operation_id': str(uuid4())}, system=linux_system)['ready']
    assert linux_system.password_writes == 1 and linux_system.passwords['napadmin'] == 'changed-by-the-owner'
    modified = {**value, 'secrets': {'guest_password': 'different-private-value'}}
    with pytest.raises(GuestError) as exc:
        run_product(Linux(), modified, system=linux_system)
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'


def test_preexisting_guest_user_is_not_adopted_or_reset(linux_system):
    from infra.services.common import run_product, GuestError
    from infra.services.linux.bootstrap import Linux
    linux_system.users['napadmin'] = {'uid': 1000, 'shell': '/bin/bash'}
    linux_system.passwords['napadmin'] = 'preexisting-password'
    with pytest.raises(GuestError):
        run_product(Linux(), request(), system=linux_system)
    assert linux_system.password_writes == 0


def test_inspection_does_not_create_guest_state_and_no_secret_is_stored_in_plaintext(linux_system):
    from infra.services.common import run_product
    from infra.services.linux.bootstrap import Linux
    value = request()
    inspected = run_product(Linux(), {k: v for k, v in (value | {'action': 'inspect'}).items() if k != 'secrets'}, system=linux_system)
    assert not inspected['ready'] and not (linux_system.root / 'var/lib/nap').exists()
    run_product(Linux(), value, system=linux_system)
    metadata = linux_system.read('var/lib/nap/bootstrap.json')
    assert 'private-test-only-value' not in metadata and value['nonce'] not in metadata
