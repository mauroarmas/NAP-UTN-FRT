#!/bin/bash
set -euo pipefail
# Ejecutar explícitamente en el nodo, desde un checkout revisado. No configura
# SSH, sudo, registro, certificados ni cuenta de forma implícita.
test "$EUID" -eq 0
source_root=$(cd -- "$(dirname -- "$0")/../.." && pwd -P)
# La instalación común valida todas las versiones antes de escribir, conserva
# respaldo y revierte ante un fallo. --config/--previous son archivos privados
# del operador; no se reciben del portal ni del protocolo SSH.
/usr/bin/python3 -I "$source_root/infra/applications/install.py" --source-root "$source_root" "$@" --apply
install -d -o root -g root -m 0755 /opt/nap/runner /etc/nap/runner /etc/nap/runner/registry.d
install -d -o root -g root -m 0700 /var/lib/nap-runner
