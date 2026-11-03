#!/bin/bash
# EN LA PC DEL OPERADOR. Consulta SQL al Postgres del portal del laboratorio (contenedor db). Pensado para LECTURA:
# estado de servicios, pedidos y operaciones. No cambiar datos con esto (usar portal.sh para operar).
# Uso: consulta-sql.sh "select id, estado from servicios order by id desc limit 3"
set -u
[ $# -eq 1 ] || { echo "uso: $0 \"SQL\"" >&2; exit 2; }
docker exec -i "${CONTENEDOR_DB:-nap-handoff-db-1}" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<< "$1"
