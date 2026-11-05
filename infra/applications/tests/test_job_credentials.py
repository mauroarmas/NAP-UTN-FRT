from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from infra.applications.job.credentials import CredentialChannel
from infra.applications.job.protocol import JobError, canonical


@pytest.fixture
def channel(tmp_path):
    source = tmp_path / 'source'
    copies = tmp_path / 'credentials'; copies.mkdir(mode=0o700)
    value = CredentialChannel(source_root=source, credentials_root=copies)
    yield value
    value.close()


def systemd_copy(channel, execution_id, monkeypatch):
    folder = channel.credentials_root / ('nap-application-' + execution_id + '.service')
    folder.mkdir(mode=0o700)
    target = folder / 'deployment'
    target.write_bytes((channel.path / ('credential.' + execution_id + '.json')).read_bytes())
    target.chmod(0o400)
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', str(folder))
    return target


def test_stage_is_private_replay_stable_and_load_unlinks_only_after_durable_claim(channel, monkeypatch):
    execution = str(uuid4()); values = {'APP_PASSWORD': 'fixture-private-credential-011'}
    channel.stage(execution, fingerprint='a'*64, secretos=values)
    path = channel.path / ('credential.'+execution+'.json')
    assert path.stat().st_mode & 0o777 == 0o600
    channel.stage(execution, fingerprint='a'*64, secretos=deepcopy(values))
    target = systemd_copy(channel, execution, monkeypatch)
    claims = []
    def mark_loaded():
        assert path.exists() and target.exists()
        claims.append(execution); return True
    assert channel.load_and_retire(execution, fingerprint='a'*64, mark_loaded=mark_loaded) == values
    assert claims == [execution] and not path.exists()
    assert channel.load_and_retire(execution, fingerprint='a'*64, mark_loaded=lambda: False) is None


def test_lost_claim_does_not_delete_credentials_or_reveal_values(channel, monkeypatch):
    execution = str(uuid4()); private = 'fixture-private-credential-011'
    channel.stage(execution, fingerprint='a'*64, secretos={'APP_PASSWORD': private})
    systemd_copy(channel, execution, monkeypatch)
    def rejected(): raise JobError('UNCONFIRMED')
    with pytest.raises(JobError) as caught:
        channel.load_and_retire(execution, fingerprint='a'*64, mark_loaded=rejected)
    assert private not in str(caught.value)
    assert (channel.path / ('credential.'+execution+'.json')).exists()


def test_conflicting_fingerprint_values_or_unknown_credential_directory_fail_closed(channel, monkeypatch):
    execution = str(uuid4()); values = {'APP_PASSWORD': 'fixture-private-credential-011'}
    channel.stage(execution, fingerprint='a'*64, secretos=values)
    with pytest.raises(JobError, match='EXECUTION_CONFLICT'):
        channel.stage(execution, fingerprint='b'*64, secretos=values)
    with pytest.raises(JobError, match='EXECUTION_CONFLICT'):
        channel.stage(execution, fingerprint='a'*64, secretos={'APP_PASSWORD': 'other-private-value'})
    target = systemd_copy(channel, execution, monkeypatch)
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', str(target.parent.parent))
    with pytest.raises(JobError): channel.load_and_retire(execution, fingerprint='a'*64, mark_loaded=lambda: True)
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', str(target.parent))
    with pytest.raises(JobError): channel.load_and_retire(execution, fingerprint='b'*64, mark_loaded=lambda: True)


def test_symlinked_systemd_copy_and_source_cannot_be_removed(channel, monkeypatch, tmp_path):
    execution = str(uuid4()); values = {'APP_PASSWORD': 'fixture-private-credential-011'}
    channel.stage(execution, fingerprint='a'*64, secretos=values)
    target = systemd_copy(channel, execution, monkeypatch)
    original = target.read_bytes(); target.unlink()
    other = tmp_path / 'other'; other.write_bytes(original); other.chmod(0o600)
    target.symlink_to(other)
    with pytest.raises(JobError): channel.load_and_retire(execution, fingerprint='a'*64, mark_loaded=lambda: True)
    source = channel.path / ('credential.'+execution+'.json')
    source.unlink(); source.symlink_to(other)
    with pytest.raises(JobError): channel.discard(execution, fingerprint='a'*64)
    assert other.read_bytes() == original
