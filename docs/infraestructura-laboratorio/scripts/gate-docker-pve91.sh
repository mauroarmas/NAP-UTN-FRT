#!/bin/bash
# EN LA PC DEL OPERADOR. Corre en pve91 la compuerta real del motor Docker 011 adaptada al
# laboratorio (infra/laboratorio/011/validar_motor_docker_lab.py) con traefik/whoami (Docker Hub).
# No habilita perfiles: solo prueba que el motor funciona. Habilitar es un paso aparte.
#
# Uso: APLICACION=whoami|mariadb [PERFIL_REV=2] gate-docker-pve91.sh preparar | iniciar | estado | evidencia | persistencia | rechazos | limpiar
#   preparar  copia el gate al nodo y sella el candidato (no crea el invitado)
#   iniciar   crea el LXC de prueba (VMID 900011, slot .119) y lanza el despliegue de whoami
#   estado    consulta fase, invitado y resultado (sólo lectura)
#   evidencia guarda en $OUT el estado SIN secretos (job confirmado + comprobaciones) para habilitar-perfil
#   persistencia (sólo mariadb) escribe una fila, reinicia el LXC de prueba y verifica que se recupere
#   rechazos  (sólo mariadb) contraseña errónea, CA no confiable, sin TLS, root remoto y lectura de mysql.user
#   limpiar   destruye el invitado de prueba, su disco y su pool; las reglas nftables las retira la
#             misma acción cleanup del motor (identidad + ausencia + recibo), no un borrado heurístico
# Whoami con /data (PERSISTENCIA='["/data"]') sólo prueba que el volumen se monta: NO acredita
# persistencia. La persistencia se acredita con MariaDB: escribir, reiniciar y recuperar (subcomando
# 'persistencia'). PERFIL_REV es la revisión que el gate sella en su definición (el original usa 1).
# 'iniciar' se ejecuta UNA vez: si la respuesta se pierde, usar 'estado', no repetir.
# El candidato vence a la hora de 'preparar'; si venció, 'limpiar' y volver a 'preparar'.
set -u
REPO=${REPO:-$HOME/Escritorio/NAP-UTN-FRT}
NODE_IP=${NODE_IP:-192.168.100.91}
APLICACION=${APLICACION:-whoami}
PERFIL_REV=${PERFIL_REV:-2}
OUT=${OUT:-$HOME/runnerjson}
RUNNER_JSON=${RUNNER_JSON:-$HOME/runnerjson/runner-pve91.json}
DEST=/root/nap011-gate-lab
GATE=$DEST/validar_motor_docker_lab.py
CTL=${NAP_SSH_CTL:-/tmp/nap-lab-ssh-%h}
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
    DATA=$(APLICACION=$APLICACION PERFIL_REV=$PERFIL_REV python3 -I - "$RUNNER_JSON" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
net = json.loads(json.dumps(cfg['networks']['lab-applications-011']))
net['nodes'] = ['pve91']
net['slots'] = {'app-119': net['slots']['app-119']}   # el gate usa un solo slot reservado
app = os.environ['APLICACION']
if app == 'mariadb':
    # mariadb:11.4 (amd64) en Docker Hub; manifiesto observado el 02/11/2026 (coincide con la evidencia de Mauro).
    image = {'repositorio': 'docker.io/library/mariadb', 'tag_original': '11.4',
             'manifest_digest': 'sha256:d9fc02976678d4236145299c40dc267051681b33489c994f0ec4a097ce4a9521',
             'index_digest': 'sha256:d1891ede5a559f1086f55053bb8cc1569b0298338c4d72d71725a7f74f6ba620',
             'config_digest': 'sha256:1d2b32fbc13a8ed222b073036d268b669ddb1396e6b8f35b41e5b1b08ac15ea1',
             'os': 'linux', 'arquitectura': 'amd64', 'registry_profile_id': 'docker-hub'}
    extra = {'application': 'mariadb', 'port': 3306, 'probe_path': '/'}
elif app == 'whoami':
    # traefik/whoami:latest (amd64) en Docker Hub, con los digests observados el 28/10/2026
    image = {'repositorio': 'docker.io/traefik/whoami', 'tag_original': 'latest',
             'manifest_digest': 'sha256:80f8bb74f634d45d55967820a702c5fddf01cf92968bb29ed7a3573dd16b0e55',
             'index_digest': 'sha256:c4717a8d1f0134a7444e24f881160e033991f23027c6c5a9a3f8fd22e70d1d44',
             'config_digest': 'sha256:cd370f99dbfb63a9541c3787c576352d0d22e78fa33ef9d831f97cbeee9667e9',
             'os': 'linux', 'arquitectura': 'amd64', 'registry_profile_id': 'docker-hub'}
    extra = {'port': 80, 'probe_path': '/'}
else:
    sys.exit('APLICACION debe ser whoami o mariadb')
print(json.dumps({'cluster_uuid': cfg['cluster_uuid'], 'profile_revision': int(os.environ['PERFIL_REV']),
                  'persistencia': json.loads(os.environ.get('PERSISTENCIA', '[]')), 'image': image, 'network': net, **extra}))
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
  evidencia)
    mkdir -p "$OUT"; F="$OUT/evidencia-$APLICACION-rev$PERFIL_REV.json"
    remote "python3 -I $GATE --status" > "$F.tmp" || die "no pude leer el estado"
    python3 -I - "$F.tmp" "$F" "$APLICACION" "$PERFIL_REV" <<'PY' || die "el job no está confirmado; no se guardó evidencia"
