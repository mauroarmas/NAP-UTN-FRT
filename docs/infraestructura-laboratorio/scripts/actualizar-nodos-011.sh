#!/bin/bash
# EN LA PC DEL OPERADOR. Alinea frt y pve91 con el motor Docker 011 de Mauro (commit 78af40e):
#   1. copia la plantilla base Ubuntu al storage "local" de cada nodo (desde truenas) y verifica su sha256;
#   2. instala el paquete 011 del checkout actual con infra/runner/install.sh;
#   3. regenera /etc/nap/applications-011/runner.json (plantilla local:, policy_bundle_sha256 vigente,
#      platform leído del nodo, solo los nodos de NODES) y deja el respaldo del anterior;
#   4. escribe ~/runnerjson/APPLICATION_PROFILES.env con la línea para backend/.env del portal.
# install.sh NO reemplaza un runner.json existente: por eso el paso 3 es aparte.
#
# Sin argumentos solo muestra qué haría (no modifica nada). Con --aplicar ejecuta.
# Pide la contraseña de root una vez por nodo (ControlMaster) y se detiene ante el primer fallo.
#
# Variables: REPO, NODES ("nombre=ip ..."), OUT (carpeta de salida local).
set -u
APLICAR=0; [ "${1:-}" = "--aplicar" ] && APLICAR=1
REPO=${REPO:-$HOME/Escritorio/NAP-UTN-FRT}
NODES=${NODES:-"frt=192.168.100.90 pve91=192.168.100.91"}
OUT=${OUT:-$HOME/runnerjson}
TPL=ubuntu-24.04-standard_24.04-2_amd64.tar.zst
TPL_SHA=75a827c4ea4b2bef42e0521f51ed869e398f56b0e6b131c3cd5d284a2e0e08b5
DIGEST_ESPERADO=73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2
CTL=/tmp/nap-actualizar-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=300"
die() { echo "ERROR: $*" >&2; exit 1; }

cd "$REPO" || die "no existe $REPO"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "hay cambios sin commitear en archivos versionados; el paquete sale de HEAD (revisá git status)"
COMMIT=$(git rev-parse --short HEAD)
DIGEST=$(PYTHONPATH="$REPO" python3 -I -c "import sys;sys.path.insert(0,'$REPO');from infra.applications.docker.runtime import policy_digest;print(policy_digest())") \
  || die "no pude calcular policy_digest()"
[ "$DIGEST" = "$DIGEST_ESPERADO" ] || die "policy_digest $DIGEST != $DIGEST_ESPERADO (¿ubuntu24.json con cambios locales?)"
echo "Commit $COMMIT, policy_digest OK ($DIGEST)"
[ $APLICAR -eq 1 ] || echo "(simulación: usá --aplicar para ejecutar)"
mkdir -p "$OUT"

