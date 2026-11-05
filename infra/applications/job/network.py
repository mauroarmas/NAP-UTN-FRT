"""Closed host-side bridge policy; never a guest command or an SSH argument.

Inputs must come from the institutional node configuration and the reserved
identity. This module does not resolve DNS, adopt existing nft tables, flush
other rules, start a guest or certify that a profile works on real Proxmox.
"""
from hashlib import sha256
import ipaddress
import re
from uuid import UUID

from .protocol import JobError, canonical


# Public installer downloads are limited to HTTP(S); private destinations need
# an explicit institutional endpoint. IPv6 and all other EtherTypes fail closed.
NON_PUBLIC = ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24',
    '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4')


def _address(value):
    parsed = ipaddress.IPv4Address(value)
    if type(value) is not str or str(parsed) != value or parsed.is_unspecified or parsed.is_multicast or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved:
        raise ValueError()
    return value


def validate_policy(value):
    """No free nft fragments, interface names, commands, or wildcard ports."""
    try:
        if type(value) is not dict or set(value) != {'resource_uuid', 'vmid', 'bridge', 'address', 'mac_address',
                'client_cidrs', 'service_port', 'management_addresses', 'peer_cidrs', 'endpoints'}: raise ValueError()
        if str(UUID(value['resource_uuid'])) != value['resource_uuid']: raise ValueError()
        if type(value['vmid']) is not int or not 100 <= value['vmid'] <= 999999999: raise ValueError()
        if type(value['bridge']) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', value['bridge']): raise ValueError()
        _address(value['address'])
        if type(value['mac_address']) is not str or not re.fullmatch(r'02(?::[0-9a-f]{2}){5}', value['mac_address']): raise ValueError()
        if type(value['service_port']) is not int or not 1 <= value['service_port'] <= 65535: raise ValueError()
        for key in ('client_cidrs', 'peer_cidrs', 'management_addresses', 'endpoints'):
            if type(value[key]) is not list or not 1 <= len(value[key]) <= 100: raise ValueError()
        for key in ('client_cidrs', 'peer_cidrs'):
            for item in value[key]:
                network = ipaddress.IPv4Network(item, strict=True)
                if type(item) is not str or str(network) != item or network.prefixlen == 0: raise ValueError()
            if len(set(value[key])) != len(value[key]): raise ValueError()
        for item in value['management_addresses']: _address(item)
        if value['address'] in value['management_addresses']: raise ValueError()
        if not any(ipaddress.IPv4Address(value['address']) in ipaddress.IPv4Network(n) for n in value['peer_cidrs']): raise ValueError()
        seen = set()
        for endpoint in value['endpoints']:
            if type(endpoint) is not dict or set(endpoint) != {'address', 'transport', 'port'}: raise ValueError()
            _address(endpoint['address'])
            if endpoint['address'] == value['address'] or endpoint['transport'] not in ('tcp', 'udp'): raise ValueError()
            if type(endpoint['port']) is not int or not 1 <= endpoint['port'] <= 65535: raise ValueError()
            # Infrastructure exceptions are narrow: DNS, HTTPS and OCI registry.
            if (endpoint['transport'], endpoint['port']) not in {('udp',53), ('tcp',53), ('tcp',443), ('tcp',5443)}: raise ValueError()
            key = (endpoint['address'], endpoint['transport'], endpoint['port'])
            if key in seen: raise ValueError()
            seen.add(key)
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        raise JobError('INVALID_REQUEST') from None


def table_name(value):
    validate_policy(value)
    return 'nap011_' + UUID(value['resource_uuid']).hex


