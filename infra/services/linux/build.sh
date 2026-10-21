#!/bin/bash
set -euo pipefail

# El builder instaló todas las versiones exactas del lock y bloqueó el arranque
# de servicios durante apt. No se resuelven versiones flotantes aquí.
test -x /usr/bin/python3
test -x /usr/bin/sudo
test -x /bin/login
test -x /sbin/agetty
chmod 4755 /usr/bin/sudo
/usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0, '/opt/nap-build')
from bootstrap import configure_image
configure_image()
PY
