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
    input_delivered: bool = True


def collect_output(process, output, *, timeout=2700, clock=time.monotonic, input_bytes=None):
    if (type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 2700):
        raise JobError('INVALID_REQUEST')
    deadline = clock() + timeout
    unconfirmed = 0
    ended = set()
    if input_bytes is not None and (type(input_bytes) is not bytes or len(input_bytes)>1048576):raise JobError('INVALID_REQUEST')
    pending=memoryview(input_bytes or b'')
    input_delivered=True
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
            if input_bytes is not None:
                if process.stdin is None:raise JobError('UNCONFIRMED')
                if pending:
                    os.set_blocking(process.stdin.fileno(),False)
                    selector.register(process.stdin,selectors.EVENT_WRITE,data='stdin')
                else:process.stdin.close()
            while selector.get_map() or process.poll() is None:
                remaining = deadline-clock()
                if remaining <= 0: raise JobError('DEADLINE_EXCEEDED')
                for key, _ in selector.select(min(0.25, remaining)):
                    if key.data=='stdin':
                        try:
                            written=os.write(key.fd,pending[:16384]);pending=pending[written:]
                        except BlockingIOError:continue
                        except BrokenPipeError:pending=pending[len(pending):];input_delivered=False
                        if not pending:
                            selector.unregister(key.fileobj);process.stdin.close()
                        continue
                    try: raw = os.read(key.fd, 16384)
                    except BlockingIOError: continue
                    if raw: consume(key.data, raw)
                    else:
                        selector.unregister(key.fileobj)
                        consume(key.data, b'', final=True); ended.add(key.data)
            code = process.poll()
            if type(code) is not int: raise JobError('UNCONFIRMED')
            return CollectionResult(code, unconfirmed, input_delivered)
    except OSError:
        raise JobError('UNCONFIRMED') from None
    finally:
        if input_bytes is not None and process.stdin is not None and not process.stdin.closed:process.stdin.close()
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
