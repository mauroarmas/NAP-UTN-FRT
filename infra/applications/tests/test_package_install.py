from hashlib import sha256
from pathlib import Path
import os

import pytest

from infra.applications.install import build_files, install_files, PackageError


@pytest.fixture(autouse=True)
def private_test_umask():
    previous = os.umask(0o077)
    try: yield
    finally: os.umask(previous)


def test_package_has_only_reviewed_code_and_never_contains_private_controller_data(tmp_path):
    files = build_files(Path(__file__).resolve().parents[3])
    assert '/opt/nap/applications/job/worker.py' in files
    assert '/opt/nap/applications/profiles/profile_contract.py' in files
    assert '/etc/tmpfiles.d/nap-application-jobs.conf' in files
    assert all(not any(part in name for part in ('.env', 'accounts.json', 'registry-auth', 'tls.key')) for name in files)


def test_install_is_additive_idempotent_and_prepares_reboot_directory_rule(tmp_path):
    root = tmp_path / 'node'; root.mkdir()
    files = {'/opt/nap/applications/job/worker.py': (b'# reviewed fixture\n', 0o444),
             '/etc/tmpfiles.d/nap-application-jobs.conf': (b'd /run/nap-application-jobs 0700 root root -\n', 0o644)}
    plan = install_files(files, root=root, apply=False)
    assert plan['changed_files'] == 2 and not (root/'opt').exists()
    first = install_files(files, root=root, apply=True)
    assert first['state'] == 'installed' and (root/'var/lib/nap-application-jobs').stat().st_mode & 0o777 == 0o700
    assert install_files(files, root=root, apply=True)['changed_files'] == 0


def test_unknown_or_linked_destination_is_rejected_before_modifying_any_file(tmp_path):
    root = tmp_path/'node'; folder = root/'opt/nap/applications/job'; folder.mkdir(parents=True)
    old = folder/'worker.py'; old.write_bytes(b'unknown local modification')
    files = {'/opt/nap/applications/job/protocol.py': (b'new source', 0o444),
             '/opt/nap/applications/job/worker.py': (b'updated worker', 0o444)}
    with pytest.raises(PackageError): install_files(files, root=root, apply=True)
    assert old.read_bytes() == b'unknown local modification'
    assert not (folder/'protocol.py').exists()


def test_reviewed_previous_version_gets_backed_up_and_partial_failure_rolls_back(tmp_path, monkeypatch):
    root = tmp_path/'node'; folder = root/'opt/nap/runner'; folder.mkdir(parents=True)
    old = folder/'node_executor.py'; old.write_bytes(b'known previous source'); old.chmod(0o444)
    files = {'/opt/nap/runner/node_executor.py': (b'new source', 0o444),
             '/opt/nap/runner/nap_guest_runner.py': (b'new wrapper', 0o444)}
    previous = {'/opt/nap/runner/node_executor.py': sha256(old.read_bytes()).hexdigest()}
    from infra.applications import install
    original = install.atomic_write
    def fail(path, content, mode):
        if path.name == 'nap_guest_runner.py': raise OSError('fixture disk full')
        return original(path, content, mode)
    monkeypatch.setattr(install, 'atomic_write', fail)
    with pytest.raises(PackageError): install_files(files, root=root, apply=True, previous=previous)
    assert old.read_bytes() == b'known previous source'
    assert not (folder/'nap_guest_runner.py').exists()


def test_active_jobs_prevent_overwriting_loaded_runtime_code(tmp_path):
    root = tmp_path/'node'; state = root/'var/lib/nap-application-jobs'; state.mkdir(parents=True, mode=0o700)
    from uuid import uuid4
    (state/('job.'+str(uuid4())+'.json')).write_text('{"estado":"ejecutando"}')
    with pytest.raises(PackageError):
        install_files({'/opt/nap/applications/job/worker.py': (b'new', 0o444)}, root=root, apply=True)


def test_admission_lock_prevents_upgrade_racing_with_a_new_job(tmp_path):
    import fcntl
    root=tmp_path/'node'; state=root/'var/lib/nap-application-jobs';state.mkdir(parents=True,mode=0o700)
    descriptor=os.open(state/'lock.node',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(PackageError,match='PACKAGE_ADMISSION_BUSY'):
            install_files({'/opt/nap/applications/job/worker.py':(b'new',0o444)},root=root,apply=True)
        assert not (root/'opt').exists()
    finally:os.close(descriptor)


def test_terminal_word_in_corrupt_manifest_is_not_evidence_of_an_idle_runtime(tmp_path):
    from uuid import uuid4
    root=tmp_path/'node';state=root/'var/lib/nap-application-jobs';state.mkdir(parents=True,mode=0o700)
    (state/('job.'+str(uuid4())+'.json')).write_text('{"estado":"confirmado"}')
    with pytest.raises(PackageError,match='ACTIVE_OR_UNKNOWN_JOB'):
        install_files({'/opt/nap/applications/job/worker.py':(b'new',0o444)},root=root,apply=True)