# Fase 1: leer nodos y copiar plantilla (solo lectura si no se aplica).
declare -A PVE KERNEL
for entry in $NODES; do
  name=${entry%%=*}; ip=${entry#*=}; host=root@$ip
  echo "=== $name ($ip)"
  ssh $SSH_OPTS "$host" 'bash -s' <<REMOTE || die "falló la lectura/plantilla en $name"
set -e
echo "pveversion: \$(pveversion)  kernel: \$(uname -r)"
dest=\$(pvesm path local:vztmpl/$TPL)
if [ -f "\$dest" ]; then echo "plantilla ya en local: \$dest"
elif [ $APLICAR -eq 1 ]; then
  if src=\$(pvesm path truenas:vztmpl/$TPL 2>/dev/null) && [ -f "\$src" ]; then cp "\$src" "\$dest.part"; mv "\$dest.part" "\$dest"
  else pveam download local $TPL; fi
else echo "falta la plantilla en local (se copiaría desde truenas)"; fi
if [ -f "\$dest" ]; then
  echo "$TPL_SHA  \$dest" | sha256sum -c - || { [ $APLICAR -eq 1 ] && rm -f "\$dest"; echo "sha256 inválido" >&2; exit 1; }
fi
REMOTE
  PVE[$name]=$(ssh $SSH_OPTS "$host" pveversion | sed -n 's|^pve-manager/\([^/]*\)/.*|\1|p')
  KERNEL[$name]=$(ssh $SSH_OPTS "$host" uname -r)
  [ -n "${PVE[$name]}" ] && [ -n "${KERNEL[$name]}" ] || die "no pude leer pveversion/uname en $name"
done

# Un solo perfil describe a todos los nodos: tienen que coincidir.
first=${NODES%% *}; first=${first%%=*}
for entry in $NODES; do n=${entry%%=*}
  [ "${PVE[$n]}" = "${PVE[$first]}" ] && [ "${KERNEL[$n]}" = "${KERNEL[$first]}" ] \
    || die "platform distinto entre nodos ($n: ${PVE[$n]}/${KERNEL[$n]} vs $first: ${PVE[$first]}/${KERNEL[$first]}); el perfil no puede cubrirlos"
done
NODE_NAMES=$(for e in $NODES; do printf '%s ' "${e%%=*}"; done)

# Fase 2: generar runner.json por nodo a partir del que ya tiene cada nodo.
for entry in $NODES; do
  name=${entry%%=*}; ip=${entry#*=}
  ssh $SSH_OPTS root@$ip 'cat /etc/nap/applications-011/runner.json' > "$OUT/runner-$name.actual.json" \
    || die "no pude leer runner.json de $name (¿paquete no instalado?)"
  python3 -I - "$OUT/runner-$name.actual.json" "$OUT/runner-$name.json" "$DIGEST" "${PVE[$first]}" "${KERNEL[$first]}" "$TPL" $NODE_NAMES <<'PY' || die "no pude generar runner.json de $name"
import hashlib, json, sys
src, dst, digest, pve, kernel, tpl, *nodes = sys.argv[1:]
cfg = json.load(open(src))
canon = lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
for key, entry in cfg['profiles'].items():
    d = entry['definition']
    d['base']['volumen_lxc'] = 'local:vztmpl/' + tpl
    d['nodes'] = nodes
    d['platform'].update(pve=pve, kernel=kernel)
    d['policy_bundle_sha256'] = digest
    entry['sha256'] = hashlib.sha256(canon(d)).hexdigest()
    entry['estado'], entry['motivo_codigo'], entry['validacion'] = 'pendiente_validacion', 'VALIDATION_REQUIRED', None
for net in cfg.get('networks', {}).values():
    net['nodes'] = nodes
json.dump(cfg, open(dst, 'w'), separators=(',', ':'))
if cfg['node'] == nodes[0]:  # línea para el portal, una sola vez
    profiles = {k: v for k, v in cfg['profiles'].items()}
    open(dst.rsplit('/', 1)[0] + '/APPLICATION_PROFILES.env', 'w').write('APPLICATION_PROFILES=' + json.dumps(profiles) + '\n')
PY
  echo "runner.json de $name generado en $OUT/runner-$name.json"
done
[ $APLICAR -eq 1 ] || { echo "Simulación terminada. Revisá $OUT/runner-*.json y corré con --aplicar."; exit 0; }

# Fase 3: instalar paquete y reemplazar runner.json.
for entry in $NODES; do
  name=${entry%%=*}; ip=${entry#*=}; host=root@$ip; dir=/root/nap-$COMMIT
  echo "=== instalando en $name"
  ssh $SSH_OPTS "$host" "rm -rf $dir && install -d -m 755 $dir" || die "no pude preparar $dir en $name"
  git -C "$REPO" archive HEAD | ssh $SSH_OPTS "$host" "tar -C $dir -xf - --no-same-owner" || die "falló la copia a $name"
  scp -o ControlPath=$CTL "$OUT/runner-$name.json" "$host:/root/runner-$name.nuevo.json" >/dev/null || die "falló scp del runner.json"
  ssh $SSH_OPTS "$host" "bash -s" <<REMOTE || die "falló la instalación en $name; me detengo."
set -e
chown -R root:root $dir && chmod -R go-w $dir
bash $dir/infra/runner/install.sh
cp -p /etc/nap/applications-011/runner.json /root/runner-$name.antes.json
install -o root -g root -m 0600 /root/runner-$name.nuevo.json /etc/nap/applications-011/runner.json
rm -f /root/runner-$name.nuevo.json
REMOTE
  ssh -o ControlPath=$CTL -O exit "$host" 2>/dev/null
done
echo "Listo. Pendiente: pegar $OUT/APPLICATION_PROFILES.env en backend/.env y reiniciar la API."
