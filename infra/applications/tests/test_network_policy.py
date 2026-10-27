from copy import deepcopy
from uuid import uuid4

import pytest

from infra.applications.job.network import compile_policy, table_name
from infra.applications.job.protocol import JobError
from infra.applications.tests.test_node_adapter import native
from infra.applications.tests.test_job_supervisor import rig


@pytest.fixture
def policy():
    return {'resource_uuid': str(uuid4()), 'vmid': 900011, 'bridge': 'vmbr0',
        'address': '172.16.36.81', 'mac_address': '02:11:22:33:44:55',
        'client_cidrs': ['172.16.36.1/32'], 'service_port': 8443,
        'management_addresses': ['172.16.36.100'], 'peer_cidrs': ['172.16.36.0/24'],
        'endpoints': [{'address':'172.16.36.2','transport':'udp','port':53},
                      {'address':'172.16.36.1','transport':'tcp','port':5443}]}


def test_bridge_policy_bounds_connections_before_established_and_only_own_veth(policy):
    text = compile_policy(policy).decode()
    table = table_name(policy)
    assert text.startswith('create table bridge '+table)
    assert text.count('create table ') == 1
    assert all(word not in text for word in ('flush ', 'delete ', 'masquerade', 'dnat', 'log '))
    assert 'iifname "veth900011i0" jump outgoing' in text
    assert 'oifname "veth900011i0" jump incoming' in text
    assert 'hook input' in text and 'hook output' in text and 'hook forward' in text
    assert text.index('ip daddr 172.16.36.100 counter drop') < text.index('ct state established,related accept')
    assert text.index('ip daddr 172.16.36.1 tcp dport 5443 accept') < text.index('ip daddr 172.16.36.0/24 counter drop')
    assert text.index('ether type != ip drop') < text.index('ct state established,related accept')
    assert 'ip saddr 172.16.36.1/32 tcp dport 8443 accept' in text
    assert 'ether type arp arp saddr ether != 02:11:22:33:44:55 drop' in text
    other = deepcopy(policy); other['resource_uuid'] = str(uuid4())
    assert table_name(other) != table


@pytest.mark.parametrize('key,value', [
    ('vmid', True), ('bridge','vmbr0"; flush ruleset'), ('resource_uuid','../x'),
    ('address','::1'), ('mac_address','ff:ff:ff:ff:ff:ff'), ('service_port',True),
    ('client_cidrs',['0.0.0.0/0']), ('peer_cidrs',['172.16.37.0/24']),
    ('endpoints',[{'address':'172.16.36.100','transport':'tcp','port':8006}]),
    ('endpoints',[{'address':'172.16.36.81','transport':'tcp','port':443}]),
])
def test_invalid_policy_fails_before_any_command(policy, key, value):
    policy[key] = value
    with pytest.raises(JobError): compile_policy(policy)


def setup_node(native, policy):
    node, values, identity = native
    policy.update(resource_uuid=identity['resource_uuid'], vmid=identity['vmid'])
    values['config']['net0'] = 'name=eth0,bridge=vmbr0,hwaddr=02:11:22:33:44:55,ip=172.16.36.81/24,gw=172.16.36.2,firewall=1'
    run = node.run_command
    effects = []
    def command(argv, **kwargs):
        if argv[0] == '/usr/sbin/nft':
            assert argv == ['/usr/sbin/nft','-f','-']
            effects.append(kwargs['input'])
            if len(effects) > 1: raise RuntimeError('table exists')
            return b''
        return run(argv, **kwargs)
    node.run_command = command
    return node, values, identity, effects


def test_native_effect_requires_owned_stopped_matching_network_and_never_replaces(native, policy):
    node, values, identity, effects = setup_node(native, policy)
    assert node.install_isolation(identity, policy)
    assert effects == [compile_policy(policy)]
    with pytest.raises(JobError): node.install_isolation(identity, policy)
    assert len(effects) == 2
    assert all(b'flush ' not in effect and b'delete ' not in effect for effect in effects)
    assert not any(argv[0] == '/usr/sbin/pct' for argv in values['calls'])


@pytest.mark.parametrize('bad', ['running','foreign','wrong-ip','extra-nic','duplicate-key'])
def test_network_mismatch_never_changes_host(native, policy, bad):
    node, values, identity, effects = setup_node(native, policy)
    if bad == 'running': values['status'] = 'running'
    if bad == 'foreign': values['resource']['pool'] = 'foreign'
    if bad == 'wrong-ip': values['config']['net0'] = values['config']['net0'].replace('.81/', '.82/')
    if bad == 'extra-nic': values['config']['net1'] = 'name=eth1,bridge=vmbr0,ip=dhcp'
    if bad == 'duplicate-key': values['config']['net0'] += ',ip=172.16.36.81/24'
    with pytest.raises(JobError): node.install_isolation(identity, policy)
    assert not effects


