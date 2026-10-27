import os
import selectors
from threading import Thread, Event

import pytest

from infra.applications.job.collector import collect_output
from infra.applications.job.protocol import JobError


class PipeProcess:
    def __init__(self):
        out, self.out_writer = os.pipe(); err, self.err_writer = os.pipe()
        self.stdout = os.fdopen(out, 'rb', buffering=0)
        self.stderr = os.fdopen(err, 'rb', buffering=0)
        self.done = Event(); self.killed = False
    def poll(self): return 0 if self.done.is_set() else None
    def wait(self, timeout=None):
        assert self.done.wait(timeout)
        return -9 if self.killed else 0
    def kill(self):
        self.killed = True
        self.finish()
    def finish(self):
        for name in ('out_writer', 'err_writer'):
            descriptor = getattr(self, name)
            if descriptor is not None: os.close(descriptor); setattr(self, name, None)
        self.done.set()


def test_drains_both_streams_with_bounded_reads_and_short_polling(monkeypatch):
    process = PipeProcess(); captured = []; waits = []
    original = selectors.DefaultSelector
    class RecordingSelector(original):
        def select(self, timeout=None):
            waits.append(timeout)
            return super().select(timeout)
    monkeypatch.setattr(selectors, 'DefaultSelector', RecordingSelector)
    def producer():
        try:
            for _ in range(30): os.write(process.out_writer, b'x'*16384)
            os.write(process.err_writer, b'error-stream\n')
        finally: process.finish()
    thread = Thread(target=producer); thread.start()
    try:
        result = collect_output(process, lambda stream, raw, **kw: captured.append((stream, len(raw), kw)), timeout=5)
    finally: thread.join(timeout=2); process.finish()
    assert result.returncode == 0 and result.unconfirmed_chunks == 0
    assert sum(size for stream,size,_ in captured if stream == 'stdout') == 30*16384
    assert sum(size for stream,size,_ in captured if stream == 'stderr') == len(b'error-stream\n')
    assert all(size <= 16384 for _,size,_ in captured)
    assert all(0 <= value <= 0.25 for value in waits)
    assert sum(bool(kw.get('final')) for _,_,kw in captured) == 2


@pytest.mark.parametrize('failure',[OSError,MemoryError])
def test_failed_console_consumer_does_not_block_the_child(failure):
    process = PipeProcess()
    def producer():
        try:
            for _ in range(100): os.write(process.out_writer, b'x'*16384)
        finally: process.finish()
    def full(*args, **kwargs): raise failure('fixture: console storage unavailable')
    thread = Thread(target=producer); thread.start()
    try: result = collect_output(process, full, timeout=5)
    finally: thread.join(timeout=2); process.finish()
    assert result.returncode == 0 and result.unconfirmed_chunks > 0 and not process.killed


def test_deadline_is_uncertain_and_never_reported_as_exit_success():
    process = PipeProcess()
    with pytest.raises(JobError, match='DEADLINE_EXCEEDED'):
        collect_output(process, lambda *args, **kwargs: None, timeout=0.01)
    assert process.killed
