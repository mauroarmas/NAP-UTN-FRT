#!/usr/bin/env bash
# Retira el acceso de consola de una identidad en fases independientes:
#   acl        quita el rol de consola del pool de la cátedra (impide sesiones NUEVAS)
#   identidad  elimina la identidad (invalida sus tickets de sesión guardados)
#   sesiones   termina las sesiones de consola ya abiertas de un contenedor
#   todas      las tres, en ese orden (por omisión)
# Se ejecuta como root. Sin --aplicar sólo muestra lo que haría.
#
#   retirar-acceso.sh --usuario <usuario>@<dominio> [--pool catedra-<N>] [--vmid <id>] [--fase acl|identidad|sesiones|todas] [--aplicar]
#
# La sesión abierta la sostiene un proceso `termproxy` del nodo POR EL QUE ENTRÓ la persona, que puede ser
# distinto del nodo que aloja el contenedor, y verifica el permiso sólo al conectar. Por eso la fase `sesiones`
# debe ejecutarse en CADA nodo del clúster. Quitar la ACL por sí sola NO termina una consola abierta; el
# resultado se comprueba con ensayo-revocacion.py y se registra como evidencia.
set -euo pipefail

ROL="${NAP_ROL_CONSOLA:-NapConsola}"
USUARIO=""; POOL=""; VMID=""; FASE="todas"; APLICAR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --usuario) USUARIO="$2"; shift ;;
    --pool) POOL="$2"; shift ;;
    --vmid) VMID="$2"; shift ;;
    --fase) FASE="$2"; shift ;;
    --aplicar) APLICAR=1 ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
  shift
done
[[ "$USUARIO" =~ ^[A-Za-z0-9._-]{1,100}@[A-Za-z0-9._-]{1,60}$ ]] || { echo "usuario inválido" >&2; exit 2; }
[ "${USUARIO,,}" != "root@pam" ] || { echo "root@pam no se retira con este procedimiento" >&2; exit 2; }
[ -z "$POOL" ] || [[ "$POOL" =~ ^catedra-[0-9]+$ ]] || { echo "pool inválido (se espera catedra-<N>)" >&2; exit 2; }
case "$FASE" in acl|identidad|sesiones|todas) ;; *) echo "fase inválida" >&2; exit 2 ;; esac
hace() { [ "$FASE" = todas ] || [ "$FASE" = "$1" ]; }
if hace acl && [ -z "$POOL" ]; then echo "la fase acl necesita --pool" >&2; exit 2; fi
if hace sesiones && [ -z "$VMID" ]; then echo "la fase sesiones necesita --vmid" >&2; exit 2; fi
[ -z "$VMID" ] || [[ "$VMID" =~ ^[0-9]+$ ]] || { echo "vmid inválido" >&2; exit 2; }

PATRON="termproxy .*--path /vms/${VMID:-0}( |$)"
echo "retirar: $USUARIO  fase: $FASE  pool: ${POOL:-—}  contenedor: ${VMID:-—}"
if hace sesiones; then
  echo "procesos de consola del contenedor $VMID en este nodo:"
  pgrep -af "$PATRON" || echo "  (ninguno)"
fi
if [ "$APLICAR" -ne 1 ]; then
  echo "(plan; use --aplicar para ejecutar)"
  exit 0
fi

if hace acl; then
  pveum acl delete "/pool/$POOL" --users "$USUARIO" --roles "$ROL"
  echo "ACL retirada de /pool/$POOL"
fi
if hace identidad; then
  pveum user delete "$USUARIO"
  echo "identidad eliminada"
fi
if hace sesiones; then
  if pkill -f "$PATRON"; then echo "sesiones de consola terminadas en este nodo"; else echo "sin sesiones de consola en este nodo"; fi
fi
