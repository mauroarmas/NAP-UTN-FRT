"""Registry de ensayo privado: TLS, publicación inicial y luego sólo lectura.

Herramienta técnica local; no instala Docker en Proxmox ni gestiona el catálogo.
Secretos únicamente en el directorio privado del operador y archivos montados.
"""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler


REGISTRY_IMAGE = 'registry@sha256:d4032d4cc323c1731c707931ecada07a53076eac38e3b61ae57533f170f2c6c3'
COPY_IMAGE = 'quay.io/skopeo/stable@sha256:e1fcbe25df701981eab0b3654c03fae118aa72bc521c10a2f7c28ad88cd2d700'
CONTAINER = 'nap011-registry'
ENDPOINT = 'https://172.16.36.1:5443'
IMAGE = 'nap011-campus-demo:acceptance'
LABEL = 'nap.bootstrap=011-registry'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def docker(*args):
    return subprocess.run(['docker', *map(str, args)], check=True, text=True,
                          timeout=180, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(data if isinstance(data, bytes) else data.encode())


def create_credentials(root):
    import bcrypt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ('pki', 'data', 'auth', 'certs'):
        (root / name).mkdir(mode=0o700)
    now = datetime.now(timezone.utc)
    ca_key, server_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'NAP 011 registry laboratorio')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=60))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    certificate = (x509.CertificateBuilder().subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, '172.16.36.1')])).issuer_name(ca_name)
        .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('172.16.36.1'))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
    for name, key in [('ca.key', ca_key), ('server.key', server_key)]:
        private_write(root / 'pki' / name, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private_write(root / 'pki' / 'server.crt', certificate.public_bytes(serialization.Encoding.PEM))
    public_ca = ca.public_bytes(serialization.Encoding.PEM)
    private_write(root / 'pki' / 'ca.crt', public_ca)
    private_write(root / 'certs' / 'ca.crt', public_ca)
    accounts = {name: secrets.token_urlsafe(32) for name in ('nap011reader', 'nap011publisher')}
    htpasswd = ''.join(name + ':' + bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode() + '\n'
                       for name, secret in accounts.items())
    private_write(root / 'auth' / 'htpasswd', htpasswd)
    private_write(root / 'accounts.json', json.dumps(accounts))
    auth = base64.b64encode(('nap011publisher:' + accounts['nap011publisher']).encode()).decode()
    private_write(root / 'auth' / 'publisher.json', json.dumps({'auths': {'172.16.36.1:5443': {'auth': auth}}}))
    http_secret = secrets.token_hex(32)
    for mode in ('read', 'write'):
        # Archivos distintos e inmutables: no depender de reemplazar un bind mount en vivo.
        config = f'''version: 0.1
log:
  level: error
  accesslog:
    disabled: true
storage:
  filesystem:
    rootdirectory: /var/lib/registry
  maintenance:
    readonly:
      enabled: {'true' if mode == 'read' else 'false'}
http:
  addr: :5000
  secret: {http_secret}
  tls:
    certificate: /pki/server.crt
    key: /pki/server.key
auth:
  htpasswd:
    realm: nap011
    path: /auth/htpasswd
'''
        private_write(root / f'registry-{mode}.yml', config)


def owned_container():
    result = subprocess.run(['docker', 'inspect', CONTAINER], text=True, timeout=15,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        # Diferenciar ausente de daemon inaccesible; no crear a ciegas después de un fallo.
        docker('info', '--format', '{{.ServerVersion}}')
        return False
    value = json.loads(result.stdout)[0]
    if (value['Config'].get('Labels', {}).get('nap.bootstrap') != '011-registry'
            or value['Config']['Image'] != REGISTRY_IMAGE):
        raise ValueError('REGISTRY_NAME_OCCUPIED')
    return True


def run_registry(root, *, readonly):
    if owned_container():
        docker('rm', '-f', CONTAINER)
    args = ['run', '-d', '--name', CONTAINER, '--label', LABEL, '--restart', 'unless-stopped',
            '--user', f'{os.geteuid()}:{os.getegid()}',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '256m', '--pids-limit', '128', '--log-driver', 'none',
            '--publish', '172.16.36.1:5443:5000', '--env', 'OTEL_TRACES_EXPORTER=none']
    for source, target, writable in [
        (root / ('registry-read.yml' if readonly else 'registry-write.yml'), '/etc/distribution/config.yml', False),
        (root / 'pki/server.crt', '/pki/server.crt', False),
        (root / 'pki/server.key', '/pki/server.key', False),
        (root / 'auth/htpasswd', '/auth/htpasswd', False), (root / 'data', '/var/lib/registry', True),
    ]:
        args += ['--mount', f'type=bind,source={source},target={target}' + ('' if writable else ',readonly')]
    docker(*args, REGISTRY_IMAGE)


def verify(root, *, readonly):
    live = json.loads(docker('inspect', CONTAINER))[0]
    mounts = {item['Destination'] for item in live['Mounts']}
    expected = {'/etc/distribution/config.yml', '/pki/server.crt', '/pki/server.key',
                '/auth/htpasswd', '/var/lib/registry'}
    if (mounts != expected or live['Config']['User'] != f'{os.geteuid()}:{os.getegid()}'
            or not live['HostConfig']['ReadonlyRootfs']
            or live['HostConfig']['LogConfig']['Type'] != 'none'):
        raise ValueError('REGISTRY_ISOLATION_NOT_CONFIRMED')
    accounts = json.loads((root / 'accounts.json').read_text())
    context = ssl.create_default_context(cafile=str(root / 'pki' / 'ca.crt'))
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    auth = 'Basic ' + base64.b64encode(('nap011reader:' + accounts['nap011reader']).encode()).decode()
    def status(path, *, authenticated=False, method='GET'):
        headers = {'Accept': 'application/vnd.oci.image.manifest.v1+json, '
                   'application/vnd.docker.distribution.manifest.v2+json'}
        if authenticated:
            headers['Authorization'] = auth
        req = Request(ENDPOINT + path, headers=headers, method=method)
        try:
            with opener.open(req, timeout=3) as response:
                return response.status
        except HTTPError as exc:
            return exc.code
    for _ in range(30):
        try:
            if status('/v2/') == 401 and status('/v2/', authenticated=True) == 200:
                break
        except OSError:
            pass
        time.sleep(.2)
    else:
        raise ValueError('REGISTRY_TLS_AUTH_NOT_CONFIRMED')
    if readonly:
        if status('/v2/nap/campus-demo/blobs/uploads/', authenticated=True, method='POST') not in {405, 503}:
            raise ValueError('REGISTRY_READ_ONLY_NOT_CONFIRMED')
        # HEAD no descarga capas ni expone el cuerpo de la imagen.
        if status('/v2/nap/campus-demo/manifests/acceptance', authenticated=True, method='HEAD') != 200:
            raise ValueError('REGISTRY_IMAGE_NOT_CONFIRMED')


def prepare(root, *, apply=False):
    root = Path(root).absolute()
    plan = {'endpoint': ENDPOINT, 'scope': 'laboratorio_local', 'profiles_enabled': [],
            'actions': ['TLS y autenticación privada', 'Publicar fixture campus-demo', 'Bloquear escrituras']}
    if not apply:
        return {**plan, 'state': 'plan_without_changes'}
    if root.exists() and (root.is_symlink() or root.stat().st_uid != os.geteuid()
                          or root.stat().st_mode & 0o077):
        raise ValueError('UNTRUSTED_PRIVATE_DIRECTORY')
    if not root.exists():
        if owned_container():
            raise ValueError('REGISTRY_PRIVATE_STATE_MISSING')
        create_credentials(root)
    complete = root / 'complete.json'
    if complete.exists():
        verify(root, readonly=True)
        return {**plan, 'state': 'registry_ready_read_only'}
    # Estado parcial se conserva privado. Un error no imprime logs ni destruye datos del registry.
    archive = root / 'campus-demo.tar'
    try:
        run_registry(root, readonly=False)
        verify(root, readonly=False)
        docker('save', '--output', archive, IMAGE)
        archive.chmod(0o600)
        docker('run', '--rm', '--network', 'host', '--cap-drop', 'ALL',
               '--log-driver', 'none', '--label', 'nap.bootstrap=011-copy',
               '--user', f'{os.geteuid()}:{os.getegid()}',
               '--security-opt', 'no-new-privileges',
               '--mount', f'type=bind,source={archive},target=/image.tar,readonly',
               '--mount', f'type=bind,source={root / "auth/publisher.json"},target=/auth.json,readonly',
               '--mount', f'type=bind,source={root / "certs"},target=/certs,readonly',
               COPY_IMAGE, 'copy', '--dest-cert-dir', '/certs', '--dest-authfile', '/auth.json',
               'docker-archive:/image.tar', 'docker://172.16.36.1:5443/nap/campus-demo:acceptance')
    finally:
        # Cerrar la ventana de escritura incluso si la copia falla.
        run_registry(root, readonly=True)
        if archive.exists():
            archive.unlink()
    verify(root, readonly=True)
    public = {**plan, 'state': 'registry_ready_read_only', 'registry_image': REGISTRY_IMAGE,
              'ca_sha256': hashlib.sha256(ssl.PEM_cert_to_DER_cert((root / 'pki' / 'ca.crt').read_text())).hexdigest()}
    private_write(complete, json.dumps(public, indent=2))
    return public
