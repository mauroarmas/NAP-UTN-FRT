#!/bin/bash
# EN LA PC DEL OPERADOR. Ejecuta portal_ops.py dentro del contenedor api del portal del laboratorio.
# Uso: portal.sh <cuenta|oferta|pedido|orden|reparar|actualizar-consola|revelar|capacidad|catedra-sintetica> [opciones]   (ver --help)
# Variables: CONTENEDOR (por defecto nap-handoff-api-1), NAP_ADMIN_EMAIL.
# `revelar --salida RUTA`: el archivo con las credenciales se genera dentro del contenedor, se copia a RUTA con modo 0600
# y se borra del contenedor; la contraseña nunca pasa por la salida estándar.
set -u
CONTENEDOR=${CONTENEDOR:-nap-handoff-api-1}
AQUI=$(cd "$(dirname "$0")" && pwd)
die() { echo "ERROR: $*" >&2; exit 1; }
docker cp "$AQUI/portal_ops.py" "$CONTENEDOR:/tmp/portal_ops.py" >/dev/null || die "no pude copiar portal_ops.py a $CONTENEDOR"
EJEC=(docker exec -w /app -e PYTHONPATH=/app -e NAP_ADMIN_EMAIL="${NAP_ADMIN_EMAIL:-admin@utn.frt.edu.ar}" "$CONTENEDOR" python /tmp/portal_ops.py)
if [ "${1:-}" = revelar ]; then
  ARGS=("$@"); SALIDA=""; INTERNA="/tmp/acceso-$$.json"
  for i in "${!ARGS[@]}"; do
    [ "${ARGS[$i]}" = "--salida" ] && { SALIDA=${ARGS[$((i+1))]}; ARGS[$((i+1))]=$INTERNA; }
  done
  [ -n "$SALIDA" ] || die "revelar requiere --salida RUTA"
  "${EJEC[@]}" "${ARGS[@]}" | sed "s|$INTERNA|$SALIDA|"
  if docker exec "$CONTENEDOR" test -f "$INTERNA"; then
    ( umask 077; docker cp "$CONTENEDOR:$INTERNA" "$SALIDA" >/dev/null ) && chmod 600 "$SALIDA"
    docker exec "$CONTENEDOR" rm -f "$INTERNA"
  fi
else
  "${EJEC[@]}" "$@"
fi
