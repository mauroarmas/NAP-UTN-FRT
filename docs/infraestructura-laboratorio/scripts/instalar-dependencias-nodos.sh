#!/bin/bash
# EN LA PC DEL OPERADOR. Instala en cada nodo Proxmox las dependencias del runner/paquete 011:
#   python3-jsonschema, python3-cryptography, openssl, nftables
# (sudo, SSH, systemd, pct y pvesh ya vienen con Proxmox o con preparar-nodo.sh).
#
# Sin APPLY=1 solo informa qué falta; no instala nada.
#   bash instalar-dependencias-nodos.sh            # consulta
#   APPLY=1 bash instalar-dependencias-nodos.sh    # instala lo que falte
#
# Pide la contraseña de root una vez por nodo: correrlo en una terminal real (no con "!").
# Variables: NODES, APPLY.
set -u
NODES=${NODES:-"192.168.100.90 192.168.100.91 192.168.100.92 192.168.100.93"}
APPLY=${APPLY:-0}
CTL=/tmp/nap-deps-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=120"

for node in $NODES; do
  host=root@$node
  echo "=== $node"
  ssh $SSH_OPTS "$host" "APPLY=$APPLY bash -s" <<'REMOTE' || { echo "FALLO en $node; me detengo."; exit 1; }
export LC_ALL=C DEBIAN_FRONTEND=noninteractive
PKGS="python3-jsonschema python3-cryptography openssl nftables"
missing=""
for p in $PKGS; do
  if dpkg -s "$p" >/dev/null 2>&1; then echo "  ya instalado: $p"; else echo "  FALTA:        $p"; missing="$missing $p"; fi
done
echo "  nftables.service: enabled=$(systemctl is-enabled nftables 2>&1 | head -1) active=$(systemctl is-active nftables 2>&1 | head -1)"
echo "  reglas nft actuales: $(nft list ruleset 2>/dev/null | wc -l) líneas"
if [ -z "$missing" ]; then echo "  nada para instalar"; exit 0; fi
if [ "$APPLY" != 1 ]; then echo "  (consulta) para instalar:$missing"; exit 0; fi
apt-get -o Acquire::Retries=0 install -y --no-install-recommends $missing </dev/null || exit 1
echo "--- después:"
python3 -c "import jsonschema, cryptography; print('  imports ok: jsonschema', jsonschema.__version__, '| cryptography', cryptography.__version__)" || exit 1
echo "  nftables.service: enabled=$(systemctl is-enabled nftables 2>&1 | head -1) active=$(systemctl is-active nftables 2>&1 | head -1)"
echo "  reglas nft actuales: $(nft list ruleset 2>/dev/null | wc -l) líneas"
REMOTE
  ssh -o ControlPath=$CTL -O exit "$host" 2>/dev/null
done
