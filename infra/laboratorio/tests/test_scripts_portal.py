"""Herramientas de operación del portal del laboratorio: lo que se puede comprobar sin infraestructura ni subprocesos."""
import datetime
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[3]/'docs/infraestructura-laboratorio/scripts/portal'


def cargar(nombre):
    sys.path.insert(0, str(PORTAL))   # los clientes se importan entre sí
    spec = importlib.util.spec_from_file_location('portal_' + nombre, PORTAL/(nombre + '.py'))
    modulo = importlib.util.module_from_spec(spec); spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope='module')
def ops():
    return cargar('portal_ops')


@pytest.mark.parametrize('archivo', sorted(p.name for p in PORTAL.glob('*.py')))
def test_every_python_tool_compiles(archivo):
    compile((PORTAL/archivo).read_text(), archivo, 'exec')


def test_portal_ops_imports_the_backend_only_inside_functions(ops):
    # Los imports del backend son perezosos: el analizador de argumentos y la guarda de cuentas no lo necesitan.
    en_modulo = [l for l in (PORTAL/'portal_ops.py').read_text().splitlines() if l.startswith(('from app', 'import app'))]
    assert en_modulo == [] and callable(ops.build_parser)


def test_account_switch_only_accepts_the_seed_admin_or_synthetic_accounts(ops):
    assert ops.email_permitido_para_cuenta('admin@utn.frt.edu.ar')
    assert ops.email_permitido_para_cuenta('lab-aislamiento-b@lab.invalid')
    for ajena in ('mauro.armas101@gmail.com', 'ivanochoa229@gmail.com', 'admin@utn.frt.edu.ar.evil.com', 'x@lab.invalid.com'):
        assert not ops.email_permitido_para_cuenta(ajena)


def test_every_mutating_command_requires_an_idempotency_key(ops):
    parser = ops.build_parser()
    casos = [['oferta'], ['pedido', '--usuario', 'a@b', '--catedra', '1', '--nodo', 'n'],
             ['orden', '--servicio', '1', '--accion', 'detener', '--usuario', 'a@b'], ['reparar', '--pedido', '1']]
    for argumentos in casos:
        with pytest.raises(SystemExit):
            parser.parse_args(argumentos)
    ok = parser.parse_args(['pedido', '--usuario', 'a@b', '--catedra', '3', '--nodo', 'pve91', '--clave', 'k'])
    assert (ok.cmd, ok.catedra, ok.dias, ok.storage, ok.sin_aprobar) == ('pedido', 3, 14, 'truenas', False)


def test_actions_are_closed_and_reveal_requires_an_output_file(ops):
    parser = ops.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(['orden', '--servicio', '1', '--accion', 'destruir', '--usuario', 'a@b', '--clave', 'k'])
    with pytest.raises(SystemExit):
        parser.parse_args(['revelar', '--servicio', '1', '--usuario', 'a@b'])
    with pytest.raises(SystemExit):
        parser.parse_args(['cuenta'])   # exige --activar o --desactivar


def test_tools_never_print_secrets():
    texto = (PORTAL/'portal_ops.py').read_text()
    # La contraseña sólo viaja al archivo de salida 0600, nunca a print.
    for linea in texto.splitlines():
        if 'print(' in linea:
            assert 'password' not in linea.lower() and 'ca_pem' not in linea
    assert 'O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600' in texto


def test_client_rejects_a_bad_ca_and_wrong_arguments():
    cliente = cargar('acceso_mariadb')
    with pytest.raises(Exception):
        cliente.contexto_tls({'ca': 'no es un certificado'})
    with pytest.raises(SystemExit):
        cliente.main(['x', 'borrar', 'a', 'b'])
    with pytest.raises(SystemExit):
        cargar('aislamiento_catedras').main(['x', 'solo-uno.json'])


def test_client_accepts_a_public_ca_bundle():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    cliente = cargar('acceso_mariadb')
    def ca(nombre):
        clave = ec.generate_private_key(ec.SECP256R1()); n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombre)])
        ahora = datetime.datetime.now(datetime.UTC)
        cert = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(clave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ahora).not_valid_after(ahora + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(clave, hashes.SHA256()))
        return cert.public_bytes(serialization.Encoding.PEM).decode()
    contexto = cliente.contexto_tls({'ca': ca('CA pve91') + ca('CA frt')})   # un conjunto, como el que entrega el portal
    assert contexto.verify_mode.name == 'CERT_REQUIRED' and contexto.check_hostname


def test_network_probe_classifies_each_outcome(monkeypatch):
    sondeo = cargar('sondeo_red')
    resultados = {'ok': None, 'tiempo': socket.timeout(), 'rst': ConnectionRefusedError(), 'otro': OSError(113, 'No route to host')}
    class Falso:
        def __init__(self, caso=None): self.caso = caso
        def settimeout(self, espera): pass
        def connect(self, destino):
            error = resultados[destino[0]]
            if error is not None: raise error
        def close(self): pass
    monkeypatch.setattr(sondeo.socket, 'socket', lambda: Falso())
    assert sondeo.sondear('ok', 3306) == 'ALCANZA'
    assert sondeo.sondear('tiempo', 22) == 'bloqueado (sin respuesta)'
    assert sondeo.sondear('rst', 22) == 'rechazado (RST)'
    assert sondeo.sondear('otro', 22).startswith('bloqueado (')
