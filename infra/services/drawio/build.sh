#!/bin/bash
set -euo pipefail
# Paquetes exactos ya instalados por el builder. Sólo fuentes con digest fijado.
test -x /usr/bin/java
test -x /usr/sbin/nginx
/usr/bin/python3 - <<'PY'
import sys,json
sys.path.insert(0,'/opt/nap-build')
from install import install_application
from common import configure_console
with open('/opt/nap-build/plan.json') as f: plan=json.load(f)
install_application(plan)
configure_console()
PY
rm -f /etc/nginx/sites-enabled/default
/usr/bin/systemctl mask nginx.service nap-drawio.service
