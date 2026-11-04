#!/usr/bin/env bash
# Crea (o actualiza) el rol de Proxmox que permite SOLO abrir la consola de un contenedor.
# Se ejecuta como root en cualquier nodo del clúster: los roles son del clúster.
# Sin --aplicar sólo muestra lo que haría.
#
#   crear-rol-consola.sh [--aplicar] [--privilegios "VM.Console VM.Audit"]
#
# El rol NO incluye energía, configuración, copias ni acceso a nodos o almacenamiento:
# la excepción de consola de la constitución cubre únicamente la sesión interactiva.
set -euo pipefail

ROL="${NAP_ROL_CONSOLA:-NapConsola}"
PRIVS="VM.Console"
APLICAR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --aplicar) APLICAR=1 ;;
    --privilegios) PRIVS="$2"; shift ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
  shift
done

# Rechazar privilegios que amplían la excepción (energía, configuración, administración).
for privilegio in $PRIVS; do
  case "$privilegio" in
    VM.Console|VM.Audit|Pool.Audit|Sys.Audit|Sys.Console) ;;
    *) echo "privilegio no permitido en el rol de consola: $privilegio" >&2; exit 2 ;;
  esac
done

if pveum role list --output-format json | grep -q "\"roleid\":\"$ROL\""; then
  ACCION=modify
else
  ACCION=add
fi
echo "rol: $ROL  acción: $ACCION  privilegios: ${PRIVS// /,}"
if [ "$APLICAR" -ne 1 ]; then
  echo "(plan; use --aplicar para ejecutar)"
  exit 0
fi
pveum role "$ACCION" "$ROL" --privs "${PRIVS// /,}"
pveum role list --output-format json | python3 -c "
import json,sys
for r in json.load(sys.stdin):
    if r['roleid']=='$ROL': print('listo:', r['roleid'], r.get('privs',''))"
