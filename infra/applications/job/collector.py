"""Drain child pipes continuously; raw bytes never reach disk or the journal.

The consumer is the closed redactor, registered before the child is executed.
Fragments admitted by it are emitted immediately. Incomplete unknown text is
kept/suppressed by that bounded filter, never flushed raw on a timer.
"""
from dataclasses import dataclass
import math
import os
import selectors
import time

from .protocol import JobError


@dataclass(frozen=True)
class CollectionResult:
    returncode: int
    unconfirmed_chunks: int


def collect_output(process, output, *, timeout=2700, clock=time.monotonic):
    if (type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 2700):
        raise JobError('INVALID_REQUEST')
    deadline = clock() + timeout
    unconfirmed = 0
    ended = set()
    def consume(stream, raw, *, final=False):
        nonlocal unconfirmed
        try: output(stream, raw, final=final)
        except JobError as exc:
            if exc.code == 'DEADLINE_EXCEEDED': raise
            unconfirmed = min(unconfirmed+1, 2**63-1)
        except Exception: unconfirmed = min(unconfirmed+1, 2**63-1)
    try:
        with selectors.DefaultSelector() as selector:
            for stream in ('stdout', 'stderr'):
                file = getattr(process, stream)
                if file is None: raise JobError('UNCONFIRMED')
                os.set_blocking(file.fileno(), False)
                selector.register(file, selectors.EVENT_READ, data=stream)
            while selector.get_map() or process.poll() is None:
                remaining = deadline-clock()
                if remaining <= 0: raise JobError('DEADLINE_EXCEEDED')
                for key, _ in selector.select(min(0.25, remaining)):
                    try: raw = os.read(key.fd, 16384)
                    except BlockingIOError: continue
                    if raw: consume(key.data, raw)
                    else:
                        selector.unregister(key.fileobj)
                        consume(key.data, b'', final=True); ended.add(key.data)
            code = process.poll()
            if type(code) is not int: raise JobError('UNCONFIRMED')
            return CollectionResult(code, unconfirmed)
    except OSError:
        raise JobError('UNCONFIRMED') from None
    finally:
        cleanup_deadline = None
        for stream in ('stdout', 'stderr'):
            file = getattr(process, stream, None)
            if stream not in ended:
                try: consume(stream, b'', final=True)
                except JobError as exc: cleanup_deadline = exc
            if file is not None: file.close()
        if process.poll() is None:
            # The caller owns this child. Guest/daemon state still needs a probe;
            # killing a transport process is not proof of installation failure.
            try: process.kill(); process.wait(timeout=2)
            except Exception: pass
        if cleanup_deadline is not None: raise cleanup_deadline
