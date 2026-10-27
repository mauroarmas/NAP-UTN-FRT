from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.config import get_settings
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.identidad_infra_service import reclamar
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


async def new_operation(db):
    op = OperacionInfraestructura(tipo='desplegar', actor_tipo='sistema', actor_id_normalizado='test',
        idempotency_key=str(uuid4()), request_hash='a'*64,
        contexto_seguro={'catedra_id':1,'destino':{'nodo':'pve1','storage':'local-lvm'},
            'asignacion':{'product':'postgresql','definition_key':'postgresql-test','definition_version':'1.0.0'},
            'preparacion_validada':{'network_profile_id':'red'}})
    db.add(op)
    await db.flush()
    return op


async def test_dos_instancias_consumen_pool_preparado_sin_editar_perfiles(db, proxmox, perfil_capacidad, monkeypatch):
    ids = [str(uuid4()), str(uuid4())]
    slots = {value:{'host':f'pg{i}.example.edu','address':f'10.20.0.{i+10}',
        'mac_address':f'02:00:00:00:00:{i+10:02x}','products':['postgresql']} for i,value in enumerate(ids)}
    monkeypatch.setattr(get_settings(), 'network_profiles', {'red':{'instances':slots,
        'allowed_cidrs':['10.20.0.0/24'],'nodes':['pve1'],'bridge':'vmbr0','client_cidrs':['10.30.0.0/24']}})
    first_op = await new_operation(db)
    first = await reclamar(db, first_op, pve=proxmox)
    assert str(first.resource_uuid) in ids
    again = await reclamar(db, first_op, pve=proxmox)
    assert again.id == first.id
    second = await reclamar(db, await new_operation(db), pve=proxmox)
    assert first.resource_uuid != second.resource_uuid
    with pytest.raises(HTTPException) as exc:
        await reclamar(db, await new_operation(db), pve=proxmox)
    assert exc.value.status_code == 409
    assert exc.value.detail['codigo'] == 'red_preparada_agotada'
    assert len(slots) == 2


@pytest.mark.parametrize('product', ['postgresql','bookstack'])
@pytest.mark.parametrize('ip_mode', ['dhcp','static'])
async def test_despliegue_dos_aplicaciones_con_pool_y_secretos_independientes(db, client, engine,
        proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_admin, monkeypatch, product, ip_mode):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.pedido import ModeloServicio, EstadoPedido
    from app.models.servicio import Servicio
    from app.services import catalogo_service
    from app.worker import procesar_una
    from app.utils.clock import clock
    from app.utils.secretos import configured_keyring
    from tests import factories
    from tests.service_helpers import link_capacity_definition, PRODUCTS
    from tests.capacity_helpers import aprobar_http
    now = [clock.now()]
    monkeypatch.setattr(clock, 'now', lambda: now[0])
    definition = await link_capacity_definition(db, template, admin, product)
    template.modelo_servicio = ModeloServicio(PRODUCTS[product])
    await db.commit()
    # El laboratorio sintético comparte el clúster de la definición del producto.
    settings = get_settings()
    monkeypatch.setattr(settings, 'infrastructure_profile', {**settings.infrastructure_profile,
        'cluster_id':definition['validation']['cluster_uuid']})
    keys = [str(uuid4()),str(uuid4())]
    slots = {key:{'host':f'{product}{i}.example.edu','address':f'10.20.0.{i+10}',
        'mac_address':f'02:00:00:00:00:{i+10:02x}', 'products':[product]} for i,key in enumerate(keys)}
    profile = {'instances':slots, 'bridge':'vmbr0','nodes':['pve1'],
        'allowed_cidrs':['10.20.0.0/24'],'client_cidrs':['10.30.0.0/24']}
    if ip_mode=='static':profile.update(ip_mode='static',static_cidr='10.20.0.0/24',gateway='10.20.0.1')
    monkeypatch.setattr(settings, 'network_profiles', {'test-network':profile})
    monkeypatch.setattr(settings, 'service_artifacts', {definition['definition_key']+':1.0.0':{
        'nodes':['pve1'],'network_profile_id':'test-network'}})
    async def available(*args, **kwargs): pass
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', available)
    proxmox.contenidos_storage[('pve1','local')].append({'volid':definition['image']['volume_id'],'content':'vztmpl','size':1024})
    class Runner:
        def __init__(self):
            self.first = True
        async def execute(self, request):
            if self.first:
                self.first = False
                from app.schemas.guest_runner import RunnerError
                raise RunnerError('UNCONFIRMED')
            instance = slots[request['resource_uuid']]
            name = 'curso_'+UUID(request['resource_uuid']).hex if product == 'postgresql' else usuario_catedra.email
            result = {'ready':True,'bootstrap_completed':True,'host':instance['host'], 'address':instance['address'],
                'addresses':[instance['address']], 'username':name,
                'port':5432 if product=='postgresql' else 443,
                'checks':['postgresql-select-v1' if product=='postgresql' else 'bookstack-status-v1']}
            if product=='postgresql': result['database']=name
            else: result['endpoint']='https://'+instance['host']
            return {**{key:request[key] for key in ['protocol','operation_id','action','resource_uuid']},
                'status':'succeeded','phase':'verified','observed_at':clock.now().isoformat(),
                'identity_verified':True,'result':result}
    from uuid import UUID
    sessions = async_sessionmaker(engine,expire_on_commit=False)
    for _ in range(2):
        pedido = await factories.crear_pedido(db,catedra.id,usuario_catedra.id,template.id,
            estado=EstadoPedido.SOLICITADO,modelo_servicio=ModeloServicio(PRODUCTS[product]))
        response = await aprobar_http(client,pedido,template,auth_admin,desplegar_inmediatamente=True)
        assert response.status_code == 202, response.text
        runner = Runner()
        await procesar_una(sessions,pve=proxmox,runner=runner)
        operation = await db.get(OperacionInfraestructura, UUID(response.json()['operation_id']), populate_existing=True)
        initial_service = await db.get(Servicio, operation.servicio_id, populate_existing=True)
        encrypted = initial_service.credenciales_encrypted
        resource = operation.identidad_infraestructura_id
        from datetime import timedelta
        now[0] += timedelta(seconds=31)
        await procesar_una(sessions,pve=proxmox,runner=runner)
        await db.refresh(initial_service)
        await db.refresh(operation)
        assert operation.estado == 'confirmada'
        assert operation.identidad_infraestructura_id == resource
        assert initial_service.credenciales_encrypted == encrypted
    services = list((await db.scalars(select(Servicio))).all())
    assert len(services)==2
    assert len(proxmox.creados)==2
    assert {service.acceso_metadata['host'] for service in services}=={slot['host'] for slot in slots.values()}
    secrets = [configured_keyring().decrypt(service.credenciales_encrypted,context=f'servicio:{service.id}:secretos') for service in services]
    password_field = 'database_password' if product=='postgresql' else 'teacher_password'
    assert secrets[0][password_field]!=secrets[1][password_field]
    assert all('hwaddr=02:' in config['net0'] for config in proxmox.creados)
    if ip_mode=='static':
        assert {config['net0'].split(',ip=',1)[1].split(',',1)[0] for config in proxmox.creados}=={'10.20.0.10/24','10.20.0.11/24'}
        assert all('gw=10.20.0.1' in config['net0'] for config in proxmox.creados)


