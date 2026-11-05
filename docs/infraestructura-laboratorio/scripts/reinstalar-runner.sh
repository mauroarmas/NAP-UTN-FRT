#!/bin/bash
# EN LA PC DEL OPERADOR. Retira un "naprunner" creado a mano e instala el runner con
# el asistente oficial infra/runner/configure_access.py.
#
# ESTADO: BLOQUEADO en el commit 0167202 de la rama 011. La verificación final del
# asistente falla porque configure_access.py no copia registry_entries.py (lo instala
# install.sh) y, a la vez, se niega a correr si esos archivos ya existen.
# Ver README, sección "Runner". NO ejecutar hasta confirmar la secuencia con Mauro.
#
# Si el procedimiento se corrige, este script ya resuelve dos problemas reales que
# aparecieron: (1) el paquete copiado debe ser de root y sin escritura de grupo/otros
# (en la PC del operador los archivos son 664), (2) pide la contraseña de root una
# vez por nodo (ControlMaster) y se detiene ante el primer fallo.
#
# Variables: REPO, PUB (clave pública Ed25519 del worker), WORKER_IP (IP de origen que
# ven los nodos), NODES.
set -u
REPO=${REPO:-$HOME/Escritorio/NAP-UTN-FRT}
PUB=${PUB:-$HOME/.local/share/nap009/ssh/runner_ed25519.pub}
WORKER_IP=${WORKER_IP:?IP de origen del worker, p. ej. la de la PC/servidor del portal}
NODES=${NODES:-"192.168.100.90 192.168.100.91 192.168.100.92 192.168.100.93"}
CTL=/tmp/nap-runner-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=180"

for node in $NODES; do
  host=root@$node
  echo "=== $node"
  ssh $SSH_OPTS "$host" 'bash -s' <<'REMOTE' || { echo "FALLO limpiando $node; me detengo."; exit 1; }
set -e
pkill -u naprunner 2>/dev/null || true
sleep 1
rm -f /etc/sudoers.d/naprunner
if getent passwd naprunner >/dev/null; then userdel -r naprunner 2>&1 | grep -v 'mail spool' || true; fi
if getent group naprunner >/dev/null; then groupdel naprunner; fi
rm -rf /root/nap-src
install -d -m 755 /root/nap-src
REMOTE
  tar -C "$REPO" -cf - \
      infra/runner/configure_access.py infra/runner/nap_guest_runner.py \
      infra/runner/node_executor.py infra/runner/nap-guest-runner \
      backend/app/schemas/guest_runner.py \
    | ssh $SSH_OPTS "$host" "tar -C /root/nap-src -xf - --no-same-owner" || { echo "FALLO copiando a $node"; exit 1; }
  scp -o ControlPath=$CTL "$PUB" "$host:/root/nap-src/worker.pub" >/dev/null || { echo "FALLO clave"; exit 1; }
  ssh $SSH_OPTS "$host" "chown -R root:root /root/nap-src && chmod -R go-w /root/nap-src && cd /root/nap-src && python3 -I infra/runner/configure_access.py --worker-ip $WORKER_IP --node-ip $node --public-key /root/nap-src/worker.pub --apply" \
    || { echo "FALLO instalando en $node; me detengo."; exit 1; }
  ssh $SSH_OPTS "$host" "rm -rf /root/nap-src"
  ssh -o ControlPath=$CTL -O exit "$host" 2>/dev/null
done
