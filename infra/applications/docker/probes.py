"""The guest's typed TLS probe follows host confinement and bridge checks."""
from ..job.protocol import JobError


def verify(context,payload):
    context.node.assert_confinement(context.identity)
    database=context.configuration['access']['tipo']=='tcp'
    request={**payload,'tls':{'ca_pem':context.tls['ca_pem']}}
    if database:request['private_values']={'MARIADB_PASSWORD':context.secret('MARIADB_PASSWORD')}
    context.node.docker_action(context.identity,'probe',request,context)
    return {'recurso_configurado':True,'comprobaciones':['aislamiento','runtime','salud','autenticacion_tcp' if database else 'acceso_web']}
