#!/bin/bash
set -euo pipefail
test "$EUID" -eq 0
test "$#" -eq 0
source_root=$(cd -- "$(dirname -- "$0")/../.." && pwd -P)
# Runtime aislado y revisión revisada. El operador prepara venv/dependencias fijadas.
test -x /opt/nap-builder/venv/bin/python
install -d -o root -g root -m 0700 /var/lib/nap-builder /var/lib/nap-builder/inputs
install -d -o root -g root -m 0755 /opt/nap-builder/runtime /opt/nap-builder/runtime/backend
# Un checkout revisado es necesario para verificar la revisión exacta de receta.
test -d /opt/nap-builder/runtime/.git
# No copiar ni actualizar implícitamente checkout, credenciales, registros ni red.
test "$(git -C /opt/nap-builder/runtime rev-parse HEAD)" = "$(git -C "$source_root" rev-parse HEAD)"
install -o root -g root -m 0755 "$source_root/infra/builder/nap-build-runner" /usr/local/sbin/nap-build-runner