def compile_policy(value):
    """One atomic, exclusive-create batch installed before the veth exists.

    iifname/oifname continue matching when the guest interface is created.
    Early EtherType/address checks apply even to established connections.
    """
    value = validate_policy(value)
    table = table_name(value)
    address, mac = value['address'], value['mac_address']
    digest = sha256(canonical(value)).hexdigest()
    outgoing = [f'ether saddr != {mac} drop',
        f'ether type arp arp saddr ether != {mac} drop',
        f'ether type arp arp saddr ip {address} accept',
        f'ether type arp arp saddr ip 0.0.0.0 arp daddr ip {address} accept',
        'ether type arp drop', 'ether type != ip drop', f'ip saddr != {address} drop', 'ct state invalid drop']
    for endpoint in value['endpoints']:
        outgoing.append(f"ip daddr {endpoint['address']} {endpoint['transport']} dport {endpoint['port']} accept")
    # Replies to authorized clients must work even on the same private subnet.
    # The original direction is still denied: clients are not an egress tunnel.
    for item in value['client_cidrs']:
        outgoing.append(f"ip daddr {item} tcp sport {value['service_port']} ct direction reply ct state established accept")
    for item in value['management_addresses'] + value['peer_cidrs'] + list(NON_PUBLIC):
        outgoing.append(f'ip daddr {item} counter drop')
    outgoing += ['ct state established,related accept', 'tcp dport { 80, 443 } accept', 'counter drop']
    incoming = ['ether type arp accept', 'ether type != ip drop', f'ip daddr != {address} drop',
        'ct state invalid drop', 'ct state established,related accept']
    for item in value['client_cidrs']:
        incoming.append(f"ip saddr {item} tcp dport {value['service_port']} accept")
    incoming.append('counter drop')
    lines = [f'create table bridge {table} {{ comment "nap011:{digest}"; }}']
    for name, rules in [('outgoing', outgoing), ('incoming', incoming)]:
        lines.append(f'add chain bridge {table} {name}')
        lines.extend(f'add rule bridge {table} {name} {rule}' for rule in rules)
    veth = f"veth{value['vmid']}i0"
    for name, hook, rules in [('forwarded', 'forward', [('iifname', 'outgoing'), ('oifname', 'incoming')]),
            ('to_host', 'input', [('iifname', 'outgoing')]), ('from_host', 'output', [('oifname', 'incoming')])]:
        lines.append(f'add chain bridge {table} {name} {{ type filter hook {hook} priority -300; policy accept; }}')
        lines.extend(f'add rule bridge {table} {name} {direction} "{veth}" jump {target}' for direction, target in rules)
    return ('\n'.join(lines)+'\n').encode('ascii')


class NetworkRegistry:
    """Institutional node data, independent of application/SSH inputs.

    Missing data means unavailable; no DHCP discovery, inferred subnet, or
    arbitrary route is used to complete it. Slots are matched by MAC AND IP.
    """
    def __init__(self, entries, *, cluster_uuid, node):
        from copy import deepcopy
        try:
            if type(entries) is not dict or len(entries) > 50 or len(canonical(entries)) > 1048576: raise ValueError()
            self.entries = deepcopy(entries)
            self.cluster_uuid, self.node = cluster_uuid, node
            seen = set()
            for name, value in self.entries.items():
                if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name): raise ValueError()
                if type(value) is not dict or set(value) != {'cluster_uuid','nodes','bridge','client_cidrs',
                        'management_addresses','peer_cidrs','endpoints','slots'}: raise ValueError()
                if (value['cluster_uuid'] != cluster_uuid or type(value['nodes']) is not list
                        or not 1 <= len(value['nodes']) <= 100 or node not in value['nodes']
                        or any(type(n) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}',n) for n in value['nodes'])): raise ValueError()
                if type(value['slots']) is not dict or not 1 <= len(value['slots']) <= 256: raise ValueError()
                for slot_id, slot in value['slots'].items():
                    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', slot_id): raise ValueError()
                    if type(slot) is not dict or set(slot) != {'host','address','mac_address'}: raise ValueError()
                    host = slot['host']
                    if type(host) is not str or len(host) > 253 or not host or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')): raise ValueError()
                    for key, item in slot.items():
                        if (key,item) in seen: raise ValueError()
                        seen.add((key,item))
                    validate_policy(self._policy(value, slot, resource_uuid='00000000-0000-0000-0000-000000000001', vmid=100, port=8443))
        except Exception: raise JobError('PROFILE_UNAVAILABLE') from None

    @staticmethod
    def _policy(value, slot, *, resource_uuid, vmid, port):
        return {key:value[key] for key in ('bridge','client_cidrs','management_addresses','peer_cidrs','endpoints')} | {
            'resource_uuid':resource_uuid,'vmid':vmid,'address':slot['address'],
            'mac_address':slot['mac_address'],'service_port':port}

    def for_guest(self, profile, identity, config, deployment):
        from copy import deepcopy
        try:
            value = self.entries[profile['network_profile_id']]
            if self.node not in value['nodes']: raise ValueError()
            parts = config['net0'].split(','); net = dict(p.split('=',1) for p in parts)
            if len(parts) != len(net) or net.get('bridge') != value['bridge']: raise ValueError()
            address = str(ipaddress.IPv4Interface(net['ip']).ip)
            matches = [v for v in value['slots'].values() if v['address'] == address and v['mac_address'] == net.get('hwaddr','').lower()]
            if len(matches) != 1: raise ValueError()
            port = 8443 if deployment['access']['tipo'] == 'web' else deployment['access']['puerto']
            policy = self._policy(value, matches[0], resource_uuid=identity['resource_uuid'], vmid=identity['vmid'], port=port)
            validate_policy(policy)
            return deepcopy(policy), deepcopy(matches[0])
        except Exception: raise JobError('PROFILE_UNAVAILABLE') from None
