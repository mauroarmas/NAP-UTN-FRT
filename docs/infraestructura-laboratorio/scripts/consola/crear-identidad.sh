#!/usr/bin/env bash
# Crea una identidad individual de consola y le da el rol de consola SOLO sobre el pool de su cátedra.
# Se ejecuta como root en un nodo. Sin --aplicar sólo muestra lo que haría.
#
#   crear-identidad.sh --usuario <usuario>@<dominio> --pool catedra-<N> [--sin-clave] [--aplicar]
#
# La contraseña (dominio `pve`) se lee de la entrada estándar, dos veces; nunca por argumento. Con --sin-clave
# no se fija ninguna: la persona la establece con `pveum passwd <identidad>` en una terminal propia del nodo.
# Una identidad pertenece a UNA persona: no se reutiliza ni se comparte. `root@pam` está prohibida.
set -euo pipefail

ROL="${NAP_ROL_CONSOLA:-NapConsola}"
USUARIO=""; POOL=""; APLICAR=0; SIN_CLAVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --usuario) USUARIO="$2"; shift ;;
    --pool) POOL="$2"; shift ;;
    --sin-clave) SIN_CLAVE=1 ;;
    --aplicar) APLICAR=1 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
  shift
done
[[ "$USUARIO" =~ ^[A-Za-z0-9._-]{1,100}@[A-Za-z0-9._-]{1,60}$ ]] || { echo "usuario inválido" >&2; exit 2; }
[ "${USUARIO,,}" != "root@pam" ] || { echo "root@pam no puede ser identidad de consola" >&2; exit 2; }
[[ "$POOL" =~ ^catedra-[0-9]+$ ]] || { echo "pool inválido (se espera catedra-<N>)" >&2; exit 2; }
pveum role list --output-format json | grep -q "\"roleid\":\"$ROL\"" || { echo "falta el rol $ROL (crear-rol-consola.sh)" >&2; exit 1; }
pvesh get "/pools/$POOL" >/dev/null 2>&1 || { echo "el pool $POOL no existe" >&2; exit 1; }

REALM="${USUARIO#*@}"
EXISTE=0
pveum user list --output-format json | grep -q "\"userid\":\"$USUARIO\"" && EXISTE=1
echo "identidad: $USUARIO  pool: /pool/$POOL  rol: $ROL  existente: $EXISTE"
if [ "$APLICAR" -ne 1 ]; then
  echo "(plan; use --aplicar para ejecutar)"
  exit 0
fi
if [ "$EXISTE" -eq 0 ]; then
  pveum user add "$USUARIO" --comment "Consola NAP (identidad individual)"
  if [ "$REALM" = "pve" ] && [ "$SIN_CLAVE" -eq 0 ]; then
    # Lee la contraseña de la entrada estándar sin exponerla en la lista de procesos.
    pveum passwd "$USUARIO"
  fi
fi
pveum acl modify "/pool/$POOL" --users "$USUARIO" --roles "$ROL"
echo "permisos efectivos:"
pveum user permissions "$USUARIO" --output-format json
