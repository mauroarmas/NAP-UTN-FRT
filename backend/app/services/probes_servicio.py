"""Validar observación del runner antes de convertirla en metadatos de acceso."""
import ipaddress
import re
from datetime import datetime, timedelta

from app.schemas.guest_runner import canonical, parse_response, RunnerError
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.clock import clock, db_utc


def confirmar(response, request, *, product, profile, service_id, preparation_id):
    try:
        response = parse_response(canonical(response).encode(), request)
        observed = db_utc(datetime.fromisoformat(response['observed_at'].replace('Z', '+00:00')))
        if (response['status'] != 'succeeded' or response['identity_verified'] is not True
            or observed > clock.now() + timedelta(seconds=5) or observed < clock.now() - timedelta(minutes=5)):
            raise ValueError()
        result = response['result']
        if result.get('ready') is not True or result.get('bootstrap_completed') is not True:
            raise ValueError()
        addresses = result.get('addresses', [])
        subnets = [ipaddress.ip_network(value, strict=True) for value in profile['allowed_cidrs']]
        if not addresses or any(not any(ipaddress.ip_address(address).version == subnet.version
            and ipaddress.ip_address(address) in subnet for subnet in subnets) for address in addresses):
            raise ValueError()
        metadata = {'preparacion_id': str(preparation_id), 'local_health': True,
            'local_observed_at': response['observed_at'], 'network_profile_id': request['network_profile_id'], 'addresses': addresses}
        if product == 'linux':
            if result.get('username') != 'napadmin' or 'linux-ready-v1' not in result.get('checks', []):
                raise ValueError()
            metadata.update(metodo='consola', username='napadmin', endpoint=f'/servicios/{service_id}/consola')
        else:
            # Perfil institucional por instancia, coherente con el que lee el
            # runner root; no aceptar un endpoint proporcionado por el guest.
            instance = profile['instances'][request['resource_uuid']]
            host, address = instance['host'], instance['address']
            if (not isinstance(host, str) or not re.fullmatch(r'[a-z0-9.-]{1,253}', host)
                or result.get('host') != host or result.get('address') != address or address not in addresses):
                raise ValueError()
            if product == 'postgresql':
                database = result['database']
                if result.get('port') != 5432 or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', database):
                    raise ValueError()
                from uuid import UUID
                if result.get('username') != 'curso_' + UUID(request['resource_uuid']).hex:
                    raise ValueError()
                expected_database = request['parameters'].get('database_name', 'curso_' + UUID(request['resource_uuid']).hex)
                if database != expected_database or 'postgresql-select-v1' not in result.get('checks', []):
                    raise ValueError()
                metadata.update(metodo='postgresql', host=host, port=5432, database=database, username=result['username'],
                    endpoint=f'postgresql://{host}:5432/{database}', sslmode='verify-full')
            elif product == 'drawio':
                from uuid import UUID
                if (result.get('port') != 443 or result.get('endpoint') != 'https://' + host
                    or result.get('username') != 'nap_' + UUID(request['resource_uuid']).hex
                    or 'drawio-status-v1' not in result.get('checks', [])):
                    raise ValueError()
                metadata.update(metodo='https', host=host, port=443, username=result['username'], endpoint='https://' + host)
            elif product == 'bookstack':
                if (result.get('port') != 443 or result.get('endpoint') != 'https://' + host
                    or result.get('username') != request['parameters']['teacher_email']
                    or 'bookstack-status-v1' not in result.get('checks', [])):
                    raise ValueError()
                metadata.update(metodo='https', host=host, port=443, username=result['username'], endpoint='https://' + host)
            else:
                raise ValueError()
        return metadata
    except (ValueError, KeyError, TypeError, RunnerError):
        raise InfraNoVerificable(incierto=True) from None
