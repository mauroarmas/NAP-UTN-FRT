#!/bin/bash
# EN LA PC DEL OPERADOR. SÓLO LECTURA: lista las tablas nftables de aislamiento (bridge nap011_*)
# y las contrasta con los LXC del nodo. YA NO BORRA NADA.
#
# Histórico: este script borraba por prefijo de hostname las tablas "huérfanas" que dejaba la baja
# de un servicio. Esa heurística no verifica identidad, recibo ni hash de las reglas: un invitado
# renombrado, o el gate (nap011-final-*), puede no coincidir con el prefijo. Desde el motor
# 0510c1a la baja OCI ejecuta la acción cerrada `cleanup`, que exige VMID ausente en todo el
# clúster, identidad privada y recibo exacto de las reglas, y recién entonces libera la
# dirección. Eso reemplaza este paso en el recorrido habitual.
#
# Residuos históricos (tablas de bajas anteriores al motor actual): NO se retiran con este script.
# Se reconcilian con la acción `cleanup` del runner usando la identidad y el recibo de cada
# recurso, o a mano y de a una tabla tras comprobar ausencia del VMID, el recibo y el hash.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
[ $# -eq 0 ] || { echo "este script ya no acepta argumentos (no elimina nada); ver la cabecera" >&2; exit 2; }
ssh -o ControlPath=${NAP_SSH_CTL:-/tmp/nap-lab-ssh-%h} -o SendEnv=-LC_* root@$NODE_IP 'bash -s' <<'REMOTE'
echo "contenedores del nodo:"; pct list
echo; echo "tablas bridge nap011_* presentes (sólo informativo):"
nft -j list tables | python3 -c "
import sys, json
for x in json.load(sys.stdin)['nftables']:
    t = x.get('table')
    if t and t['name'].startswith('nap011_'): print(' ', t['family'], t['name'])
" | sort
echo; echo "recibos de aislamiento: $(ls /var/lib/nap-application-isolation 2>/dev/null | wc -l) archivos"
REMOTE
