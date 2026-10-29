#!/bin/bash
# EN LA PC DEL OPERADOR. Sólo lectura. Muestra el estado REAL del último job de aplicación en
# pve91, sin depender de la consulta del portal: campos públicos del job (estado, fase, error,
# resultado), la unidad systemd del worker del nodo, los LXC y los contenedores Docker.
# No imprime secretos ni el contenido completo del job.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
ssh -o SendEnv=-LC_* root@$NODE_IP 'bash -s' <<'REMOTE'
dir=/var/lib/nap-application-jobs
f=$(ls -t $dir/job.*.json 2>/dev/null | head -1)
echo "=== job más reciente: ${f:-ninguno}"
[ -n "$f" ] && python3 - "$f" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
for k in ('estado', 'fase', 'error_codigo', 'resultado', 'last_source_seq', 'updated_at', 'finished_at'):
    if k in j: print('%-16s %s' % (k, j[k]))
PY
if [ -n "$f" ]; then
  id=$(basename "$f" .json); id=${id#job.}
  echo; echo "=== unidad systemd"
  systemctl show "nap-application-$id.service" -p ActiveState -p SubState -p Result -p ExecMainStatus 2>&1
fi
echo; echo "=== carga del nodo"; uptime; free -m | sed -n 2p
echo; pct list
for ct in $(pct list | awk 'NR>1 {print $1}'); do
  echo; echo "=== docker en CT $ct"
  pct exec $ct -- docker ps -a --format '{{.Names}}  {{.Status}}  {{.Image}}' 2>&1
done
REMOTE
