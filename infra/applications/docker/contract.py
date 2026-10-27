"""Pure fixed Docker CLI plan shared by host adapter and guest program."""
from hashlib import sha256
from uuid import UUID


def volume_name(resource_uuid,path):
    return 'nap_'+UUID(resource_uuid).hex+'_'+sha256(path.encode()).hexdigest()[:16]


def application_arguments(identity,configuration,resources):
    """No ENTRYPOINT/CMD override, values in argv, anonymous volume or host bind."""
    resource=UUID(identity['resource_uuid']).hex
    ram=resources['ram_mb']
    if any(type(resources[k]) is not int for k in ('vcpus','ram_mb','disk_gb')):raise ValueError('INVALID_REQUEST')
    if (resources['vcpus'],ram,resources['disk_gb']) not in {(1,512,4),(2,1024,8)}:raise ValueError('INVALID_REQUEST')
    args=['run','-d','--name','nap-'+resource,'--pull=never','--restart=unless-stopped','--network=bridge',
        '--cap-drop=ALL','--cap-add=NET_BIND_SERVICE','--security-opt=no-new-privileges:true',
        '--log-driver=none','--no-healthcheck','--pids-limit=256','--memory='+str(ram-256)+'m',
        '--memory-swap='+str(ram-256)+'m','--cpus='+str(resources['vcpus']),
        '--label=nap.resource_uuid='+identity['resource_uuid'],
        '--label=nap.configuration_sha256='+identity['configuracion_sha256'],
        '--publish=127.0.0.1:18080:'+str(configuration['access']['puerto'])]
    for path in configuration['persistencia']:
        args+=['--mount','type=volume,source='+volume_name(identity['resource_uuid'],path)+',target='+path]
    for name in sorted([*configuration['variables'],*[s['nombre'] for s in configuration['secretos']]]):
        args+=['--env',name]
    image=configuration['imagen'];args.append(image['repositorio']+'@'+image['manifest_digest'])
    return args
