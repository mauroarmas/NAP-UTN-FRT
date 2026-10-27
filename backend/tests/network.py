"""Bloqueo de red real, compartido por suites backend e infraestructura."""

import os
import socket

from sqlalchemy.engine import make_url

from tests.postgres.safety import validate_test_database_url


def block_network(monkeypatch, *, allow_postgres=False):
    allowed = set()
    allowed_hosts = set()
    if allow_postgres and os.environ.get('TEST_DATABASE_URL'):
        value = validate_test_database_url(os.environ['TEST_DATABASE_URL'])
        url = make_url(value)
        allowed_hosts.add(url.host)
        for entry in socket.getaddrinfo(url.host, url.port or 5432, type=socket.SOCK_STREAM):
            allowed.add(entry[4][:2])

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_lookup = socket.getaddrinfo
    original_sendto = socket.socket.sendto

    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6} and tuple(address[:2]) not in allowed:
            raise RuntimeError('Red real prohibida: sustituir el adaptador por un doble de prueba')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6} and tuple(address[:2]) not in allowed:
            raise RuntimeError('Red real prohibida: sustituir el adaptador por un doble de prueba')
        return original_connect_ex(sock, address)

    def lookup(host, *args, **kwargs):
        if host not in allowed_hosts:
            raise RuntimeError('DNS real prohibido en pruebas')
        return original_lookup(host, *args, **kwargs)

    def sendto(sock, data, *args):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            raise RuntimeError('Red real prohibida: datagrama sin doble de prueba')
        return original_sendto(sock, data, *args)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', lookup)
    monkeypatch.setattr(socket.socket, 'sendto', sendto)
