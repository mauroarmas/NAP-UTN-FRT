#!/bin/bash
# EN LA PC DEL OPERADOR. Habilita docker-ubuntu24:$PERFIL_REV (por defecto 2) con la evidencia real
# del gate en pve91. Las revisiones históricas (docker-ubuntu24:1) NO se modifican.
#
# La entrada habilitada se arma con la definición que el gate VALIDÓ de verdad (campo 'profile' de
# su contexto root en pve91), no con una recalculada, y exige TODO lo siguiente (si falta algo,
# no se modifica nada):
#   - el gate quedó 'cleaned' (invitado retirado con gate-docker-pve91.sh limpiar);
#   - revisión de la definición validada == PERFIL_REV y nodes == GATE_NODOS (sólo nodos comprobados);
#   - sha256(canónico(definición)) == perfil.sha256 de la petición validada;
#   - la definición coincide con la del runner.json actual salvo 'nodes';
#   - evidencia-mariadb-rev<N>.json (gate-docker-pve91.sh evidencia): job 'confirmado' con
#     aislamiento, runtime, salud y autenticacion_tcp (TLS + SELECT 1 con la CA);
#   - persistencia-mariadb-rev<N>.json: fila escrita y recuperada tras reiniciar el LXC. Montar
#     /data en whoami NO acredita persistencia y no se acepta como tal;
#   - ProfileRegistry (el mismo contrato de portal y nodos) acepta la entrada habilitada.
# Las cinco comprobaciones del registro se derivan de esa evidencia (secretos = secretos generados
# por job usados por el motor MariaDB). Pull privado y carga multi-cátedra NO quedan acreditados.
#
# Sin argumentos: genera y valida en $OUT, no modifica nada. Con --aplicar: instala la MISMA entrada
# en runner.json de los nodos y la FUSIONA (sin quitar revisiones previas) en compose-api-011.yml,
# con respaldos, y recrea api y worker. Los nodos fuera de 'nodes' no pueden correr el perfil.
set -u
APLICAR=0; [ "${1:-}" = "--aplicar" ] && APLICAR=1
REPO=${REPO:-$HOME/Escritorio/NAP-UTN-FRT}
GATE_NODE=${GATE_NODE:-192.168.100.91}
PERFIL_REV=${PERFIL_REV:-2}
GATE_NODOS=${GATE_NODOS:-pve91}
NODES=${NODES:-"frt=192.168.100.90 pve91=192.168.100.91"}
OUT=${OUT:-$HOME/runnerjson}
PRIV=${PRIV:-$HOME/.local/share/nap009}
CTL=${NAP_SSH_CTL:-/tmp/nap-lab-ssh-%h}
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=300 -o SendEnv=-LC_*"
die() { echo "ERROR: $*" >&2; exit 1; }
mkdir -p "$OUT"

# 1. Del nodo sólo salen los campos públicos del contexto (no el nonce ni el resto).
ssh $SSH_OPTS root@$GATE_NODE "python3 -I -c \"
import json
c = json.load(open('/root/nap011-final-docker-gate/context.json'))
print(json.dumps({'phase': c['phase'], 'profile': c['profile'], 'perfil': c['request']['perfil']}))\"" \
  > "$OUT/gate-validado.json" || die "no pude leer el contexto del gate en $GATE_NODE"

