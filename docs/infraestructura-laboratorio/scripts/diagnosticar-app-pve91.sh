#!/bin/bash
# EN LA PC DEL OPERADOR. Diagnóstico de una app que entra en "Restarting" en un LXC de pve91.
# La app se lanza con --log-driver=none, así que 'docker logs' no sirve. Aquí se arranca la MISMA
# imagen con las MISMAS restricciones (infra/applications/docker/contract.py) pero con el driver
# de logs por defecto, en un contenedor descartable (--rm, otro nombre, sin publicar puertos),
# y se muestra su salida. No modifica el contenedor de la app ni el estado del portal.
# Uso: diagnosticar-app-pve91.sh [VMID] [IMAGEN]   (VMID por defecto 101)
# Con IMAGEN (p. ej. nginxinc/nginx-unprivileged:latest) la descarga en ese invitado y la prueba en
# vez de la imagen de la app. Sólo agrega una imagen al invitado, que es de prueba/descartable.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
VMID=${1:-101}
IMAGEN=${2:-}
ssh -o SendEnv=-LC_* root@$NODE_IP "pct exec $VMID -- env IMAGEN=$IMAGEN bash -s" <<'REMOTE'
app=$(docker ps -a --format '{{.Names}}' | grep -v -- '-edge$' | head -1)
[ -n "$app" ] || { echo "no encuentro el contenedor de la app"; exit 1; }
img=$(docker inspect --format '{{.Image}}' "$app")
if [ -n "$IMAGEN" ]; then
  echo "== descargando $IMAGEN"
  docker pull "$IMAGEN" 2>&1 | tail -3 || exit 1
  img=$IMAGEN
fi
echo "== app: $app  imagen: $img"
echo "== estado: $(docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}} reinicios={{.RestartCount}}' "$app")"
echo "== arranque de prueba con las mismas restricciones (15 s máx.)"
timeout 15 docker run --rm --name diag-nap --pull=never --network=bridge \
  --cap-drop=ALL --cap-add=NET_BIND_SERVICE --security-opt=no-new-privileges:true \
  --pids-limit=256 --memory=768m --memory-swap=768m --cpus=2 --publish=127.0.0.1:18081:8080 "$img" 2>&1 | tail -25
echo "== codigo de salida: ${PIPESTATUS[0]:-?} (124 = siguió corriendo, o sea arrancó bien)"
REMOTE
