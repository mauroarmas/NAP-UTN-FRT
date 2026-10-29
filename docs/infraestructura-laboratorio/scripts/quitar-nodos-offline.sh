#!/bin/bash
# EN LA PC DEL OPERADOR. Saca del cluster Proxmox los nodos que ya no se usan (pve92, pve93).
#
# Por qué: el portal sólo confirma que un contenedor "ya no existe" si TODOS los nodos del
# cluster están online (identidad_infra_service.observar). Con nodos apagados las bajas quedan
# "inciertas" y la capacidad no se libera. Además quita la necesidad de 'pvecm expected 2'.
#
# IRREVERSIBLE: un nodo retirado no vuelve al cluster sin reinstalarlo. Comprobaciones previas:
#   - las VMs de VirtualBox de esos nodos están apagadas (si no, aborta);
#   - el nodo desde el que se ejecuta tiene quórum;
#   - esos nodos no alojan ningún contenedor ni VM según el cluster.
# Sin argumentos sólo comprueba y muestra el plan. Con --aplicar ejecuta pvecm delnode.
set -u
APLICAR=0; [ "${1:-}" = "--aplicar" ] && APLICAR=1
NODE_IP=${NODE_IP:-192.168.100.91}         # nodo que se queda y desde el que se ejecuta
QUITAR=${QUITAR:-"pve92=nap3 pve93=nap4"}  # nodo Proxmox=VM de VirtualBox
CTL=/tmp/nap-delnode-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=120 -o SendEnv=-LC_*"
die() { echo "ERROR: $*" >&2; exit 1; }

for item in $QUITAR; do
  vm=${item#*=}
  state=$(VBoxManage showvminfo "$vm" --machinereadable 2>/dev/null | sed -n 's/^VMState="\(.*\)"/\1/p')
  [ "$state" = "poweroff" ] || die "la VM $vm no está apagada (estado: ${state:-desconocido}); apagala antes"
  echo "VM $vm apagada: OK"
done

ssh $SSH_OPTS root@$NODE_IP 'bash -s' -- "$APLICAR" $QUITAR <<'REMOTE' || die "falló en el nodo; no sigo."
aplicar=$1; shift
pvecm status | grep -q '^Quorate:[[:space:]]*Yes' || { echo "el nodo no tiene quórum" >&2; exit 1; }
echo "quórum: OK"
resources=$(pvesh get /cluster/resources --type vm --output-format json)
for item in "$@"; do
  node=${item%%=*}
  pvesh get /nodes --output-format json | grep -q "\"node\":\"$node\"" || { echo "$node no figura en el cluster; lo salteo"; continue; }
  n=$(printf '%s' "$resources" | python3 -c "import sys,json;print(sum(1 for r in json.load(sys.stdin) if r.get('node')=='$node'))")
  [ "$n" = "0" ] || { echo "$node aloja $n invitado(s); aborto" >&2; exit 1; }
  echo "$node: sin invitados, se puede retirar"
  if [ "$aplicar" = 1 ]; then pvecm delnode "$node" && echo "$node retirado"; fi
done
echo "--- estado final"
pvecm status | grep -i -E 'quorate|expected|total votes'
REMOTE
ssh -o ControlPath=$CTL -O exit root@$NODE_IP 2>/dev/null
[ $APLICAR -eq 1 ] || echo "(simulación: usá --aplicar para retirar los nodos)"