# 2. Construir y validar la entrada habilitada (y un runner.json por nodo).
for entry in $NODES; do
  name=${entry%%=*}; ip=${entry#*=}
  ssh $SSH_OPTS root@$ip 'cat /etc/nap/applications-011/runner.json' > "$OUT/runner-$name.actual.json" \
    || die "no pude leer runner.json de $name"
done
PERFIL_REV=$PERFIL_REV GATE_NODOS=$GATE_NODOS python3 -I - "$REPO" "$OUT" $NODES <<'PY' || die "la entrada habilitada no es válida; no se modificó nada"
import hashlib, json, os, sys
repo, out, *nodes = sys.argv[1:]
sys.path.insert(0, repo)
from backend.app.schemas.application_profiles import ProfileRegistry, canonical
gate = json.load(open(out + '/gate-validado.json'))
if gate['phase'] != 'cleaned':
    sys.exit('el gate no está en fase cleaned (fase: %s); correr gate-docker-pve91.sh limpiar' % gate['phase'])
d = gate['profile']
rev = int(os.environ['PERFIL_REV'])
if d['revision'] != rev:
    sys.exit('el gate validó la revisión %s, no %s' % (d['revision'], rev))
if d['nodes'] != os.environ['GATE_NODOS'].split():
    sys.exit('nodes de la definición validada %s != GATE_NODOS' % d['nodes'])
ev = json.load(open('%s/evidencia-mariadb-rev%d.json' % (out, rev)))
need = {'aislamiento', 'runtime', 'salud', 'autenticacion_tcp'}
if ev['job_state'] != 'confirmado' or ev['perfil_revision'] != rev or not need <= set(ev['comprobaciones'] or []):
    sys.exit('la evidencia de MariaDB no acredita un job confirmado con %s' % sorted(need))
per = json.load(open('%s/persistencia-mariadb-rev%d.json' % (out, rev)))
if per.get('escrito') is not True or per.get('recuperado_tras_reinicio') is not True:
    sys.exit('la persistencia (escribir, reiniciar, recuperar) no está acreditada')
if hashlib.sha256(canonical(d)).hexdigest() != gate['perfil']['sha256']:
    sys.exit('el hash de la definición validada no coincide con el de la petición')
entry = {'definition': d, 'sha256': gate['perfil']['sha256'], 'estado': 'habilitado', 'motivo_codigo': None,
         'validacion': {'tipo': 'proxmox_real', 'perfil_sha256': gate['perfil']['sha256'],
                        'cluster_uuid': d['cluster_uuid'], 'platform': d['platform'],
                        'comprobaciones': ['aislamiento', 'runtime', 'persistencia', 'acceso', 'secretos']}}
key = d['id'] + ':' + str(d['revision'])
ProfileRegistry({key: entry})
for item in nodes:
    name = item.split('=')[0]
    cfg = json.load(open('%s/runner-%s.actual.json' % (out, name)))
    old = cfg['profiles'][key]['definition']
    if {k: v for k, v in old.items() if k != 'nodes'} != {k: v for k, v in d.items() if k != 'nodes'}:
        sys.exit('la definición validada difiere de la de %s más que en nodes' % name)
    if cfg['profiles'][key]['estado'] == 'habilitado' and cfg['profiles'][key] != entry:
        sys.exit('%s ya está habilitado con otra entrada en %s' % (key, name))
    cfg['profiles'][key] = entry
    json.dump(cfg, open('%s/runner-%s.json' % (out, name), 'w'), separators=(',', ':'))
json.dump({key: entry}, open(out + '/APPLICATION_PROFILES.habilitado.json', 'w'), separators=(',', ':'))
open(out + '/PERFIL_KEY', 'w').write(key)
print('entrada habilitada OK:', key, entry['sha256'], 'nodes =', d['nodes'])
PY
[ $APLICAR -eq 1 ] || { echo "Simulación terminada. Archivos en $OUT; corré con --aplicar."; exit 0; }

# 3. Aplicar: nodos primero (con respaldo), después el portal.
for entry in $NODES; do
  name=${entry%%=*}; ip=${entry#*=}
  scp -o ControlPath=$CTL "$OUT/runner-$name.json" root@$ip:/root/runner-$name.habilitado.json >/dev/null || die "falló scp a $name"
  ssh $SSH_OPTS root@$ip "set -e; cp -p /etc/nap/applications-011/runner.json /root/runner-$name.antes-habilitar.json; install -o root -g root -m 0600 /root/runner-$name.habilitado.json /etc/nap/applications-011/runner.json; rm -f /root/runner-$name.habilitado.json" \
    || die "falló la instalación en $name; me detengo."
  echo "runner.json habilitado en $name"
done
cp -p "$PRIV/compose-api-011.yml" "$PRIV/env-backup/compose-api-011.yml.$(date +%Y%m%d-%H%M%S)" || die "no pude respaldar el override"
python3 -I - "$PRIV/compose-api-011.yml" "$OUT/APPLICATION_PROFILES.habilitado.json" <<'PY' || die "no pude actualizar el override del portal"
import json, sys
path, new = sys.argv[1:]
lines = open(path).read().split('\n')
idx = [i for i, l in enumerate(lines) if l.startswith('  APPLICATION_PROFILES: ')]
assert len(idx) == 1
current = json.loads(json.loads(lines[idx[0]].split(': ', 1)[1]))
added = json.loads(open(new).read())
# Se fusiona: las revisiones históricas del portal se conservan; sólo se agrega/actualiza la nueva.
current.update(added)
lines[idx[0]] = '  APPLICATION_PROFILES: ' + json.dumps(json.dumps(current, separators=(',', ':')))
open(path, 'w').write('\n'.join(lines))
PY
cd "$REPO" && docker compose -p nap-handoff -f docker-compose.handoff.yml -f "$PRIV/compose-api-lab.yml" -f "$PRIV/compose-api-011.yml" up -d --force-recreate api worker \
  || die "falló la recreación de api/worker"
echo "Listo: perfil habilitado en nodos y portal. Probar desde el portal."
