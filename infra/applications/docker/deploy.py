"""One existing NAP LXC, five fixed guest actions; no Docker on the PVE node."""
from ..job.protocol import JobError
from .runtime import validate_profile
from .access import registry_credentials
from .probes import verify


def deploy(context):
    node=context.node
    if node is None or context.network is None or context.tls is None:raise JobError('PROFILE_UNAVAILABLE')
    config,profile=node._configuration(context.identity)
    lock=validate_profile(profile)
    access=context.configuration['access']
    if (access['tipo']=='web' and access['upstream']!='http'
            or access['tipo']=='tcp' and context.configuration['imagen']['repositorio']!='docker.io/library/mariadb'):
        raise JobError('PROFILE_UNAVAILABLE')
    payload={'configuration':context.configuration,'runtime':profile['runtime'],'edge':lock['edge'],
        'network':context.network,'resources':{'vcpus':config['cores'],'ram_mb':config['memory'],
            'disk_gb':4 if config['cores']==1 else 8}}
    node.start_guest(context.identity)
    node.bootstrap_docker(context.identity,context)
    context.begin_output(packages={'docker.io','containerd','runc'})
    node.docker_action(context.identity,'prepare',payload,context)
    context.phase('instalacion')
    registry=registry_credentials(context.configuration['imagen'])
    context.begin_output(extra_secrets=[v for k,v in registry.items() if k in {'username','password'} and isinstance(v,str)])
    node.docker_action(context.identity,'pull',{**payload,'registry':registry},context)
    registry.clear()
    context.phase('configuracion');context.begin_output()
    node.docker_action(context.identity,'configure',{**payload,'tls':context.tls},context)
    context.phase('arranque');context.begin_output()
    values={s['nombre']:context.secret(s['nombre']) for s in context.configuration['secretos']}
    node.docker_action(context.identity,'start',{**payload,'private_values':values},context)
    values.clear()
    context.phase('comprobacion');context.begin_output()
    return verify(context,payload)