import json, sys
s = json.loads(open(sys.argv[1]).read().strip().splitlines()[-1]); s = s.get('data', s)
if s.get('job_state') != 'confirmado' or not s.get('result') or not s['result'].get('recurso_configurado'):
    sys.exit(1)
json.dump({'aplicacion': sys.argv[3], 'perfil_revision': int(sys.argv[4]), 'job_state': s['job_state'],
           'comprobaciones': s['result'].get('comprobaciones'), 'gate_phase': s.get('gate_phase')},
          open(sys.argv[2], 'w'), indent=1, sort_keys=True)
print(open(sys.argv[2]).read())
PY
    rm -f "$F.tmp" ;;
  persistencia)
    [ "$APLICACION" = mariadb ] || die "la persistencia se acredita con APLICACION=mariadb"
    mkdir -p "$OUT"; F="$OUT/persistencia-mariadb-rev$PERFIL_REV.json"
    # Corre en el nodo como root; la contraseña sale del contexto root-only y viaja por stdin, nunca por argv ni salida.
    remote "python3 -I - " > "$F" <<'PY' || die "falló la prueba de persistencia (ver salida parcial en $F)"
import json, secrets, subprocess, sys, time
from uuid import UUID
c = json.load(open('/root/nap011-final-docker-gate/context.json'))
pw = c['private_values']['MARIADB_PASSWORD']; name = 'nap-' + UUID(c['request']['resource_uuid']).hex
addr = c['slot']['address']; vmid = str(c['request']['vmid'])
def sql(statement, timeout=40):
    sh = ('read -r MYSQL_PWD; export MYSQL_PWD; exec docker exec --env MYSQL_PWD %s mariadb --no-defaults --protocol=tcp '
          '--host=%s --port=3306 --user=docente --database=catedra --connect-timeout=5 --ssl-ca=/run/nap-tls/ca.crt '
          '--ssl-verify-server-cert --batch --skip-column-names --execute="%s"') % (name, addr, statement)
    r = subprocess.run(['/usr/sbin/pct', 'exec', vmid, '--', 'sh', '-c', sh], input=(pw + '\n').encode(),
                       capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode().strip()
marca = secrets.token_hex(12)
r1 = sql('CREATE TABLE IF NOT EXISTS nap_persistencia (id INT PRIMARY KEY, marca VARCHAR(64))')[0]
r2 = sql("REPLACE INTO nap_persistencia VALUES (1,'%s')" % marca)[0]
rc, antes = sql('SELECT marca FROM nap_persistencia WHERE id=1')
subprocess.run(['/usr/sbin/pct', 'reboot', vmid], check=True, capture_output=True, timeout=120)
despues = None; t0 = time.monotonic(); intentos = 0
while time.monotonic() - t0 < 240:
    time.sleep(6); intentos += 1
    try: rc, out = sql('SELECT marca FROM nap_persistencia WHERE id=1', timeout=30)
    except subprocess.TimeoutExpired: continue
    if rc == 0 and out: despues = out; break
res = {'escrito': r1 == 0 and r2 == 0 and antes == marca, 'recuperado_tras_reinicio': despues == marca,
       'segundos_hasta_consulta': round(time.monotonic() - t0), 'intentos': intentos}
print(json.dumps(res)); sys.exit(0 if res['escrito'] and res['recuperado_tras_reinicio'] else 1)
PY
    cat "$F" ;;
  rechazos)
    [ "$APLICACION" = mariadb ] || die "los rechazos se prueban con APLICACION=mariadb"
    mkdir -p "$OUT"; F="$OUT/rechazos-mariadb-rev$PERFIL_REV.json"
    # Control positivo primero: sin él un rechazo no significa nada. Secretos por stdin, nunca en argv/salida.
    remote "python3 -I - " > "$F" <<'PY' || die "algún rechazo NO se produjo o el control positivo falló (ver $F)"
