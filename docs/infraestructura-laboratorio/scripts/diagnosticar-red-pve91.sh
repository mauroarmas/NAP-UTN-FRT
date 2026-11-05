#!/bin/bash
# EN LA PC DEL OPERADOR. Sólo lectura. Diagnostica por qué un LXC de aplicación de pve91 no
# resuelve nombres: prueba DNS/TCP/ICMP desde el invitado y lista las tablas nftables de
# aislamiento del nodo (con sus contadores). No modifica reglas ni el invitado.
# Uso: diagnosticar-red-pve91.sh [VMID]   (por defecto 101)
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
VMID=${1:-101}
ssh -o SendEnv=-LC_* root@$NODE_IP "VMID=$VMID bash -s" <<'REMOTE'
echo "=== pruebas desde el invitado $VMID"
pct exec $VMID -- python3 - <<'PY'
import socket, struct, random
def consulta(server, nombre, tcp=False):
    q = struct.pack('>HHHHHH', random.randrange(65536), 0x0100, 1, 0, 0, 0)
    q += b''.join(bytes([len(p)]) + p.encode() for p in nombre.split('.')) + b'\x00' + struct.pack('>HH', 1, 1)
    try:
        if tcp:
            s = socket.create_connection((server, 53), timeout=4); s.sendall(struct.pack('>H', len(q)) + q); r = s.recv(512)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(4); s.sendto(q, (server, 53)); r = s.recv(512)
        return 'responde (%d bytes, rcode=%d)' % (len(r), r[3 + (2 if tcp else 0)] & 15)
    except Exception as e:
        return 'FALLA: %s' % e
for server in ('192.168.100.1', '8.8.8.8'):
    for tcp in (False, True):
        print('DNS %-14s %s -> %s' % (server, 'tcp' if tcp else 'udp', consulta(server, 'archive.ubuntu.com', tcp)))
for host, port in (('192.168.100.1', 53), ('185.125.190.82', 80), ('91.189.91.83', 80)):
    try: socket.create_connection((host, port), timeout=4).close(); print('TCP %s:%d -> conecta' % (host, port))
    except Exception as e: print('TCP %s:%d -> FALLA: %s' % (host, port, e))
PY
echo; echo "=== tablas nftables del nodo"
nft list tables 2>&1
for t in $(nft -j list tables 2>/dev/null | python3 -c "import sys,json;print(' '.join(x['table']['family']+':'+x['table']['name'] for x in json.load(sys.stdin)['nftables'] if 'table' in x and x['table']['name'].startswith('nap011_')))"); do
  fam=${t%%:*}; name=${t#*:}
  echo; echo "--- $fam $name"; nft list table $fam $name 2>&1 | head -60
done
REMOTE
