from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import tarfile
from uuid import uuid4

import pytest

from tests.service_helpers import manifest


def put(root, relative, content):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


@pytest.fixture
def rootfs(tmp_path):
    root = tmp_path / 'workspace' / 'rootfs'
    root.mkdir(parents=True)
    root.chmod(0o700)
    put(root, '.nap-build-workspace', 'nap-image-builder/1\n')
    put(root, 'etc/os-release', 'ID=ubuntu\nVERSION_ID="24.04"\n')
    put(root, 'etc/passwd', 'root:x:0:0:root:/root:/bin/bash\nwww-data:x:33:33:www:/var/www:/usr/sbin/nologin\nprevious:x:1000:1000::/home/previous:/bin/bash\nnobody:x:65534:65534::/nonexistent:/usr/sbin/nologin\n')
    put(root, 'etc/shadow', 'root:known-root-hash:1:0:99999:7:::\nprevious:private-password-hash:1:0:99999:7:::\nwww-data:*:1:0:99999:7:::\nnobody:*:1:0:99999:7:::\n')
    put(root, 'etc/group', 'root:x:0:\nwww-data:x:33:\nprevious:x:1000:\nnogroup:x:65534:\n')
    put(root, 'etc/gshadow', 'root:*::\nwww-data:*::\nprevious:secret::\nnogroup:*::\n')
    put(root, 'var/lib/dpkg/status', 'Package: base-files\nStatus: install ok installed\nArchitecture: amd64\nVersion: 13ubuntu10.3\n\n')
    for path in ['etc/ssh/ssh_host_ed25519_key', 'root/.ssh/authorized_keys', 'root/.bash_history',
        'home/previous/.pgpass', 'tmp/cookie', 'var/tmp/session', 'var/log/app.log',
        'etc/machine-id', 'var/lib/dbus/machine-id', 'var/lib/cloud/instance-data.json',
        'var/lib/postgresql/16/main/private-data', 'var/lib/mysql/private-db',
        'var/lib/nap/bootstrap.key', 'var/lib/nap/bootstrap.json',
        'etc/nap/postgresql/monitor.secret', 'etc/nap/postgresql/server.key',
        'etc/nap/bookstack/server.key',
        'var/cache/apt/archives/old_1.0_amd64.deb', 'var/lib/apt/lists/mirror_Packages',
        'var/www/bookstack/.env', 'var/www/bookstack/public/uploads/private-image.png',
        'var/www/bookstack/storage/uploads/private-attachment', 'var/www/bookstack/storage/logs/app.log']:
        put(root, path, 'previous-private-value')
    return root


@pytest.mark.parametrize('product', ['linux', 'postgresql', 'bookstack'])
def test_sanitize_removes_previous_identity_credentials_and_app_data(rootfs, product):
    from infra.services.sanitize import sanitize_rootfs
    sanitize_rootfs(rootfs, product)
    assert (rootfs / 'etc/machine-id').read_text() == ''
    assert 'previous' not in (rootfs / 'etc/passwd').read_text()
    assert 'nobody:' in (rootfs / 'etc/passwd').read_text()
    assert 'known-root-hash' not in (rootfs / 'etc/shadow').read_text()
    assert (rootfs / 'etc/shadow').read_text().startswith('root:!:')
    assert not (rootfs / 'etc/ssh/ssh_host_ed25519_key').exists()
    for path in rootfs.rglob('*'):
        if path.is_file() and not path.is_symlink():
            assert b'previous-private-value' not in path.read_bytes(), str(path)


def test_sanitize_rejects_unknown_root_and_symlinked_parents_before_mutating(tmp_path, rootfs):
    from infra.services.sanitize import sanitize_rootfs, ImageError
    with pytest.raises(ImageError):
        sanitize_rootfs(Path('/'), 'linux')
    outside = tmp_path / 'outside'
    outside.mkdir()
    protected = put(outside, '.env', 'protected-host-value')
    # A malicious rootfs must not make cleanup follow a path into the host.
    import shutil
    shutil.rmtree(rootfs / 'var/www/bookstack')
    (rootfs / 'var/www/bookstack').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ImageError):
        sanitize_rootfs(rootfs, 'bookstack')
    assert protected.read_text() == 'protected-host-value'
    assert 'known-root-hash' in (rootfs / 'etc/shadow').read_text()


