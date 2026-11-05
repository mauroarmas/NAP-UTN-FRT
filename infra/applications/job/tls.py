"""Per-resource server keys, kept in a private node directory, never in jobs.

The institutional CA is injected only by the trusted local runtime. Neither CA
paths nor key material are accepted from the SSH protocol or offer document.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import ipaddress
import os
from pathlib import Path
import re

from .protocol import JobError
from .state import PrivateDirectory, StateStore, uuid_text


class InstanceTLS:
    @classmethod
    def from_node(cls, *, ca_directory=Path('/etc/nap/applications-011/pki'),
                  directory=Path('/var/lib/nap-application-tls')):
        try:
            values = {}
            with PrivateDirectory(ca_directory, create=False) as folder:
                for name in ('ca.crt','ca.key'):
                    descriptor = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder.fd)
                    with os.fdopen(descriptor,'rb') as source:
                        folder._private_file(os.fstat(source.fileno()))
                        raw = source.read(65537)
                        if len(raw) > 65536: raise ValueError()
                        values[name] = raw
            return cls(directory=directory,ca_certificate=values['ca.crt'],ca_private_key=values['ca.key'])
        except Exception: raise JobError('PROFILE_UNAVAILABLE') from None

    def __init__(self, *, directory, ca_certificate, ca_private_key, now=None):
        self.directory = directory
        self.now = now or (lambda: datetime.now(timezone.utc))
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec, rsa
            self.ca = x509.load_pem_x509_certificate(ca_certificate)
            self.key = serialization.load_pem_private_key(ca_private_key, password=None)
            public = lambda k: k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            if public(self.ca.public_key()) != public(self.key.public_key()): raise ValueError()
            if not (isinstance(self.key, ec.EllipticCurvePrivateKey) and self.key.key_size >= 256
                    or isinstance(self.key, rsa.RSAPrivateKey) and self.key.key_size >= 3072): raise ValueError()
            if not self.ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca: raise ValueError()
            if not self.ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign: raise ValueError()
            if not self.ca.not_valid_before_utc <= self.now() < self.ca.not_valid_after_utc: raise ValueError()
            self.ca_pem = self.ca.public_bytes(serialization.Encoding.PEM).decode('ascii')
            self.ca_sha = sha256(self.ca.public_bytes(serialization.Encoding.DER)).hexdigest()
        except Exception: raise JobError('PROFILE_UNAVAILABLE') from None

    @staticmethod
    def _binding(identity, slot):
        try:
            for key in ('resource_uuid','cluster_uuid'): uuid_text(identity[key])
            if not re.fullmatch(r'[0-9a-f]{64}', identity['nonce_sha256']): raise ValueError()
            host = slot['host']
            if type(host) is not str or len(host) > 253 or not host or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in host.split('.')): raise ValueError()
            address = ipaddress.IPv4Address(slot['address'])
            if str(address) != slot['address'] or address.is_unspecified or address.is_multicast: raise ValueError()
            return {key:identity[key] for key in ('resource_uuid','cluster_uuid','nonce_sha256')} | {'host':host,'address':str(address)}
        except Exception: raise JobError('INVALID_REQUEST') from None

    def material(self, identity, slot):
        """Stable on replay; another resource always gets a new key and serial.

        A changed CA/binding, corrupt/expired material or a busy lock fails closed.
        There is no implicit replacement or renewal underneath a live identity.
        """
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        binding = self._binding(identity, slot)
        try:
            with StateStore(self.directory, create=False) as store:
                with store.lock('resource', binding['resource_uuid']):
                    record = store.read('credential', binding['resource_uuid'])
                    if record is None:
                        now = self.now()
                        if not self.ca.not_valid_before_utc <= now < self.ca.not_valid_after_utc - timedelta(hours=1): raise ValueError()
                        key = ec.generate_private_key(ec.SECP256R1())
                        certificate = (x509.CertificateBuilder()
                            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,binding['resource_uuid'])]))
                            .issuer_name(self.ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                            .not_valid_before(max(now-timedelta(minutes=5),self.ca.not_valid_before_utc))
                            .not_valid_after(min(now+timedelta(days=180),self.ca.not_valid_after_utc))
                            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
                            .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,content_commitment=False,
                                data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,
                                encipher_only=False,decipher_only=False),critical=True)
                            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
                            .add_extension(x509.SubjectAlternativeName([x509.DNSName(binding['host']),
                                x509.IPAddress(ipaddress.IPv4Address(binding['address']))]),critical=False)
                            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
                            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()),critical=False)
                            .sign(self.key,hashes.SHA256()))
                        record = {'schema_version':'nap-instance-tls/1','binding':binding,'ca_sha256':self.ca_sha,
                            'certificate_pem':certificate.public_bytes(serialization.Encoding.PEM).decode('ascii'),
                            'private_key_pem':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode('ascii')}
                        store.write('credential',binding['resource_uuid'],record)
                    self._validate(record,binding)
                    return {key:record[key] for key in ('certificate_pem','private_key_pem')} | {'ca_pem':self.ca_pem}
        except JobError: raise
        except Exception: raise JobError('UNCONFIRMED') from None

    def _validate(self, record, binding):
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import ExtendedKeyUsageOID
        if (type(record) is not dict or set(record) != {'schema_version','binding','ca_sha256','certificate_pem','private_key_pem'}
                or record['schema_version'] != 'nap-instance-tls/1' or record['binding'] != binding
                or record['ca_sha256'] != self.ca_sha): raise ValueError()
        certificate = x509.load_pem_x509_certificate(record['certificate_pem'].encode('ascii'))
        key = serialization.load_pem_private_key(record['private_key_pem'].encode('ascii'),password=None)
        certificate.verify_directly_issued_by(self.ca)
        public = lambda k: k.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        if public(certificate.public_key()) != public(key.public_key()): raise ValueError()
        if not certificate.not_valid_before_utc <= self.now() < certificate.not_valid_after_utc: raise ValueError()
        if certificate.not_valid_after_utc > self.ca.not_valid_after_utc: raise ValueError()
        if certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca: raise ValueError()
        if list(certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) != [ExtendedKeyUsageOID.SERVER_AUTH]: raise ValueError()
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if (len(names) != 2 or names.get_values_for_type(x509.DNSName) != [binding['host']]
                or names.get_values_for_type(x509.IPAddress) != [ipaddress.IPv4Address(binding['address'])]): raise ValueError()
