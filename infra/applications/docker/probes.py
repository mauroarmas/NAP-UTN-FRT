"""The guest's typed TLS probe follows host confinement and bridge checks."""
from ..job.protocol import JobError


def verify(context,payload):
    context.node.assert_confinement(context.identity)
    context.node.docker_action(context.identity,'probe',{**payload,'tls':{'ca_pem':context.tls['ca_pem']}},context)
    return {'recurso_configurado':True,'comprobaciones':['aislamiento','runtime','salud','acceso_web']}
