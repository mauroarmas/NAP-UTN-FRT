"""Short SSH requests to an independently supervised application job.

Start and ACK are sent once. A lost start response requires status reconciliation;
it never restarts the remote service. Closing this transport only kills local SSH.
"""
import asyncio
import re

from infra.applications.job.protocol import (JobError, canonical, fingerprint,
    parse_request, parse_response, MAX_RESPONSE_BYTES)
from .guest_runner_client import GuestRunnerClient, RunnerError, ssh_argv


class ApplicationJobClient(GuestRunnerClient):
    response_limit = MAX_RESPONSE_BYTES

    def __init__(self, *, config=None, start_process=None, timeout_seconds=20, query_retries=1):
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int,float))
                or not 0 < timeout_seconds <= 30 or type(query_retries) is not int or not 0 <= query_retries <= 2):
            raise ValueError('Invalid short request budget')
        super().__init__(config=config, start_process=start_process, timeout_seconds=timeout_seconds)
        self.query_retries = query_retries

    async def _once(self, argv, raw):
        process = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                process = await self.start_process(*argv, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    limit=self.response_limit+1, start_new_session=True,
                    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
                output = await self._exchange(process, raw)
                if process.returncode != 0: raise JobError('UNCONFIRMED')
                return output
        except asyncio.CancelledError:
            raise
        except (TimeoutError, OSError, ValueError, RunnerError):
            raise JobError('UNCONFIRMED') from None
        finally:
            await self._stop(process)

    async def execute(self, request, *, node=None, expected_fingerprint=None):
        try: raw = canonical(request)
        except (TypeError, ValueError, RecursionError, UnicodeError):
            raise JobError('INVALID_REQUEST') from None
        request = parse_request(raw)
        action = request['action']
        if action != 'profiles':
            if node is not None and node != request['node']: raise JobError('IDENTITY_MISMATCH')
            node = request['node']
            if action == 'start':
                actual = fingerprint(request)
                if expected_fingerprint is not None and expected_fingerprint != actual: raise JobError('EXECUTION_CONFLICT')
                expected_fingerprint = actual
            if type(expected_fingerprint) is not str or not re.fullmatch('[a-f0-9]{64}', expected_fingerprint):
                raise JobError('INVALID_REQUEST')
        try:
            argv = ssh_argv(self.config.get(node) if isinstance(self.config,dict) and type(node) is str else None)
        except RunnerError: raise JobError('PROFILE_UNAVAILABLE') from None
        attempts = 1+self.query_retries if action in {'profiles','status','read'} else 1
        for attempt in range(attempts):
            try:
                output = await self._once(argv,raw)
                break
            except JobError as error:
                if error.code != 'UNCONFIRMED' or attempt == attempts-1: raise
        try: response = parse_response(output,request=request)
        except JobError: raise JobError('UNCONFIRMED') from None
        if (response['ok'] and action != 'profiles'
                and response['data']['fingerprint'] != expected_fingerprint):
            raise JobError('EXECUTION_CONFLICT')
        return response
