"""Safety boundaries of the explicit root gate; no Proxmox effects."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def gate():
    path=Path(__file__).resolve().parents[1]/'validar_motor_docker.py'
    spec=importlib.util.spec_from_file_location('nap011_final_gate_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('bad',['pool','marker','privileged','mount','host-command'])
def test_cleanup_owner_guard_never_adopts_foreign_or_expanded_guest(gate,monkeypatch,bad):
    context={'request':{'resource_uuid':str(uuid4()),'cluster_uuid':str(uuid4()),'nonce':'a'*64,
        'configuracion_sha256':'b'*64,'node':'proxmox'},'profile':{'policy_bundle_sha256':'c'*64}}
    config={'description':json.dumps(gate.config_marker(context)),'unprivileged':1,'cores':2,'memory':1024,
        'rootfs':'local-lvm:vm-900011-disk-0,size=8G'}
    row={'vmid':900011,'type':'lxc','node':'proxmox','pool':gate.POOL}
    if bad=='pool':row['pool']='catedra-1'
    if bad=='marker':config['description']='{"nap":{}}'
    if bad=='privileged':config['unprivileged']=0
    if bad=='mount':config['mp0']='/shared,mp=/data'
    if bad=='host-command':config['hookscript']='local:snippets/other.sh'
    monkeypatch.setattr(gate,'pve',lambda path,**kwargs:[row] if path=='/cluster/resources' else config)
    with pytest.raises(ValueError):gate.owned(context)


def test_existing_vmid_prevents_initialization_before_assets_or_external_commands(gate,tmp_path,monkeypatch):
    monkeypatch.setattr(gate,'BASE',tmp_path)
    monkeypatch.setattr(gate,'pve',lambda *args,**kwargs:[{'vmid':900011}])
    monkeypatch.setattr(gate,'assets',lambda:pytest.fail('No runtime setup for a busy VMID'))
    with pytest.raises(ValueError,match='VMID_BUSY'):gate.initialize({})
