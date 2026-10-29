#!/bin/bash
# EN LA PC DEL OPERADOR. Crea, en el propio nodo, la CA de laboratorio que usa el runner 011
# para emitir el certificado TLS de cada instancia (/etc/nap/applications-011/pki/{ca.crt,ca.key}).
#
# - La clave privada se genera en el nodo y no sale de él.
# - Es una CA de LABORATORIO: no es la CA institucional y no se instala en ningún otro lado.
# - Se niega a sobrescribir si el directorio pki ya existe.
# - Al terminar comprueba que InstanceTLS.from_node (el código real del runner) la acepta.
# Una CA por nodo: repetir con NODE_IP distinto para frt.
set -u
NODE_IP=${NODE_IP:-192.168.100.91}
NODE_NAME=${NODE_NAME:-pve91}
CTL=/tmp/nap-ca-ssh-%h
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=120 -o SendEnv=-LC_*"

ssh $SSH_OPTS root@$NODE_IP "NODE_NAME=$NODE_NAME python3 -I -" <<'PY'
import os, sys
from datetime import datetime, timedelta, timezone
PKI = '/etc/nap/applications-011/pki'
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
except ImportError:
    sys.exit('Falta python3-cryptography en el nodo (apt install python3-cryptography)')
if os.path.lexists(PKI):
    sys.exit(PKI + ' ya existe; no se sobrescribe')
name = os.environ['NODE_NAME']
key = ec.generate_private_key(ec.SECP256R1())
subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'NAP laboratorio'),
                     x509.NameAttribute(NameOID.COMMON_NAME, 'NAP lab CA ' + name)])
now = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=5 * 365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256()))
os.umask(0o077)
os.mkdir(PKI, 0o700)
for file, data in (('ca.key', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption())),
                   ('ca.crt', cert.public_bytes(serialization.Encoding.PEM))):
    fd = os.open(os.path.join(PKI, file), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(data); target.flush(); os.fsync(target.fileno())
# Prueba con el código real del runner: lo que acepta aquí es lo que usará el job.
sys.dont_write_bytecode = True
sys.path.insert(0, '/opt/nap')
from applications.job.tls import InstanceTLS
tls = InstanceTLS.from_node()
print('CA creada y aceptada por el runner; sha256 DER:', tls.ca_sha)
PY
rc=$?
ssh -o ControlPath=$CTL -O exit root@$NODE_IP 2>/dev/null
exit $rc
