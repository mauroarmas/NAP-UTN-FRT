#!/bin/bash
# EN LA PC DEL OPERADOR. Corre en pve91 la compuerta real del motor Docker 011 adaptada al
# laboratorio (infra/laboratorio/011/validar_motor_docker_lab.py) con traefik/whoami (Docker Hub).
# No habilita perfiles: solo prueba que el motor funciona. Habilitar es un paso aparte.
#
# Uso: gate-docker-pve91.sh preparar | iniciar | estado | limpiar
#   preparar  copia el gate al nodo y sella el candidato (no crea el invitado)
#   iniciar   crea el LXC de prueba (VMID 900011, slot .119) y lanza el despliegue de whoami
#   estado    consulta fase, invitado y resultado (sólo lectura)
#   limpiar   destruye el invitado de prueba, su disco, su tabla nftables y su pool
# Para la corrida que cubre persistencia: PERSISTENCIA='["/data"]' gate-docker-pve91.sh preparar
# 'iniciar' se ejecuta UNA vez: si la respuesta se pierde, usar 'estado', no repetir.
# El candidato vence a la hora de 'preparar'; si venció, 'limpiar' y volver a 'preparar'.
set -u
REPO=${REPO:-$HOME/Escritorio/NAP-UTN-FRT}
NODE_IP=${NODE_IP:-192.168.100.91}
RUNNER_JSON=${RUNNER_JSON:-$HOME/runnerjson/runner-pve91.json}
DEST=/root/nap011-gate-lab
GATE=$DEST/validar_motor_docker_lab.py
CTL=/tmp/nap-gate-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=600 -o SendEnv=-LC_*"
die() { echo "ERROR: $*" >&2; exit 1; }
remote() { ssh $SSH_OPTS root@$NODE_IP "$@"; }
BASE=/root/nap011-final-docker-gate
# Sin quórum /etc/pve es de sólo lectura y el gate falla sin mensaje (CalledProcessError).
quorum() {
  remote "pvecm status | grep -q '^Quorate:[[:space:]]*Yes'" \
    || die "el cluster no tiene quórum; en el nodo: pvecm expected 2 (se pierde al reiniciar)"
}

case "${1:-}" in
  preparar)
    [ -f "$RUNNER_JSON" ] || die "no existe $RUNNER_JSON (corré actualizar-nodos-011.sh primero)"
    DATA=$(python3 -I - "$RUNNER_JSON" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
net = json.loads(json.dumps(cfg['networks']['lab-applications-011']))
net['nodes'] = ['pve91']
net['slots'] = {'app-119': net['slots']['app-119']}   # el gate usa un solo slot reservado
# traefik/whoami:latest (amd64) en Docker Hub, con los digests observados el 28/10/2026
image = {'repositorio': 'docker.io/traefik/whoami', 'tag_original': 'latest',
         'manifest_digest': 'sha256:80f8bb74f634d45d55967820a702c5fddf01cf92968bb29ed7a3573dd16b0e55',
         'index_digest': 'sha256:c4717a8d1f0134a7444e24f881160e033991f23027c6c5a9a3f8fd22e70d1d44',
         'config_digest': 'sha256:cd370f99dbfb63a9541c3787c576352d0d22e78fa33ef9d831f97cbeee9667e9',
         'os': 'linux', 'arquitectura': 'amd64', 'registry_profile_id': 'docker-hub'}
print(json.dumps({'cluster_uuid': cfg['cluster_uuid'], 'port': 80, 'probe_path': '/',
                  'persistencia': json.loads(os.environ.get('PERSISTENCIA', '[]')), 'image': image, 'network': net}))
PY
    ) || die "no pude armar la entrada del gate"
    quorum
    # El gate se niega a sellar si queda un contexto anterior. Sólo se archiva uno ya limpiado.
    remote "if [ -e $BASE/context.json ]; then grep -q '\"phase\":\"cleaned\"' $BASE/context.json && mv $BASE/context.json $BASE/context.cleaned.\$(date +%s) || { echo 'contexto anterior sin limpiar: correr limpiar' >&2; exit 1; }; fi" \
      || die "hay un contexto anterior que no está limpiado"
    remote "install -d -m 700 -o root -g root $DEST" || die "no pude crear $DEST"
    scp -o ControlPath=$CTL "$REPO/infra/laboratorio/011/validar_motor_docker_lab.py" root@$NODE_IP:$GATE >/dev/null || die "falló la copia"
    remote "chown root:root $GATE && chmod 700 $GATE"
    printf '%s' "$DATA" | remote "python3 -I $GATE --init"
    ;;
  iniciar)  quorum; remote "python3 -I $GATE --start" ;;
  estado)   remote "python3 -I $GATE --status" ;;
  limpiar)  remote "python3 -I $GATE --cleanup" ;;
  *) die "uso: $0 preparar | iniciar | estado | limpiar" ;;
esac
