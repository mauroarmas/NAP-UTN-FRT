#!/bin/bash
# EN LA PC DEL OPERADOR. Sólo lectura: lista los LXC de pve91 y, dentro de cada uno, los
# contenedores Docker con su estado y las últimas líneas de su log. Sirve para entender por
# qué falló la fase 'comprobacion' de un despliegue (el portal oculta la salida de docker).
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
ssh -o SendEnv=-LC_* root@$NODE_IP 'bash -s' <<'REMOTE'
pct list
for id in $(pct list | awk 'NR>1 {print $1}'); do
  echo
  echo "=== CT $id ($(pct status $id))"
  pct exec $id -- docker ps -a --format '{{.Names}}  {{.Status}}  {{.Image}}' 2>&1
  for c in $(pct exec $id -- docker ps -aq 2>/dev/null); do
    echo "--- logs de $c"
    pct exec $id -- docker logs --tail 15 $c 2>&1
  done
done
REMOTE
