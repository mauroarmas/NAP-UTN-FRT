#!/bin/bash
# EN LA PC DEL OPERADOR. Sondeo TCP de salida desde DENTRO de una instancia (LXC) de un nodo.
# Uso: sondear-red.sh IP_NODO VMID etiqueta,host,puerto [etiqueta,host,puerto ...]
#   p. ej.: sondear-red.sh 192.168.100.91 102 instancia_B,192.168.100.105,3306 pve91_ssh,192.168.100.91,22 dns,192.168.100.1,53
# Usa el socket SSH compartido (NAP_SSH_CTL). Las etiquetas no deben llevar espacios ni paréntesis.
set -u
[ $# -ge 3 ] || { echo "uso: $0 IP_NODO VMID etiqueta,host,puerto ..." >&2; exit 2; }
NODO=$1; VMID=$2; shift 2
CTL=${NAP_SSH_CTL:-/tmp/nap-lab-ssh-%h}
AQUI=$(cd "$(dirname "$0")" && pwd)
scp -q -o ControlPath=$CTL "$AQUI/sondeo_red.py" root@$NODO:/root/sondeo_red.py || exit 1
ssh -o ControlPath=$CTL root@$NODO "pct push $VMID /root/sondeo_red.py /tmp/sondeo_red.py && pct exec $VMID -- python3 /tmp/sondeo_red.py $*; rm -f /root/sondeo_red.py" 2>&1 \
  | grep -v 'perl:\|LC_\|LANG\|are supported\|locale'