def test_red_estatica_configurada_no_depende_de_dhcp_y_conserva_snapshot():
    from app.services.reserva_red_service import snapshot,aplicar_asignacion
    profile={'bridge':'vmbr0','client_cidrs':['172.16.36.1/32'],
        'allowed_cidrs':['172.16.36.0/24'],'ip_mode':'static','static_cidr':'172.16.36.0/24','gateway':'172.16.36.2'}
    instance={'host':'drawio1.nap.test','address':'172.16.36.61','mac_address':'02:00:00:00:00:61'}
    allocation=snapshot(profile,instance)
    assert aplicar_asignacion('name=eth0,bridge=vmbr0,ip=dhcp,tag=42',allocation)==(
        'name=eth0,bridge=vmbr0,ip=172.16.36.61/24,gw=172.16.36.2,tag=42,hwaddr=02:00:00:00:00:61')
    profile['gateway']='172.16.36.3'
    assert allocation['static_ip']['gateway']=='172.16.36.2'
    assert aplicar_asignacion('name=eth0,bridge=vmbr0,ip=dhcp',instance).endswith('ip=dhcp,hwaddr=02:00:00:00:00:61')


@pytest.mark.parametrize('change',[{'address':'10.0.0.61'},{'address':'172.16.36.2'},{'address':'172.16.36.255'},
    {'gateway':'10.0.0.1'},{'static_cidr':'172.16.0.0/16'}])
def test_red_estatica_rechaza_direcciones_fuera_de_alcance(change):
    from app.services.reserva_red_service import snapshot
    profile={'bridge':'vmbr0','client_cidrs':['172.16.36.1/32'],'allowed_cidrs':['172.16.36.0/24'],
        'ip_mode':'static','static_cidr':'172.16.36.0/24','gateway':'172.16.36.2'}
    instance={'host':'drawio1.nap.test','address':'172.16.36.61','mac_address':'02:00:00:00:00:61'}
    profile.update({k:v for k,v in change.items() if k!='address'});instance.update({k:v for k,v in change.items() if k=='address'})
    with pytest.raises(ValueError):snapshot(profile,instance)
