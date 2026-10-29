"""Bounded native SELECT with certificate identity checking before authentication."""
import ssl
import pymysql
from pymysql.constants import CLIENT

from app.config import get_settings
from app.services.infraestructura_io import ejecutar,InfraNoVerificable


class TLSConnection(pymysql.connections.Connection):
    def _request_authentication(self):
        # PyMySQL may otherwise fall back when a peer advertises no TLS support.
        # The driver version is pinned; the secret must never precede TLS.
        if not self.ssl or not self.server_capabilities & CLIENT.SSL:
            raise pymysql.err.OperationalError(2026,'TLS required')
        super()._request_authentication()
        if not isinstance(self._sock,ssl.SSLSocket):
            raise pymysql.err.OperationalError(2026,'TLS required')


def connect(instance,password):
    context=ssl.create_default_context(cafile=get_settings().application_gateway_ca_file)
    return TLSConnection(host=instance['address'],port=instance['port'],user='docente',
        password=password,database='catedra',ssl=context,connect_timeout=5,read_timeout=5,
        write_timeout=5,autocommit=True,local_infile=False,charset='utf8mb4')


async def probe(instance,private):
    from app.services.application_verification_service import AccessObservation
    def check():
        try:
            with connect(instance,private['MARIADB_PASSWORD']) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    if cursor.fetchone()!=(1,):raise InfraNoVerificable()
            return AccessObservation(instance['host'],instance['address'],instance['port'],
                instance['configuration_sha256'],1)
        except (pymysql.Error,OSError,ValueError):raise InfraNoVerificable() from None
    return await ejecutar(check,timeout=instance['access']['probe']['timeout_segundos'])
