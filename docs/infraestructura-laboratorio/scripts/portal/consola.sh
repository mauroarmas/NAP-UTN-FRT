#!/bin/bash
# EN LA PC DEL OPERADOR. Ejecuta consola_ops.py dentro del contenedor api del portal del laboratorio.
# Uso: consola.sh <sintetico|inventario|tramite|evidencia|confirmar|perfil> [opciones]   (ver --help)
# Los archivos de entrada/salida (informe del ensayo, perfil) se copian desde/hacia el contenedor; el perfil queda 0600.
set -u
CONTENEDOR=${CONTENEDOR:-nap-handoff-api-1}
AQUI=$(cd "$(dirname "$0")" && pwd)
die() { echo "ERROR: $*" >&2; exit 1; }
docker cp "$AQUI/consola_ops.py" "$CONTENEDOR:/tmp/consola_ops.py" >/dev/null || die "no pude copiar consola_ops.py a $CONTENEDOR"
EJEC=(docker exec -w /app -e PYTHONPATH=/app -e NAP_ADMIN_EMAIL="${NAP_ADMIN_EMAIL:-admin@utn.frt.edu.ar}" "$CONTENEDOR" python /tmp/consola_ops.py)
CMD=${1:-}; ARGS=("$@")
for i in "${!ARGS[@]}"; do
  case "${ARGS[$i]}" in
    --informe) F=${ARGS[$((i+1))]}; docker cp "$F" "$CONTENEDOR:/tmp/informe-ensayo.json" >/dev/null || die "no pude copiar el informe"; ARGS[$((i+1))]=/tmp/informe-ensayo.json ;;
    --salida) SALIDA=${ARGS[$((i+1))]}; ARGS[$((i+1))]=/tmp/perfil-consola.json ;;
  esac
done
"${EJEC[@]}" "${ARGS[@]}"; RC=$?
if [ "$CMD" = perfil ] && [ $RC -eq 0 ]; then
  ( umask 077; docker cp "$CONTENEDOR:/tmp/perfil-consola.json" "$SALIDA" >/dev/null ) && chmod 600 "$SALIDA"
  docker exec "$CONTENEDOR" rm -f /tmp/perfil-consola.json
fi
docker exec "$CONTENEDOR" rm -f /tmp/informe-ensayo.json 2>/dev/null
exit $RC
