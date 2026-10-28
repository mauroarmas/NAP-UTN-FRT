#!/bin/bash
# Se ejecuta EN LA PC DEL OPERADOR. Copia imágenes y bundles a cada nodo y corre
# instalar_artefactos.py --apply (que NO sobrescribe y verifica hashes).
#
# Variables:
#   SRC        carpeta con los 6 .tar.gz + artifact-index.json + instalar_artefactos.py
#   NODES      IPs/hosts de los nodos (separados por espacio)
#   SSH_USER   usuario remoto con sudo sin contraseña (o root)
#   SSH_KEY    llave privada (opcional); sin ella usa el agente/contraseña
#
# Nota: con contraseña interactiva hay que correrlo en una terminal real (no con "!").
# En el laboratorio se usó un usuario "naprunner" temporal con sudo; ese usuario
# NO forma parte del diseño final (ver README, sección "Runner").
set -u
SRC=${SRC:-$HOME/.local/share/nap009}
NODES=${NODES:-"192.168.100.90 192.168.100.91 192.168.100.92 192.168.100.93"}
SSH_USER=${SSH_USER:-root}
SSH_KEY=${SSH_KEY:-}

H=$(sha256sum "$SRC/artifact-index.json" | cut -d' ' -f1)
OPTS="-o BatchMode=no"
[ -n "$SSH_KEY" ] && OPTS="$OPTS -i $SSH_KEY -o BatchMode=yes"
SUDO=""; [ "$SSH_USER" != root ] && SUDO="sudo"
STAGE=/home/$SSH_USER/nap009-src; [ "$SSH_USER" = root ] && STAGE=/root/nap009-src
DEST=/root/nap009-src

for node in $NODES; do
  host=$SSH_USER@$node
  echo "=== $node"
  ssh $OPTS "$host" "rm -rf $STAGE; mkdir -p $STAGE; $SUDO rm -rf $DEST" || { echo "FALLO: ssh"; continue; }
  scp $OPTS "$SRC"/*.tar.gz "$SRC/artifact-index.json" "$SRC/instalar_artefactos.py" "$host:$STAGE/" || { echo "FALLO: scp"; continue; }
  # El instalador exige origen de root, sin escritura de grupo/otros y ancestros seguros.
  ssh $OPTS "$host" "
    [ '$STAGE' = '$DEST' ] || $SUDO mv $STAGE $DEST
    $SUDO chown -R root:root $DEST && $SUDO chmod 755 $DEST &&
    $SUDO sh -c 'chmod 444 $DEST/*.tar.gz $DEST/artifact-index.json' &&
    $SUDO env LC_ALL=C python3 -I $DEST/instalar_artefactos.py --source $DEST --index-sha256 $H --apply" \
    && ssh $OPTS "$host" "$SUDO rm -rf $DEST; ls -l /var/lib/vz/template/cache/nap009-* /opt/nap/recipes/"
done
