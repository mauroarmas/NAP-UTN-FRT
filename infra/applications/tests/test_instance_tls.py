from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infra.applications.job.tls import InstanceTLS
from infra.applications.job.protocol import JobError


@pytest.fixture
def issuer(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'NAP disposable test CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,content_commitment=False,
            data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
        .sign(key,hashes.SHA256()))
    folder = tmp_path/'tls'; folder.mkdir(mode=0o700)
    clock = [now]
    value = InstanceTLS(directory=folder,ca_certificate=ca.public_bytes(serialization.Encoding.PEM),
        ca_private_key=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),now=lambda:clock[0])
    value.test_clock = clock
    return value


@pytest.fixture
def binding():
    return {'resource_uuid':str(uuid4()),'cluster_uuid':str(uuid4()),'nonce_sha256':'a'*64}, {'host':'app81.nap.test','address':'172.16.36.81'}


def test_new_resource_gets_new_key_serial_and_exact_sans_but_replay_is_stable(issuer,binding):
    identity,slot = binding
    first = issuer.material(identity,slot)
    assert issuer.material(identity,slot) == first
    second = issuer.material({**identity,'resource_uuid':str(uuid4())},slot)
    assert first['private_key_pem'] != second['private_key_pem']
    assert x509.load_pem_x509_certificate(first['certificate_pem'].encode()).serial_number != x509.load_pem_x509_certificate(second['certificate_pem'].encode()).serial_number
    for file in issuer.directory.iterdir(): assert file.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize('mutation',['nonce','cluster','host','address','expired','corrupt'])
def test_existing_material_cannot_be_adopted_or_silently_replaced(issuer,binding,mutation):
    identity,slot = binding
    issuer.material(identity,slot)
    file = issuer.directory/('credential.'+identity['resource_uuid']+'.json')
    if mutation == 'corrupt':
        data = json.loads(file.read_text()); data['private_key_pem'] = 'not a key'
        file.write_text(json.dumps(data))
    before = file.read_bytes()
    if mutation == 'nonce': identity['nonce_sha256'] = 'b'*64
    if mutation == 'cluster': identity['cluster_uuid'] = str(uuid4())
    if mutation == 'host': slot['host'] = 'other.nap.test'
    if mutation == 'address': slot['address'] = '172.16.36.82'
    if mutation == 'expired': issuer.test_clock[0] += timedelta(days=181)
    with pytest.raises(JobError) as caught: issuer.material(identity,slot)
    assert file.read_bytes() == before
    assert 'PRIVATE KEY' not in str(caught.value)


def test_symlink_and_public_storage_are_rejected(issuer,binding,tmp_path):
    identity,slot=binding
    path = issuer.directory/('credential.'+identity['resource_uuid']+'.json')
    outside = tmp_path/'other'; outside.write_text('untouched'); outside.chmod(0o600)
    path.symlink_to(outside)
    with pytest.raises(JobError): issuer.material(identity,slot)
    assert outside.read_text() == 'untouched'
    path.unlink(); issuer.directory.chmod(0o755)
    with pytest.raises(JobError): issuer.material(identity,slot)


def test_material_works_with_strict_tls_and_rejects_other_hostname(issuer,binding,tmp_path):
    import socket
    import ssl
    import threading
    identity,slot=binding
    material=issuer.material(identity,slot)
    for name,key in [('cert.pem','certificate_pem'),('key.pem','private_key_pem')]:
        path=tmp_path/name; path.write_text(material[key]); path.chmod(0o600)
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); server.load_cert_chain(tmp_path/'cert.pem',tmp_path/'key.pem')
    client=ssl.create_default_context(cadata=material['ca_pem'])
    for host,expected in [(slot['host'],True),(slot['address'],True),('wrong.nap.test',False)]:
        left,right=socket.socketpair(); left.settimeout(2);right.settimeout(2)
        failures=[]
        def respond():
            try:
                with server.wrap_socket(left,server_side=True) as stream: stream.sendall(b'OK')
            except ssl.SSLError: failures.append('rejected')
        thread=threading.Thread(target=respond);thread.start()
        try:
            if expected:
                with client.wrap_socket(right,server_hostname=host) as stream: assert stream.recv(2)==b'OK'
            else:
                with pytest.raises(ssl.SSLCertVerificationError): client.wrap_socket(right,server_hostname=host)
        finally:
            left.close();right.close();thread.join(timeout=3)
        assert not thread.is_alive()
        if expected: assert not failures


def test_fixed_ca_loader_rejects_links_and_does_not_create_missing_private_storage(issuer,binding,tmp_path):
    pki=tmp_path/'pki';pki.mkdir(mode=0o700)
    cert=pki/'ca.crt';cert.write_text(issuer.ca_pem);cert.chmod(0o600)
    target=tmp_path/'outside-key';target.write_text('not-read');target.chmod(0o600)
    (pki/'ca.key').symlink_to(target)
    with pytest.raises(JobError,match='PROFILE_UNAVAILABLE'):
        InstanceTLS.from_node(ca_directory=pki,directory=tmp_path/'missing')
    assert not (tmp_path/'missing').exists()
