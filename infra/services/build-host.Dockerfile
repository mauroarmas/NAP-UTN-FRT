# Host efímero del operador; BASE_IMAGE debe ser una base verificada localmente.
# No montar Docker socket, datos operativos ni / del host dentro del constructor.
ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE}
COPY host-requirements.lock /opt/nap-tools/requirements.lock
RUN set -eu; \
    test -x /usr/bin/python3; \
    DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends git python3-venv; \
    python3 -m venv /opt/nap-tools/venv; \
    /opt/nap-tools/venv/bin/python -m pip install --no-cache-dir --require-hashes -r /opt/nap-tools/requirements.lock
ENV PYTHONPATH=/source/backend:/source
WORKDIR /source
ENTRYPOINT ["/opt/nap-tools/venv/bin/python", "-m", "infra.services.build_image"]
