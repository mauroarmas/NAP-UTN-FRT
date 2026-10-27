"""Transporte OpenSSH asíncrono con hostkeys fijadas y protocolo por stdin."""
import asyncio
from contextlib import suppress
import ipaddress
import os
from pathlib import Path
import re
import signal
import stat

from app.config import get_settings
from app.schemas.guest_runner import RunnerError, canonical, parse_request, parse_response


def _file(path, *, private):
    try:
        path = Path(path)
        if (not path.is_absolute() or path.parent.resolve() != path.parent or path.is_symlink()
            or not path.parent.is_dir() or path.parent.stat().st_mode & 0o022):
            raise ValueError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & (0o077 if private else 0o022) or not 0 < info.st_size <= 1048576):
                raise ValueError()
        finally:
            os.close(fd)
        return str(path)
    except (TypeError, ValueError, OSError):
        raise RunnerError('RUNNER_UNAVAILABLE') from None


def _destination(entry):
    try:
        if not isinstance(entry, dict) or set(entry) != {'host', 'user', 'port', 'private_key_path', 'known_hosts_path'}:
            raise ValueError()
        host, user, port = entry['host'], entry['user'], entry['port']
        if not isinstance(host, str) or len(host) > 253 or not host:
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', part) for part in host.split('.')):
                raise ValueError()
        if not isinstance(user, str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user) or user in {'root', 'nobody'}:
            raise ValueError()
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
        return host, user, port, _file(entry['private_key_path'], private=True), _file(entry['known_hosts_path'], private=False)
    except (TypeError, ValueError, KeyError):
        raise RunnerError('RUNNER_UNAVAILABLE') from None


def ssh_argv(entry):
    """Only an institutional destination and a fixed forced command."""
    host, user, port, key, hosts = _destination(entry)
    options = ['BatchMode=yes', 'StrictHostKeyChecking=yes', 'IdentitiesOnly=yes', 'IdentityAgent=none',
        'UserKnownHostsFile=' + hosts, 'GlobalKnownHostsFile=/dev/null', 'UpdateHostKeys=no', 'VerifyHostKeyDNS=no',
        'ProxyCommand=none', 'ProxyJump=none', 'PermitLocalCommand=no', 'PasswordAuthentication=no',
        'KbdInteractiveAuthentication=no', 'PreferredAuthentications=publickey', 'ConnectionAttempts=1',
        'ConnectTimeout=10', 'ServerAliveInterval=15', 'ServerAliveCountMax=2', 'RequestTTY=no',
        'ClearAllForwardings=yes', 'ControlMaster=no', 'ControlPath=none', 'ControlPersist=no', 'EscapeChar=none']
    argv = ['/usr/bin/ssh', '-F', '/dev/null', '-T', '-i', key, '-p', str(port), '-l', user]
    for option in options: argv += ['-o', option]
    return argv + ['--', host, 'nap-guest-runner']


class GuestRunnerClient:
    response_limit = 65536
    def __init__(self, *, config=None, start_process=None, timeout_seconds=180):
        self.config = get_settings().runner_nodes if config is None else config
        self.start_process = start_process or asyncio.create_subprocess_exec
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 180:
            raise ValueError('Deadline fuera del límite del protocolo')
        self.timeout_seconds = timeout_seconds

    def validar_destino(self, node):
        _destination(self.config.get(node) if isinstance(self.config, dict) else None)

    async def _exchange(self, process, raw):
        if not hasattr(process, 'stdout'):
            # Doble explícito de transporte usado en pruebas; el proceso real
            # siempre usa streams acotados y descarta stderr desde su creación.
            output, _ = await process.communicate(input=raw)
            if not isinstance(output, bytes) or len(output) > self.response_limit:
                raise RunnerError('UNCONFIRMED')
            return output
        async def send():
            try:
                process.stdin.write(raw)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()
                with suppress(BrokenPipeError, ConnectionResetError):
                    await process.stdin.wait_closed()
        async def receive():
            result = bytearray()
            while True:
                chunk = await process.stdout.read(8192)
                if not chunk:
                    return bytes(result)
                result.extend(chunk)
                if len(result) > self.response_limit:
                    raise RunnerError('UNCONFIRMED')
        tasks = [asyncio.create_task(send()), asyncio.create_task(receive()), asyncio.create_task(process.wait())]
        try:
            results = await asyncio.gather(*tasks)
            return results[1]
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _stop(self, process):
        if process is None or process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            if hasattr(process, 'pid'):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        with suppress(asyncio.TimeoutError, ProcessLookupError):
            await asyncio.wait_for(process.wait(), timeout=1)

    async def execute(self, request):
        try:
            raw = canonical(request).encode()
        except (TypeError, ValueError, RecursionError):
            raise RunnerError('INVALID_REQUEST') from None
        request = parse_request(raw)
        entry = self.config.get(request['node']) if isinstance(self.config, dict) else None
        argv = ssh_argv(entry)
        process = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                process = await self.start_process(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, limit=65537, start_new_session=True,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
                output = await self._exchange(process, raw)
                if process.returncode != 0:
                    raise RunnerError('RUNNER_UNAVAILABLE')
                return parse_response(output, request)
        except asyncio.CancelledError:
            await self._stop(process)
            raise
        except (TimeoutError, OSError, ValueError):
            raise RunnerError('UNCONFIRMED') from None
        finally:
            await self._stop(process)