@pytest.mark.integration
@pytest.mark.skipif(__import__('os').environ.get('NAP_INFRA_INTEGRATION') != '1', reason='explicit local namespace gate')
def test_real_nft_batch_is_atomic_and_exclusive_in_disposable_network_namespace(policy):
    """Actual Linux nft parser/kernel, never the host network or Proxmox."""
    import subprocess
    import sys
    script = '''
import json, subprocess, sys, socket, struct, time
batch = sys.stdin.buffer.read()
def nft(args, data=None):
    return subprocess.run(['/usr/sbin/nft', *args], input=data, capture_output=True, timeout=5)
assert nft(['add','table','bridge','unrelated']).returncode == 0
first = nft(['-f','-'], batch)
assert first.returncode == 0, first.stderr.decode()
before = nft(['-j','list','ruleset'])
assert before.returncode == 0
second = nft(['-f','-'], batch)
assert second.returncode != 0
assert nft(['-j','list','ruleset']).stdout == before.stdout
result = json.loads(before.stdout)
assert len([v for v in result['nftables'] if 'table' in v]) == 2
# Exercise actual bridge hooks in this namespace, using private veth pairs.
# No addresses/routes, services, host interfaces or host firewall are changed.
def ip(*args):
    subprocess.run(['/usr/sbin/ip', *args], check=True, capture_output=True, timeout=5)
ip('link','add','br011','type','bridge')
ip('link','add','veth900011i0','type','veth','peer','name','guest011')
ip('link','add','uplink011','type','veth','peer','name','client011')
ip('link','set','guest011','address','02:11:22:33:44:55')
for name in ('veth900011i0','uplink011'):
    ip('link','set',name,'master','br011')
for name in ('br011','veth900011i0','uplink011','guest011','client011'):
    ip('link','set',name,'up')
source = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
target = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
source.bind(('guest011',0)); target.bind(('client011',0))
target.settimeout(.15)
mac = bytes.fromhex('021122334455'); dst = target.getsockname()[4]
def checksum(data):
    parts = struct.unpack('!10H',data)
    total = sum(parts); total = (total & 65535) + (total >> 16)
    return (~((total & 65535) + (total >> 16))) & 65535
def packet(destination, port, *, sender='172.16.36.81', spoof=False, ipv6=False):
    if ipv6:
        header = struct.pack('!IHBB16s16s',6 << 28,4,59,64,
            socket.inet_pton(socket.AF_INET6,'fd00::81'),socket.inet_pton(socket.AF_INET6,'fd00::2'))
        return dst+mac+struct.pack('!H',0x86dd)+header+b'NAP!'
    udp = struct.pack('!HHHH',30001,port,12,0)+b'NAP!'
    header = struct.pack('!BBHHHBBH4s4s',0x45,0,32,7,0,64,17,0,socket.inet_aton(sender),socket.inet_aton(destination))
    header = header[:10]+struct.pack('!H',checksum(header))+header[12:]
    return dst+(bytes.fromhex('021122334456') if spoof else mac)+struct.pack('!H',0x800)+header+udp
def received(frame):
    target.setblocking(False)
    try:
        while True: target.recv(2048)
    except BlockingIOError: pass
    target.settimeout(.15)
    source.send(frame)
    until = time.monotonic()+.2
    while time.monotonic() < until:
        try:
            if target.recv(2048) == frame: return True
        except socket.timeout: pass
    return False
# Exact DNS exception works; node, peer, metadata, MAC/IP spoof and IPv6 don't.
assert received(packet('172.16.36.2',53))
for frame in [packet('172.16.36.100',8006), packet('172.16.36.63',80),
              packet('169.254.169.254',80), packet('172.16.36.2',53,spoof=True),
              packet('172.16.36.2',53,sender='172.16.36.82'),
              packet('172.16.36.2',53,ipv6=True)]:
    assert not received(frame)
source.close(); target.close()
print('isolated nft batch: installed; replay rejected; unrelated table preserved')
'''
    result = subprocess.run(['/usr/bin/unshare','--user','--map-root-user','--net',sys.executable,'-c',script],
        input=compile_policy(policy), capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode()
    assert b'isolated nft batch: installed' in result.stdout
