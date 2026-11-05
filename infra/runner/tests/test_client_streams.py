"""Opt-in local: streams del cliente con Python efímero, sin ejecutar SSH."""
import asyncio

import pytest

from tests.test_guest_runner_client import request


pytestmark = pytest.mark.integration


def test_client_real_streams_use_stdin_and_discard_stderr(tmp_path):
    from app.services.guest_runner_client import GuestRunnerClient
    key, hosts = tmp_path / 'key', tmp_path / 'hosts'
    key.write_text('not-a-real-key'); key.chmod(0o600)
    hosts.write_text('test-only'); hosts.chmod(0o644)
    config = {'pve1': {'host': 'pve-test.invalid', 'user': 'naprunner', 'port': 22,
        'private_key_path': str(key), 'known_hosts_path': str(hosts)}}
    script = '''import sys,json,datetime
r=json.load(sys.stdin)
v={k:r[k] for k in ['protocol','operation_id','action','resource_uuid']}
v.update(status='succeeded',phase='verified',identity_verified=True,
 observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),result={'ready':True})
print('private-stderr-must-be-discarded',file=sys.stderr)
print(json.dumps(v))
'''
    async def run():
        async def start(*argv, **options):
            assert argv[0] == '/usr/bin/ssh' and options['stderr'] == asyncio.subprocess.DEVNULL
            return await asyncio.create_subprocess_exec('/usr/bin/python3', '-c', script, **options)
        return await GuestRunnerClient(config=config, start_process=start).execute(request())
    assert asyncio.run(run())['status'] == 'succeeded'


def test_client_real_streams_reject_large_output(tmp_path):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    key, hosts = tmp_path / 'key', tmp_path / 'hosts'
    key.write_text('not-a-real-key'); key.chmod(0o600)
    hosts.write_text('test-only'); hosts.chmod(0o644)
    config = {'pve1': {'host': 'pve-test.invalid', 'user': 'naprunner', 'port': 22,
        'private_key_path': str(key), 'known_hosts_path': str(hosts)}}
    async def run():
        async def start(*argv, **options):
            return await asyncio.create_subprocess_exec('/usr/bin/python3', '-c', 'import os; os.write(1,b"x"*131072)', **options)
        with pytest.raises(RunnerError) as exc:
            await GuestRunnerClient(config=config, start_process=start).execute(request())
        assert exc.value.code == 'UNCONFIRMED'
    asyncio.run(run())
