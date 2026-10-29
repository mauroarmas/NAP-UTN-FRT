#!/bin/bash
# EN LA PC DEL OPERADOR. Diagnóstico del gate Docker en pve91 cuando 'start' queda UNCONFIRMED.
# El gate descarta el stderr de docker; aquí se reproduce el MISMO docker run de la app
# (infra/applications/docker/contract.py: application_arguments) con otro nombre, --rm y
# un timeout, dentro del invitado de prueba 900011, para ver el mensaje de error real.
# No toca el estado del gate. Si el contenedor llega a arrancar, --rm lo retira.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
VMID=${VMID:-900011}
IMG=docker.io/traefik/whoami@sha256:80f8bb74f634d45d55967820a702c5fddf01cf92968bb29ed7a3573dd16b0e55
ssh -o SendEnv=-LC_* root@$NODE_IP "pct exec $VMID -- sh -s" <<REMOTE
echo "== docker info (cgroup/seguridad)"
docker info 2>&1 | grep -i -E 'storage driver|cgroup|security|swap|warning'
echo "== docker run de la app (mismas opciones que el gate)"
timeout 20 docker run --rm --name diag-nap --pull=never --network=bridge \
  --cap-drop=ALL --cap-add=NET_BIND_SERVICE --security-opt=no-new-privileges:true \
  --log-driver=none --no-healthcheck --pids-limit=256 --memory=768m --memory-swap=768m \
  --cpus=2 --publish=127.0.0.1:18080:80 $IMG
echo "== codigo de salida: \$? (124 = siguio corriendo hasta el timeout, es decir, arranco bien)"
docker ps -a --format '{{.Names}} {{.Status}}'
REMOTE
