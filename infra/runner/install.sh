#!/bin/bash
set -euo pipefail
# Ejecutar explícitamente en el nodo, desde un checkout revisado. No configura
# SSH, sudo, registro, certificados ni cuenta de forma implícita.
test "$EUID" -eq 0
test "$#" -eq 0
source_root=$(cd -- "$(dirname -- "$0")/../.." && pwd -P)
install -d -o root -g root -m 0755 /opt/nap/runner /etc/nap/runner
install -d -o root -g root -m 0700 /var/lib/nap-runner
for name in nap_guest_runner.py node_executor.py; do
    install -o root -g root -m 0444 "$source_root/infra/runner/$name" "/opt/nap/runner/$name"
done
install -o root -g root -m 0444 "$source_root/backend/app/schemas/guest_runner.py" /opt/nap/runner/protocol.py
install -o root -g root -m 0755 "$source_root/infra/runner/nap-guest-runner" /usr/local/sbin/nap-guest-runner
