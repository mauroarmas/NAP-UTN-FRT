#!/bin/bash
# Se ejecuta COMO ROOT EN CADA NODO Proxmox (no en la PC del operador).
# Uso:  ssh root@NODO 'bash -s' < preparar-nodo.sh      (o scp + ejecutar)
#
# Qué hace (pensado para laboratorio sin suscripción):
#   1. fija DNS (el resolv.conf heredado de otra red dejó los nodos sin resolución)
#   2. cambia los repos enterprise por pve-no-subscription
#   3. instala sudo
# En servidores reales: revisar cada paso. Con suscripción NO se tocan los repos
# enterprise; los DNS son los de la institución.
#
# Variables opcionales: DNS1, DNS2, SUITE (trixie = PVE 9, bookworm = PVE 8)
export LC_ALL=C DEBIAN_FRONTEND=noninteractive
DNS1=${DNS1:-192.168.100.1}
DNS2=${DNS2:-8.8.8.8}
SUITE=${SUITE:-trixie}
APT="-o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o Acquire::Retries=0"

pkill apt-get 2>/dev/null; sleep 1
echo "--- resolv.conf anterior:"; cat /etc/resolv.conf
printf 'nameserver %s\nnameserver %s\n' "$DNS1" "$DNS2" > /etc/resolv.conf
echo "--- DNS:"; getent hosts download.proxmox.com || echo "NO resuelve download.proxmox.com"

rm -f /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources
cat > /etc/apt/sources.list.d/pve-no-subscription.sources <<REPO
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: $SUITE
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
REPO

echo "--- apt update:";       apt-get $APT update </dev/null
echo "--- apt install sudo:"; apt-get $APT install -y sudo </dev/null
sudo -V | head -1
