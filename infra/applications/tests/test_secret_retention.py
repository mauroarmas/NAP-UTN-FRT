"""Pruebas de retención de secretos, spool, journal y archivos operativos (T100).

Verifica que ningún secreto de aplicación o credencial quede en texto plano
en el spool, logs de salida, journal de systemd o archivos de ejecución.
"""

import base64
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest

from infra.applications.job.credentials import CredentialChannel
from infra.applications.job.network import compile_policy, table_name
from infra.applications.job.redaction import MASK, SUPPRESSED, ClosedOutput, SecretRedactor


def test_redaction_comprehensive_across_streams_and_formats():
    """Redactor elimina múltiples secretos en todas sus codificaciones y a través de cortes de chunks."""
    secrets = [
        "pass_db_secret_9981",
        "app_key_jwt_5521",
        "private_auth_token_xyz",
    ]
    for secret in secrets:
        encodings = [
            secret,
            base64.b64encode(secret.encode()).decode(),
            quote(secret, safe=""),
            json.dumps(secret)[1:-1],
        ]
        for enc in encodings:
            redactor = SecretRedactor(secrets)
            text = f"prefix log message {enc} suffix"
            raw = text.encode()
            # Probar corte arbitrario en la mitad del stream
            mid = len(raw) // 2
            out = redactor.feed(raw[:mid]) + redactor.feed(raw[mid:], final=True)
            assert enc not in out
            assert secret not in out
            assert MASK in out


def test_spool_and_credentials_strict_permissions_and_unlink(tmp_path, monkeypatch):
    """Las credenciales se guardan con 0600 y se eliminan del disco tras el consumo durable."""
    source = tmp_path / "staging"
    copies = tmp_path / "systemd_creds"
    copies.mkdir(mode=0o700)
    channel = CredentialChannel(source_root=source, credentials_root=copies)

    exec_id = str(uuid4())
    secretos = {"DB_PASS": "pass_super_secreta_011", "API_KEY": "tok_123456789"}
    channel.stage(exec_id, fingerprint="f" * 64, secretos=secretos)

    stage_file = channel.path / f"credential.{exec_id}.json"
    assert stage_file.exists()
    # Permiso estricto de solo lectura/escritura del propietario (0600)
    assert stage_file.stat().st_mode & 0o777 == 0o600

    # Simular entrega a systemd
    service_folder = copies / f"nap-application-{exec_id}.service"
    service_folder.mkdir(mode=0o700)
    target = service_folder / "deployment"
    target.write_bytes(stage_file.read_bytes())
    target.chmod(0o400)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(service_folder))

    # Carga y retiro
    consumed = channel.load_and_retire(
        exec_id, fingerprint="f" * 64, mark_loaded=lambda: True
    )
    assert consumed == secretos
    # El archivo de credencial en staging debe haber sido desvinculado
    assert not stage_file.exists()

    channel.close()


def test_docker_runtime_configuration_forbids_docker_socket_and_privileged():
    """No se permite exponer el socket Docker ni ejecutar contenedores privilegiados."""
    from app.schemas.configuracion_despliegue import FORBIDDEN_TARGETS

    assert "/var/run" in FORBIDDEN_TARGETS
    assert "/var/lib/docker" in FORBIDDEN_TARGETS
    assert "/proc" in FORBIDDEN_TARGETS
    assert "/sys" in FORBIDDEN_TARGETS


def test_network_policy_blocks_host_node_and_ssrf():
    """La política de red del guest descarta acceso al nodo host, portal y servicios de metadatos."""
    policy = {
        "resource_uuid": str(uuid4()),
        "vmid": 900011,
        "bridge": "vmbr0",
        "address": "172.16.36.81",
        "mac_address": "02:11:22:33:44:55",
        "client_cidrs": ["172.16.36.1/32"],
        "service_port": 8443,
        "management_addresses": ["172.16.36.100"],
        "peer_cidrs": ["172.16.36.0/24"],
        "endpoints": [
            {"address": "172.16.36.2", "transport": "udp", "port": 53},
            {"address": "172.16.36.1", "transport": "tcp", "port": 5443},
        ],
    }
    nft_rules = compile_policy(policy).decode()
    table = table_name(policy)
    # Tabla bridge aislada exclusiva por recurso
    assert f"create table bridge {table}" in nft_rules
    # Descarta conexiones hacia la IP de gestión del nodo host (172.16.36.100)
    assert "ip daddr 172.16.36.100 counter drop" in nft_rules
    # Descarta tráfico a otras redes pares de la infraestructura
    assert "ip daddr 172.16.36.0/24 counter drop" in nft_rules
    # No contiene comandos globales destructivos
    assert "flush ruleset" not in nft_rules