@pytest.mark.parametrize('name,link', [('../escape', None), ('/absolute', None), ('etc/escape', '../../outside'), ('dev/unsafe', 'device')])
def test_unpack_rejects_escaping_entries_and_devices(tmp_path, name, link):
    from infra.services.build_image import safe_extract, ImageError
    archive = tmp_path / 'unsafe.tar'
    with tarfile.open(archive, 'w') as handle:
        item = tarfile.TarInfo(name)
        if link == 'device':
            item.type = tarfile.CHRTYPE
        elif link:
            item.type = tarfile.SYMTYPE; item.linkname = link
        else:
            item.size = 4
        handle.addfile(item, None if link else io.BytesIO(b'data'))
    destination = tmp_path / 'build-root'
    with pytest.raises(ImageError):
        safe_extract(archive, destination, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    assert not (tmp_path / 'outside').exists() and not (tmp_path / 'escape').exists()


def test_archive_is_reproducible_and_digest_covers_actual_content(rootfs, tmp_path):
    from infra.services.build_image import archive_rootfs
    from infra.services.sanitize import sanitize_rootfs
    sanitize_rootfs(rootfs, 'linux')
    first, second = tmp_path / 'first.tar.gz', tmp_path / 'second.tar.gz'
    digest = archive_rootfs(rootfs, first, source_date_epoch=1700000000)
    assert archive_rootfs(rootfs, second, source_date_epoch=1700000000) == digest
    assert first.read_bytes() == second.read_bytes()
    assert digest == hashlib.sha256(first.read_bytes()).hexdigest()
    with tarfile.open(first) as archive:
        assert '.nap-build-workspace' not in archive.getnames()
        assert all(item.mtime == 1700000000 for item in archive.getmembers())


def test_package_inventory_rejects_wrong_os_architecture_and_unpinned_versions(rootfs):
    from infra.services.build_image import inspect_rootfs, ImageError
    value = inspect_rootfs(rootfs)
    assert value == [{'name': 'base-files', 'version': '13ubuntu10.3', 'architecture': 'amd64'}]
    put(rootfs, 'var/lib/dpkg/status', 'Package: base-files\nStatus: install ok installed\nArchitecture: arm64\nVersion: latest\n\n')
    with pytest.raises(ImageError):
        inspect_rootfs(rootfs)
    put(rootfs, 'etc/os-release', 'ID=debian\nVERSION_ID="12"\n')
    with pytest.raises(ImageError):
        inspect_rootfs(rootfs)


def test_package_cache_copies_regular_files_without_touching_host_or_following_links(rootfs, tmp_path):
    from infra.services.build_image import stage_package_cache, ImageError
    cache = tmp_path / 'cache'
    cache.mkdir()
    package = cache / 'example_1.0_amd64.deb'
    package.write_bytes(b'fixture-cache-not-a-valid-package')
    stage_package_cache(rootfs, cache)
    assert (rootfs / 'var/cache/apt/archives' / package.name).read_bytes() == package.read_bytes()
    outside = tmp_path / 'private-host-fixture'
    outside.write_bytes(b'must-remain-private')
    unsafe = tmp_path / 'unsafe-cache'
    unsafe.mkdir()
    (unsafe / 'unsafe_1.0_amd64.deb').symlink_to(outside)
    with pytest.raises(ImageError):
        stage_package_cache(rootfs, unsafe)
    assert not (rootfs / 'var/cache/apt/archives/unsafe_1.0_amd64.deb').exists()
    assert outside.read_bytes() == b'must-remain-private'
    directory_link = tmp_path / 'cache-link'
    directory_link.symlink_to(cache, target_is_directory=True)
    with pytest.raises(ImageError):
        stage_package_cache(rootfs, directory_link)


def test_evidence_requires_two_distinct_measured_instances_and_all_product_checks():
    from infra.services.build_image import evidence_from_trials, finalize_manifest, ImageError
    value = manifest('bookstack')
    definition_id = str(uuid4())
    observed = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    trial = {'resource_uuid': str(uuid4()), 'image_sha256': value['image']['sha256'],
        'recipe_sha256': value['preparation']['bundle_sha256'], 'entorno': 'simulado', 'observado_at': observed,
        'checks': {key: True for key in value['validation']['checks']}}
    args = {'definition_id': definition_id, 'manifest': {k: v for k, v in value.items() if k != 'validation'},
        'operator': 'isolated-test-operator', 'reference': 'TEST-ONLY-BUILD', 'cluster_uuid': value['validation']['cluster_uuid'],
        'pve_versions': ['9.2.2'], 'environment': 'simulado'}
    with pytest.raises(ImageError):
        evidence_from_trials([trial], **args)
    with pytest.raises(ImageError):
        evidence_from_trials([trial, trial], **args)
    other = {**deepcopy(trial), 'resource_uuid': str(uuid4())}
    other['checks']['reader_permissions_and_revocation'] = False
    with pytest.raises(ImageError):
        evidence_from_trials([trial, other], **args)
    other['checks']['reader_permissions_and_revocation'] = True
    proof = evidence_from_trials([trial, other], **args)
    assert proof['resultado']['definicion_id'] == definition_id
    assert proof['entorno'] == 'simulado'
    draft = args['manifest']
    assert 'validation' not in draft
    from app.schemas.evidencia import canonical
    checksum = hashlib.sha256(canonical(proof).encode()).hexdigest()
    complete = finalize_manifest(draft, proof, reference=str(uuid4()), checksum=checksum)
    assert complete['validation']['evidence_sha256'] == checksum
    assert 'validation' not in draft
    with pytest.raises(ImageError):
        finalize_manifest(draft, proof, reference=str(uuid4()), checksum='f' * 64)


def test_builder_checks_base_lock_and_emits_only_a_draft_until_trials(rootfs, tmp_path):
    from infra.services.build_image import archive_rootfs, build_artifact, ImageError, file_sha256
    base = tmp_path / 'base.tar.gz'
    base_hash = archive_rootfs(rootfs, base, source_date_epoch=1700000000)
    value = manifest('linux')
    value.pop('validation')
    value['image']['volume_id'] = 'local:vztmpl/linux-built.tar.gz'
    value['image'].pop('sha256')
    value['preparation'].pop('bundle_sha256')
    plan = {'schema_version': 1, 'definition_id': str(uuid4()), 'base_sha256': base_hash,
        'source_date_epoch': 1700000000, 'package_lock': {'base-files': '13ubuntu10.3'}, 'manifest': value}
    calls = []
    def installer(root, plan):
        calls.append(plan['manifest']['product'])
        put(root, 'var/log/build.log', 'previous-private-value')
    def bundle(product, output):
        output.write_bytes(b'isolated-recipe-bundle')
    kwargs = {'installer': installer, 'bundle_factory': bundle, 'revision_verifier': lambda *args: None}
    result = build_artifact(plan, base, tmp_path / 'result', **kwargs)
    assert calls == ['linux'] and 'validation' not in result['manifest']
    assert result['manifest']['image']['sha256'] == file_sha256(result['image_path'])
    assert result['manifest']['preparation']['bundle_sha256'] == file_sha256(result['bundle_path'])
    assert not Path(result['image_path']).stat().st_mode & 0o022
    assert not Path(result['bundle_path']).stat().st_mode & 0o022
    with tarfile.open(result['image_path']) as image:
        assert 'var/log/build.log' not in image.getnames()
        assert b'previous-private-value' not in image.extractfile('etc/shadow').read()
    with pytest.raises(ImageError):
        build_artifact(plan, base, tmp_path / 'result', **kwargs)
    bad = {**plan, 'package_lock': {'base-files': '13ubuntu10.4'}}
    with pytest.raises(ImageError):
        build_artifact(bad, base, tmp_path / 'mismatch', **kwargs)


def test_build_resolver_is_private_and_restores_guest_link_even_on_failure(rootfs):
    from infra.services.build_image import resolver_for_build
    resolver = rootfs / 'etc/resolv.conf'
    resolver.symlink_to('../run/systemd/resolve/stub-resolv.conf')
    with pytest.raises(RuntimeError):
        with resolver_for_build(rootfs, contents=b'nameserver 192.0.2.53\n'):
            assert not resolver.is_symlink() and resolver.read_text() == 'nameserver 192.0.2.53\n'
            raise RuntimeError('simulated installer failure')
    assert resolver.is_symlink() and resolver.readlink().as_posix() == '../run/systemd/resolve/stub-resolv.conf'
