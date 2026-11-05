import sqlite3

import pytest

from infra.applications.job.spool import Spool
from infra.applications.job.protocol import JobError, canonical
from infra.applications.tests.test_job_supervisor import rig, call


def spool(rig, **kwargs):
    return Spool(store=rig.store, execution_id=rig.request['execution_id'], **kwargs)


def test_spool_survives_reopen_reads_replay_and_ack_only_retires_confirmed_prefix(rig):
    call(rig); output = spool(rig)
    for n in range(4): assert output.append_safe(fase='instalacion', stream='sistema', texto_depurado=f'Paso {n}')
    replay = spool(rig)
    with rig.store.lock('resource', rig.request['resource_uuid']):
        job = rig.store.read_job(rig.request['execution_id'])
        first = replay.read_locked(job, after=0, limit_bytes=65536)
        assert first == replay.read_locked(job, after=0, limit_bytes=65536)
        assert [i['source_seq'] for i in first['items']] == [1,2,3,4]
        replay.ack_locked(job, through_seq=2)
        assert [i['source_seq'] for i in replay.read_locked(job, after=0, limit_bytes=65536)['items']] == [3,4]
        with pytest.raises(JobError): replay.ack_locked(job, through_seq=5)
        assert replay.summary_locked(job) == {'last_source_seq': 4, 'acknowledged_seq': 2}


def test_quota_is_bounded_and_reports_real_dropped_prefix_without_stalling_writer(rig):
    call(rig); output = spool(rig, max_bytes=80, max_records=4)
    for n in range(100): assert output.append_safe(fase='instalacion', stream='stdout', texto_depurado='x'*40)
    with rig.store.lock('resource', rig.request['resource_uuid']):
        job = rig.store.read_job(rig.request['execution_id'])
        read = output.read_locked(job, after=0, limit_bytes=65536)
        assert [i['source_seq'] for i in read['items']] == [99,100]
        assert read['dropped_ranges'] == [{'from_seq': 1, 'through_seq': 98, 'bytes': 98*40}]
        output.ack_locked(job, through_seq=50)
        # Loss metadata describes the original range; clipping would invent bytes.
        assert output.read_locked(job, after=50, limit_bytes=65536)['dropped_ranges'] == read['dropped_ranges']


def test_fragment_and_serialized_read_budgets_are_real_utf8_bytes(rig):
    call(rig); output = spool(rig)
    for _ in range(10): output.append_safe(fase='instalacion', stream='stdout', texto_depurado='ñ'*4096)
    with pytest.raises(JobError): output.append_safe(fase='instalacion', stream='stdout', texto_depurado='ñ'*4097)
    with pytest.raises(JobError): output.append_safe(fase='instalacion', stream='stdout', texto_depurado='\x1b[31mraw')
    with rig.store.lock('resource', rig.request['resource_uuid']):
        read = output.read_locked(rig.store.read_job(rig.request['execution_id']), after=0, limit_bytes=65536)
        assert len(canonical(read['items'])) <= 65536 and len(read['items']) < 10


def test_physical_write_failure_does_not_block_or_reuse_published_sequence(rig, monkeypatch):
    call(rig); output = spool(rig)
    assert output.append_safe(fase='instalacion', stream='stdout', texto_depurado='Primero')
    original = output._connect
    def full(*args, **kwargs): raise sqlite3.OperationalError('database or disk is full')
    monkeypatch.setattr(output, '_connect', full)
    for _ in range(5): assert not output.append_safe(fase='instalacion', stream='stdout', texto_depurado='Mensaje no confirmado')
    monkeypatch.setattr(output, '_connect', original)
    assert output.append_safe(fase='instalacion', stream='stdout', texto_depurado='Continuación')
    with rig.store.lock('resource', rig.request['resource_uuid']):
        read = output.read_locked(rig.store.read_job(rig.request['execution_id']), after=0, limit_bytes=65536)
    assert [i['source_seq'] for i in read['items']] == [1,2,3]
    assert '5 mensajes' in read['items'][1]['texto_depurado']
    assert read['items'][-1]['texto_depurado'] == 'Continuación'


def test_reader_without_writer_does_not_create_console_data(rig):
    call(rig); output = spool(rig)
    before = sorted(p.name for p in rig.path.iterdir())
    with rig.store.lock('resource', rig.request['resource_uuid']):
        job = rig.store.read_job(rig.request['execution_id'])
        assert output.read_locked(job, after=0, limit_bytes=65536) == {'items': [], 'dropped_ranges': []}
    assert sorted(p.name for p in rig.path.iterdir()) == before


def test_supervisor_correlates_read_ack_and_keeps_tombstone_after_text_is_gone(rig):
    output = spool(rig)
    rig.supervisor.spool_factory = lambda execution_id: output
    call(rig)
    for n in range(4): output.append_safe(fase='instalacion', stream='sistema', texto_depurado=f'Paso {n}')
    page = call(rig, 'read', after=0, limit_bytes=65536)
    assert page['last_source_seq'] == 4 and len(page['items']) == 4
    assert call(rig, 'ack', through_seq=4)['acknowledged_seq'] == 4
    assert call(rig, 'read', after=0, limit_bytes=65536)['items'] == []
    assert call(rig)['execution_id'] == rig.request['execution_id']
    assert len(rig.service.starts) == 1


def test_ack_securely_deletes_text_and_refuses_symlinked_database(rig, tmp_path):
    call(rig); output = spool(rig)
    marker = 'safe-marker-for-ack-retirement-011'
    output.append_safe(fase='instalacion', stream='sistema', texto_depurado=marker)
    path = rig.path / output.name
    assert marker.encode() in path.read_bytes()
    with rig.store.lock('resource', rig.request['resource_uuid']):
        output.ack_locked(rig.store.read_job(rig.request['execution_id']), through_seq=1)
    assert marker.encode() not in path.read_bytes()
    target = tmp_path / 'unrelated'; target.write_text('unchanged')
    path.unlink(); path.symlink_to(target)
    with pytest.raises(JobError):
        with rig.store.lock('resource', rig.request['resource_uuid']):
            output.read_locked(rig.store.read_job(rig.request['execution_id']), after=0, limit_bytes=65536)
    assert target.read_text() == 'unchanged'
