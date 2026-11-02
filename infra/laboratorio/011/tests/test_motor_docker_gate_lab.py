"""Safety boundaries of the lab variant of the root gate (pve91 + truenas); no Proxmox effects."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def gate():
    path=Path(__file__).resolve().parents[1]/'validar_motor_docker_lab.py'
    spec=importlib.util.spec_from_file_location('nap011_final_gate_lab_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('bad',['pool','marker','privileged','mount','host-command'])
def test_cleanup_owner_guard_never_adopts_foreign_or_expanded_guest(gate,monkeypatch,bad):
    context={'request':{'resource_uuid':str(uuid4()),'cluster_uuid':str(uuid4()),'nonce':'a'*64,
        'configuracion_sha256':'b'*64,'node':gate.NODE},'profile':{'policy_bundle_sha256':'c'*64}}
    config={'description':json.dumps(gate.config_marker(context)),'unprivileged':1,'cores':2,'memory':1024,
        'rootfs':'truenas:900011/vm-900011-disk-0.raw,size=8G'}
    row={'vmid':900011,'type':'lxc','node':gate.NODE,'pool':gate.POOL}
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


def test_lab_constants_replace_the_original_environment(gate):
    assert (gate.NODE,gate.STORAGE,gate.SLOT_ADDRESS) == ('pve91','truenas','192.168.100.119')
    assert 'proxmox' not in Path(gate.__file__).read_text().split('POOL=',1)[1].replace('original fija proxmox','')


def _normalized(text,lab):
    """Cuerpo ejecutable sin el encabezado documental ni el bloque de constantes de entorno."""
    body=text.split("\nPOOL=",1)[1]
    if lab:
        for old,new in [("'/nodes/'+NODE+'/storage/'+STORAGE+'/content'","'/nodes/proxmox/storage/local-lvm/content'"),
            ("'/nodes/'+NODE+'/lxc/'","'/nodes/proxmox/lxc/'"),("[NODE]","['proxmox']"),
            ("'node':NODE","'node':'proxmox'"),("node=NODE","node='proxmox'"),("('node',NODE)","('node','proxmox')"),
            ("node=NODE;","node='proxmox';"),("SLOT_ADDRESS","'172.16.36.81'"),("STORAGE+':8'","'local-lvm:8'"),
            ("'--nameserver',NAMESERVER","'--nameserver','172.16.36.2'"),("gw='+GATEWAY+',","gw=172.16.36.2,"),
            ("re.escape(STORAGE)+r':(?:900011/)?vm-900011-disk-[0-9]+(?:\\.raw)?","r'local-lvm:vm-900011-disk-[0-9]+")]:
            body=body.replace(old,new)
    return body


def test_lab_variant_only_differs_from_original_in_environment_constants(gate):
    """Evita que la variante derive del gate original: mismas garantías, otro entorno."""
    here=Path(gate.__file__).read_text()
    original=(Path(gate.__file__).parent/'validar_motor_docker.py').read_text()
    assert _normalized(here,True)==_normalized(original,False)


def test_lab_variant_keeps_mariadb_secrets_and_runtime_cleanup(gate):
    text=Path(gate.__file__).read_text()
    for needle in ("data.get('application')=='mariadb'","mariadb_select_1","private_values","engine.cleanup(cleanup_request)","profile_revision"):
        assert needle in text
