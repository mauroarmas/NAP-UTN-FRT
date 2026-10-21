"""Opt-in local: procesos Python efímeros, sin SSH/PVE/red."""
import pytest


pytestmark = pytest.mark.integration


def test_local_process_stdin_and_output_limit():
    from app.schemas.guest_runner import RunnerError
    from infra.runner.node_executor import bounded_command
    value = b'private-local-process-test' * 5000
    echo = ['/usr/bin/python3', '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())']
    assert bounded_command(echo, input=value, timeout=3) == value
    with pytest.raises(RunnerError) as exc:
        bounded_command(['/usr/bin/python3', '-c', 'print("x" * 4096)'], timeout=3, limit=128)
    assert exc.value.code == 'UNCONFIRMED'


def test_local_process_timeout_terminates_without_waiting_for_completion():
    from app.schemas.guest_runner import RunnerError
    from infra.runner.node_executor import bounded_command
    with pytest.raises(RunnerError) as exc:
        bounded_command(['/usr/bin/python3', '-c', 'import time; time.sleep(30)'], timeout=0.1)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
