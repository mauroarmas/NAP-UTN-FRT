#!/bin/bash
set -euo pipefail

# Versiones exactas instaladas por el lock del builder, nunca apt flotante.
/usr/lib/postgresql/16/bin/postgres --version | /usr/bin/grep -Eq '^postgres \(PostgreSQL\) 16\.'
test -x /usr/bin/pg_createcluster
test -x /usr/bin/psql
test -x /usr/bin/openssl
test -x /usr/sbin/runuser
test -x /usr/bin/python3
/usr/bin/systemctl mask postgresql.service postgresql@16-main.service
/usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0, '/opt/nap-build')
from common import configure_console
configure_console()
PY
# El saneador elimina después /var/lib/postgresql/16 y /etc/postgresql/16.
# La imagen no tiene una base inicializada que pueda escuchar antes del bootstrap.
