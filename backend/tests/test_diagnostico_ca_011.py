"""Hallazgos 6 y 7: diagnóstico seguro de excepciones y confianza explícita en la CA del portal."""
import datetime
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from app import worker
from app.services import ca_portal_service as ca
from app.services.application_profiles_service import verify_node_profile
from app.utils.diagnostico import resumen_excepcion

SECRETO = 'contrasena-privada-que-no-debe-aparecer'


def pem_publico():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CA de prueba')])
    now = datetime.datetime.now(datetime.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


# ---------- hallazgo 7 ----------

def lanzar():
    try:
        raise TimeoutError(f'la clave {SECRETO} agotó el tiempo')
    except TimeoutError:
        raise RuntimeError(f'falló con {SECRETO}') from None


def test_exception_summary_has_types_and_location_but_never_the_message():
    with pytest.raises(RuntimeError) as capturada:
        lanzar()
    texto = resumen_excepcion(capturada.value)
    assert SECRETO not in texto
    assert texto.startswith('RuntimeError <- TimeoutError en ')
    assert 'lanzar' in texto and 'test_diagnostico_ca_011.py' in texto
    assert '/home/' not in texto and '/tmp/' not in texto


def test_exception_summary_without_traceback_is_safe():
    assert resumen_excepcion(ValueError(SECRETO)) == 'ValueError en sin traza'


class Sesiones:
    def __init__(self, registro): self.registro = registro
    def __call__(self): return self
    async def __aenter__(self): return SimpleNamespace(commit=self._commit)
    async def __aexit__(self, *args): return False
    async def _commit(self): self.registro.append('commit')


async def test_worker_ingest_failure_records_a_specific_code_and_logs_origin_without_message(monkeypatch, caplog):
    registro = []
    async def habilitacion(db, componente): return None
    async def reclamar(db, **kwargs): return ('lease',)
    async def ceder(db, lease, **kwargs): registro.append(kwargs)
    async def heartbeat(sessions, lease): return None
    async def ingerir(sessions, lease, **kwargs): raise ca.CaPortalNoDisponible('ca_portal_no_configurada')
    monkeypatch.setattr('app.services.restauracion_service.exigir_habilitacion', habilitacion)
    monkeypatch.setattr(worker.operacion_service, 'reclamar', reclamar)
    monkeypatch.setattr(worker.operacion_service, 'ceder', ceder)
    monkeypatch.setattr(worker, '_heartbeat', heartbeat)
    monkeypatch.setattr('app.services.application_execution_service.ingerir_trabajo', ingerir)
    with caplog.at_level('ERROR'):
        assert await worker.procesar_ingesta_una(Sesiones([])) is True
    assert registro[0]['error_codigo'] == 'ca_portal_no_configurada'
    assert 'APPLICATION_GATEWAY_CA_FILE' in registro[0]['error_detalle_seguro']
    assert 'CaPortalNoDisponible' in caplog.text and 'InfraNoVerificable' not in caplog.text.split('CaPortalNoDisponible')[0]


async def test_worker_generic_failure_keeps_old_codes_and_hides_the_message(monkeypatch, caplog):
    registro = []
    async def habilitacion(db, componente): return None
    async def reclamar(db, **kwargs): return ('lease',)
    async def ceder(db, lease, **kwargs): registro.append(kwargs)
    async def heartbeat(sessions, lease): return None
    async def ingerir(sessions, lease, **kwargs): raise RuntimeError(SECRETO)
    monkeypatch.setattr('app.services.restauracion_service.exigir_habilitacion', habilitacion)
    monkeypatch.setattr(worker.operacion_service, 'reclamar', reclamar)
    monkeypatch.setattr(worker.operacion_service, 'ceder', ceder)
    monkeypatch.setattr(worker, '_heartbeat', heartbeat)
    monkeypatch.setattr('app.services.application_execution_service.ingerir_trabajo', ingerir)
    with caplog.at_level('ERROR'):
        await worker.procesar_ingesta_una(Sesiones([]))
    assert registro[0]['error_codigo'] == 'consola_no_confirmada'
    assert 'RuntimeError' in caplog.text and SECRETO not in caplog.text


# ---------- hallazgo 6 ----------

def test_ca_status_distinguishes_missing_unreadable_and_invalid(tmp_path):
    assert ca.estado_ca_portal('') == 'ca_portal_no_configurada'
    assert ca.estado_ca_portal(str(tmp_path/'no-existe.crt')) == 'ca_portal_ilegible'
    assert ca.estado_ca_portal(str(tmp_path)) == 'ca_portal_ilegible'
    sin_pem = tmp_path/'a.crt'; sin_pem.write_text('texto cualquiera')
    assert ca.estado_ca_portal(str(sin_pem)) == 'ca_portal_invalida'
    roto = tmp_path/'b.crt'; roto.write_text('-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n')
    assert ca.estado_ca_portal(str(roto)) == 'ca_portal_invalida'
    bueno = tmp_path/'c.crt'; bueno.write_text(pem_publico())
    assert ca.estado_ca_portal(str(bueno)) is None


def test_private_key_material_is_not_a_valid_ca_file(tmp_path):
    clave = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    archivo = tmp_path/'ca.key'; archivo.write_text(clave)
    assert ca.estado_ca_portal(str(archivo)) == 'ca_portal_invalida'


@pytest.mark.parametrize('codigo', ['ca_portal_no_configurada', 'ca_portal_ilegible', 'ca_portal_invalida'])
def test_pending_verification_error_carries_fixed_code_and_text(codigo):
    error = ca.CaPortalNoDisponible(codigo)
    assert error.codigo_seguro == codigo and error.detalle_seguro == ca.MENSAJES[codigo] and error.incierto


def entrada(tmp_path):
    clave = tmp_path/'key'; clave.write_text('fake-key-not-used'); clave.chmod(0o600)
    hosts = tmp_path/'known_hosts'; hosts.write_text('pve-test.invalid ssh-ed25519 TEST-ONLY'); hosts.chmod(0o644)
    return {'host': 'pve-test.invalid', 'user': 'naprunner', 'port': 22,
            'private_key_path': str(clave), 'known_hosts_path': str(hosts)}


@pytest.mark.parametrize('archivo, esperado', [('', 'ca_portal_no_configurada'), ('/no/existe.crt', 'ca_portal_ilegible')])
async def test_approval_rejects_before_any_ssh_when_portal_cannot_trust_the_ca(tmp_path, monkeypatch, archivo, esperado):
    import asyncio
    async def prohibido(*args, **kwargs): pytest.fail('No se abre SSH si el portal no puede verificar el TLS')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', prohibido)
    settings = SimpleNamespace(runner_nodes={'pve1': entrada(tmp_path)}, application_gateway_ca_file=archivo)
    with pytest.raises(HTTPException) as error:
        await verify_node_profile({'id': 'docker-ubuntu24', 'revision': 4, 'sha256': 'a' * 64}, node='pve1', settings=settings)
    assert error.value.status_code == 409 and error.value.detail['codigo'] == esperado
    assert 'clave privada' in error.value.detail['mensaje'] or 'certificado' in error.value.detail['mensaje'] or 'archivo' in error.value.detail['mensaje']


async def test_final_verification_stops_with_a_specific_code_before_touching_the_database(monkeypatch):
    from app.config import get_settings
    from app.services.application_verification_service import verify
    monkeypatch.setattr(get_settings(), 'application_gateway_ca_file', '')
    with pytest.raises(ca.CaPortalNoDisponible) as error:
        await verify(None, None)
    assert error.value.codigo_seguro == 'ca_portal_no_configurada'


def test_container_mount_prefix_is_not_duplicated():
    from app.utils import diagnostico
    class Marco:
        filename = '/app/app/services/x.py'; lineno = 7; name = 'f'
    original = diagnostico.traceback.extract_tb
    diagnostico.traceback.extract_tb = lambda tb: [Marco()]
    try:
        try:
            raise ValueError(SECRETO)
        except ValueError as capturado:
            error = capturado
        assert diagnostico.resumen_excepcion(error) == 'ValueError en app/services/x.py:7 f'
    finally:
        diagnostico.traceback.extract_tb = original
