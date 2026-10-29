#!/bin/bash
# EN LA PC DEL OPERADOR. Elimina las tablas nftables de aislamiento (bridge nap011_*) cuyo
# contenedor YA NO EXISTE en el nodo.
#
# Por qué: la baja de un servicio desde el portal destruye el LXC pero deja su tabla de
# aislamiento. Las tablas enganchan por nombre de interfaz (iifname "veth<VMID>i0") y Proxmox
# reutiliza los VMID, así que la tabla vieja bloquea al contenedor nuevo que reciba ese VMID
# (síntoma: sin DNS ni salida, 'apt' no arranca, la fase 'entorno' falla con
# DEPENDENCY_UNAVAILABLE). Sólo el gate manual (cleanup) borra su tabla.
#
# Una tabla se considera huérfana si ningún LXC del nodo tiene un nombre que empiece por
# nap-<primeros 8 hex del UUID del recurso> (los LXC de aplicación se llaman así). Las tablas
# de contenedores existentes NO se tocan. Sin argumentos sólo muestra qué haría.
set -u
APLICAR=0; [ "${1:-}" = "--aplicar" ] && APLICAR=1
NODE_IP=${NODE_IP:-192.168.100.91}
ssh -o SendEnv=-LC_* root@$NODE_IP "APLICAR=$APLICAR bash -s" <<'REMOTE'
nombres=$(pct list | awk 'NR>1 {print $NF}')
echo "contenedores del nodo:"; pct list
echo
for t in $(nft -j list tables | python3 -c "import sys,json;print(' '.join(x['table']['family']+':'+x['table']['name'] for x in json.load(sys.stdin)['nftables'] if 'table' in x and x['table']['name'].startswith('nap011_')))"); do
  fam=${t%%:*}; name=${t#*:}; hex=${name#nap011_}; corto=${hex:0:8}
  if printf '%s\n' $nombres | grep -q "^nap-$corto"; then
    echo "$name: su contenedor existe (nap-$corto...) -> se conserva"
  else
    echo "$name: HUÉRFANA (no hay contenedor nap-$corto...)"
    if [ "$APLICAR" = 1 ]; then nft delete table $fam $name && echo "  eliminada"; fi
  fi
done
echo; echo "tablas restantes:"; nft list tables | grep nap011_ || echo "(ninguna)"
REMOTE
[ $APLICAR -eq 1 ] || echo "(simulación: usá --aplicar para eliminar las huérfanas)"
