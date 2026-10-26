# Herramienta explícita del operador. La base local debe importarse solo después
# de comprobar SHA256SUMS y su firma oficial. No ejecutar servicios ni publicar
# esta imagen: contiene estado de paquetes anterior al saneamiento del builder.
ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE}
ARG PRODUCT
ARG REFRESH_APT_INDEXES=true
COPY resolve_packages.py /opt/nap-resolution/resolve_packages.py
RUN set -eu; \
    case "$PRODUCT" in \
      linux) extra="" ;; \
      drawio) extra="openjdk-21-jre-headless nginx" ;; \
      postgresql) extra="postgresql-16 postgresql-client-16" ;; \
      bookstack) extra="mariadb-server nginx php8.3-fpm php8.3-cli php8.3-mysql php8.3-gd php8.3-curl php8.3-mbstring php8.3-xml php8.3-zip php8.3-intl php8.3-bcmath php8.3-ldap composer unzip" ;; \
      *) exit 1 ;; \
    esac; \
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; \
    chmod 0755 /usr/sbin/policy-rc.d; \
    case "$REFRESH_APT_INDEXES" in \
      true) apt-get -o Acquire::Languages=none update ;; \
      false) ls /var/lib/apt/lists/*_InRelease >/dev/null ;; \
      *) exit 1 ;; \
    esac; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus udev python3 sudo util-linux passwd login \
      iproute2 iputils-ping openssl ca-certificates curl $extra; \
    python3 /opt/nap-resolution/resolve_packages.py "$PRODUCT"