import json, re, subprocess, sys
from uuid import UUID
c = json.load(open('/root/nap011-final-docker-gate/context.json'))
pv = c['private_values']; name = 'nap-' + UUID(c['request']['resource_uuid']).hex
addr = c['slot']['address']; vmid = str(c['request']['vmid'])
def run(user, password, sql, ssl_args):
    sh = ('read -r MYSQL_PWD; export MYSQL_PWD; exec docker exec --env MYSQL_PWD %s mariadb --no-defaults --protocol=tcp '
          '--host=%s --port=3306 --user=%s --connect-timeout=5 %s --batch --skip-column-names --execute="%s"') % (name, addr, user, ssl_args, sql)
    r = subprocess.run(['/usr/sbin/pct', 'exec', vmid, '--', 'sh', '-c', sh], input=(password + '\n').encode(), capture_output=True, timeout=60)
    err = r.stderr.decode(errors='replace')
    for v in pv.values(): err = err.replace(v, '***')
    m = re.search(r'ERROR (\d+)', err)
    return r.returncode, (m.group(1) if m else None), r.stdout.decode().strip()
good = '--ssl-ca=/run/nap-tls/ca.crt --ssl-verify-server-cert'
pw = pv['MARIADB_PASSWORD']
cases = {}
rc, code, out = run('docente', pw, 'SELECT 1', good); cases['control_positivo_tls_ok'] = (rc == 0 and out == '1', code)
rc, code, _ = run('docente', pw + 'x', 'SELECT 1', good); cases['contrasena_incorrecta'] = (rc != 0 and code == '1045', code)
rc, code, _ = run('docente', pw, 'SELECT 1', '--ssl-ca=/etc/ssl/certs/ca-certificates.crt --ssl-verify-server-cert'); cases['ca_no_confiable'] = (rc != 0 and code in ('2026', '2002', '2013'), code)
rc, code, _ = run('docente', pw, 'SELECT 1', '--skip-ssl'); cases['sin_tls'] = (rc != 0 and code in ('1045', '3159', '2026', '4141'), code)
rc, code, _ = run('root', pv['MARIADB_ROOT_PASSWORD'], 'SELECT 1', good); cases['root_remoto'] = (rc != 0 and code == '1045', code)
rc, code, _ = run('docente', pw, 'SELECT COUNT(*) FROM mysql.user', good + ' --database=catedra'); cases['docente_no_lee_mysql_user'] = (rc != 0 and code in ('1142', '1044', '1045'), code)
res = {k: {'ok': v[0], 'codigo_mariadb': v[1]} for k, v in cases.items()}
print(json.dumps(res, sort_keys=True)); sys.exit(0 if all(v[0] for v in cases.values()) else 1)
PY
    cat "$F" ;;
  limpiar)  remote "python3 -I $GATE --cleanup" ;;
  *) die "uso: $0 preparar | iniciar | estado | evidencia | persistencia | rechazos | limpiar" ;;
esac
