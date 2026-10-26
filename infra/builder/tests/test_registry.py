import json
import pytest
from app.utils.artifact_registry import read_private_json,entry_name,lookup,all_entries
from types import SimpleNamespace


def test_registry_reload_checks_permissions_digest_and_identity(tmp_path):
    key='drawio-trial:1.0.0';path=tmp_path/entry_name(key)
    settings=SimpleNamespace(service_artifacts={},artifact_registry_directory=str(tmp_path))
    assert lookup(settings,key) is None
    value={'key':key,'portal':{'registry_revision':'a'*64},'runner':{}}
    path.write_text(json.dumps(value));path.chmod(0o444)
    assert lookup(settings,key)==value['portal'] and all_entries(settings)[key]==value['portal']
    value['portal']['registry_revision']='b'*64;path.chmod(0o600);path.write_text(json.dumps(value));path.chmod(0o444)
    assert lookup(settings,key)['registry_revision']=='b'*64
    path.chmod(0o666)
    with pytest.raises(ValueError):lookup(settings,key)


def test_no_symlink_or_duplicate_fields(tmp_path):
    real=tmp_path/'real';real.write_text('{"key":1,"key":2}')
    with pytest.raises(ValueError):read_private_json(real)
    link=tmp_path/'link';link.symlink_to(real)
    with pytest.raises(ValueError):read_private_json(link)
