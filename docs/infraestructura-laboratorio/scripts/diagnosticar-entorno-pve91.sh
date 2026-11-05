#!/bin/bash
# EN LA PC DEL OPERADOR. Sólo lectura. Diagnostica por qué falló la fase 'entorno' (instalación de
# Docker con apt) dentro de un LXC de pve91: red, DNS, rutas, espacio y lo que dejó apt/dpkg.
# No ejecuta apt update/install ni modifica nada del invitado. Revisa todos los LXC del nodo.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
ssh -o SendEnv=-LC_* root@$NODE_IP 'bash -s' <<'REMOTE'
pct list
for id in $(pct list | awk 'NR>1 {print $1}'); do
  echo; echo "=================== CT $id ($(pct status $id))"
  pct exec $id -- bash -c '
    echo "--- red"; ip -4 -br addr; ip route
    echo "--- dns"; cat /etc/resolv.conf | grep -v "^#"
    echo "--- resolucion"; for h in archive.ubuntu.com security.ubuntu.com registry-1.docker.io; do printf "%s -> " $h; getent hosts $h | head -1 || echo FALLA; done
    echo "--- espacio"; df -h / | tail -1; free -m | sed -n 2p
    echo "--- docker.io instalado?"; dpkg -l docker.io containerd runc 2>&1 | tail -4
    echo "--- apt (history, ultimas lineas)"; tail -6 /var/log/apt/history.log 2>&1
    echo "--- apt (term.log, ultimas lineas)"; tail -15 /var/log/apt/term.log 2>&1
    echo "--- procesos apt/dpkg vivos"; pgrep -a "apt|dpkg" || echo ninguno
  ' 2>&1
done
REMOTE
