import hashlib
import json
import os

import pytest

from infra.laboratorio import instalar_artefactos as installer


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'source'; source.mkdir(mode=0o700)
    targets = {'image':tmp_path/'cache', 'bundle':tmp_path/'recipes'}
    artifacts = []
    for product in installer.PRODUCTS:
        for kind in targets:
            data = f'fixture-{product}-{kind}'.encode()
            path = source/f'{product}-{kind}.tar.gz'
            path.write_bytes(data); path.chmod(0o644)
            artifacts.append({'product':product, 'kind':kind, 'sha256':hashlib.sha256(data).hexdigest(), 'size':len(data)})
    index = source/'artifact-index.json'
    index.write_text(json.dumps({'schema_version':1, 'artifacts':artifacts}))
    index.chmod(0o644)
    return source, targets, hashlib.sha256(index.read_bytes()).hexdigest()


@pytest.fixture(params=[0o022, 0o077])
def mask(request):
    previous = os.umask(request.param)
    try: yield
    finally: os.umask(previous)


def test_plan_does_not_create_destinations_and_install_is_idempotent(case,mask):
    source, targets, sha = case
    assert installer.install(source,sha,targets=targets)['estado'] == 'plan_sin_cambios'
    assert not any(p.exists() for p in targets.values())
    result = installer.install(source,sha,apply=True,targets=targets)
    assert len(result['archivos']) == 6 and not any(v['ya_existia'] for v in result['archivos'])
    before = {p:(p.stat().st_ino,p.read_bytes()) for d in targets.values() for p in d.iterdir()}
    result = installer.install(source,sha,apply=True,targets=targets)
    assert all(v['ya_existia'] for v in result['archivos'])
    assert before == {p:(p.stat().st_ino,p.read_bytes()) for p in before}
    assert all(p.stat().st_mode & 0o777 == 0o444 for p in before)


def test_wrong_digest_never_copies_anything(case):
    source, targets, sha = case
    (source/'linux-image.tar.gz').write_bytes(b'changed')
    with pytest.raises(ValueError): installer.install(source,sha,apply=True,targets=targets)
    assert not any(p.exists() for p in targets.values())


def test_existing_different_target_is_not_replaced(case):
    source, targets, sha = case
    targets['image'].mkdir(mode=0o755); target=targets['image']/'nap009-linux-1.0.0.tar.gz';target.write_bytes(b'existing');target.chmod(0o644)
    with pytest.raises(ValueError): installer.install(source,sha,apply=True,targets=targets)
    assert target.read_bytes() == b'existing' and not targets['bundle'].exists()


@pytest.mark.parametrize('kind', ['symlink','hardlink','writable'])
def test_untrusted_source_or_link_is_rejected(case,kind):
    source, targets, sha = case
    path = source/'linux-image.tar.gz'
    if kind == 'symlink':
        moved = source/'original';path.rename(moved);path.symlink_to(moved)
    elif kind == 'hardlink': os.link(path,source/'another-name')
    else: path.chmod(0o666)
    with pytest.raises((ValueError,OSError)): installer.install(source,sha,apply=True,targets=targets)
    assert not any(p.exists() for p in targets.values())


def test_mid_copy_failure_rolls_back_only_its_new_files(case,monkeypatch):
    source, targets, sha = case
    first=installer.inspect_plan(source,sha,targets=targets)[0]
    first['target'].parent.mkdir(mode=0o755); first['target'].write_bytes(first['source'].read_bytes());first['target'].chmod(0o644)
    inode = first['target'].stat().st_ino
    original = installer.copy_exclusive
    count = 0
    def failed(item):
        nonlocal count
        count += 1
        if count == 3: raise OSError('No space fixture')
        return original(item)
    monkeypatch.setattr(installer,'copy_exclusive',failed)
    with pytest.raises(OSError): installer.install(source,sha,apply=True,targets=targets)
    assert first['target'].stat().st_ino == inode
    assert list(targets['image'].iterdir()) == [first['target']]
    assert list(targets['bundle'].iterdir()) == []


def test_index_cannot_select_paths_or_unknown_products(case):
    source, targets, sha = case
    index=source/'artifact-index.json';value=json.loads(index.read_text())
    value['artifacts'][0]['destination']='/etc/passwd';index.write_text(json.dumps(value))
    sha=hashlib.sha256(index.read_bytes()).hexdigest()
    with pytest.raises(ValueError): installer.install(source,sha,apply=True,targets=targets)
    assert not any(p.exists() for p in targets.values())


def test_cli_refuses_apply_without_root_before_copying(case,monkeypatch):
    source, targets, sha = case
    monkeypatch.setattr(os,'geteuid',lambda:1000)
    monkeypatch.setattr('sys.argv',['installer','--source',str(source),'--index-sha256',sha,'--apply'])
    with pytest.raises(SystemExit) as exc: installer.main()
    assert exc.value.code == 2 and not any(p.exists() for p in targets.values())
