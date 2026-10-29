"""Pruebas de ciclo de vida de aplicaciones OCI (US5 - T089):
stop/start/restart sin pull/reinstalar/regenerar secretos, datos persistentes,
identidad ajena, baja fallida/almacenamiento presente, y oferta retirada.
"""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.models.reserva_red_aplicacion import ReservaRedAplicacion
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.servicio import Servicio, EstadoServicio
from app.models.recurso_template import RecursoTemplate
from app.models.usuario import Usuario
from app.models.vigencia import VigenciaAutorizada
from app.services import orquestacion_service, admision_service
from app.services.application_verification_service import AccessObservation
from app.utils.clock import clock
from app.worker import procesar_una, procesar_ingesta_una
from tests.test_admision_aplicaciones_011 import (
    app_order,
    approve,
    perfil_capacidad,
    red_aplicaciones_011,
    profile_entry,
)
from tests.test_creacion_aplicaciones_011 import stopped_create, wake
from tests.test_entrega_aplicaciones_011 import DeliveredNode


@pytest.fixture
async def active_app_service(db, engine, admin, app_order, proxmox):
    """Fixture que despliega y entrega un servicio OCI activo con secreto."""
    admin_id = admin.id
    order_id = app_order.pedido.id
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = DeliveredNode(app_order, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    db.expire_all()

    identity = await db.scalar(select(IdentidadInfraestructura))
    proxmox.estados[identity.vmid] = "running"
    await wake(db)

    async def probe(instance):
        return AccessObservation(
            instance["host"],
            instance["address"],
            instance["port"],
            instance["configuration_sha256"],
            200,
        )

    await procesar_ingesta_una(sessions, runner=node, pve=proxmox, probe=probe)
    db.expire_all()

    service = await db.scalar(select(Servicio))
    assert service.disponibilidad_aplicacion == "utilizable"
    assert service.estado == EstadoServicio.RUNNING

    return sessions, service.id, node, order_id, admin_id


async def test_detener_iniciar_reiniciar_sin_pull_ni_reinstalar_ni_regenerar_secretos(
    db, active_app_service, proxmox
):
    sessions, service_id, node, order_id, admin_id = active_app_service

    # Guardar estado de secretos antes del ciclo
    secretos_originales = list((await db.scalars(select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == order_id))).all())
    starts_count_before = len(node.starts)

    service = await db.get(Servicio, service_id)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    vmid = identity.vmid

    admin = await db.get(Usuario, admin_id)
    # 1. Detener el servicio
    res_stop = await orquestacion_service.detener_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res_stop.status_code == 202
    await db.commit()

    # Procesar la operación 'detener'
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    service = await db.get(Servicio, service_id)
    assert service.estado == EstadoServicio.STOPPED
    assert proxmox.estados[vmid] == "stopped"

    # 2. Iniciar el servicio nuevamente
    await wake(db)
    admin = await db.get(Usuario, admin_id)
    res_start = await orquestacion_service.iniciar_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res_start.status_code == 202
    await db.commit()

    # Procesar la operación 'iniciar'
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    service = await db.get(Servicio, service_id)
    assert service.estado == EstadoServicio.RUNNING
    assert proxmox.estados[vmid] == "running"

    # 3. Reiniciar el servicio
    await wake(db)
    admin = await db.get(Usuario, admin_id)
    res_reboot = await orquestacion_service.reiniciar_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res_reboot.status_code == 202
    await db.commit()

    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    service = await db.get(Servicio, service_id)
    assert service.estado == EstadoServicio.RUNNING

    # Comprobar que NINGUNA operación de ciclo de vida llamó a start del runner (sin pull ni reinstalación)
    assert len(node.starts) == starts_count_before

    # Comprobar que los secretos NO se regeneraron
    secretos_despues = list((await db.scalars(select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == order_id))).all())
    assert len(secretos_despues) == len(secretos_originales)
    if secretos_originales:
        assert secretos_despues[0].id == secretos_originales[0].id
        assert secretos_despues[0].creado_at == secretos_originales[0].creado_at


async def test_identidad_incierta_o_ajena_rechaza_operaciones(
    db, active_app_service, proxmox
):
    sessions, service_id, node, _, admin_id = active_app_service

    service = await db.get(Servicio, service_id)
    identity_id = service.identidad_infraestructura_id
    admin = await db.get(Usuario, admin_id)

    # Caso A: identidad en la base de datos marcada como incierta -> reiniciar rechaza
    identity = await db.get(IdentidadInfraestructura, identity_id)
    identity.estado = "incierta"
    await db.commit()

    with pytest.raises(Exception) as exc_info:
        await orquestacion_service.reiniciar_servicio(
            db, service_id, admin, clave=str(uuid4())
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["codigo"] == "reconciliacion_pendiente"

    # Caso B: identidad con ausencia confirmada -> detener rechaza
    identity = await db.get(IdentidadInfraestructura, identity_id)
    identity.estado = "retirada"
    identity.ausencia_confirmada_at = clock.now()
    await db.commit()

    admin = await db.get(Usuario, admin_id)
    with pytest.raises(Exception) as exc_info:
        await orquestacion_service.detener_servicio(
            db, service_id, admin, clave=str(uuid4())
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["codigo"] == "asignacion_sin_regularizar"

    # Restaurar identidad materializada normal
    identity = await db.get(IdentidadInfraestructura, identity_id)
    identity.estado = "materializada"
    identity.ausencia_confirmada_at = None
    await db.commit()

    # Caso C: el contenedor en Proxmox fue alterado con marcador ajeno
    # Se admite la orden pero al despacharla el worker detecta la identidad ajena y la rechaza sin tocar el contenedor
    admin = await db.get(Usuario, admin_id)
    res = await orquestacion_service.detener_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res.status_code == 202
    await db.commit()

    # Alterar descripción simulando contenedor ajeno
    proxmox.configuraciones[(identity.nodo, identity.vmid)]["description"] = "contenedor-ajeno-no-nap"
    detenidos_antes = len(proxmox.detenidos)

    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    # Comprobar que el contenedor ajeno NO fue detenido
    assert len(proxmox.detenidos) == detenidos_antes

    # La operación pasa a estado incierto (requiere reconciliación)
    op = await db.scalar(
        select(OperacionInfraestructura)
        .where(
            OperacionInfraestructura.servicio_id == service_id,
            OperacionInfraestructura.tipo == "detener",
        )
    )
    assert op.estado == "incierta"


async def test_baja_fallida_mantiene_limpieza_pendiente_sin_liberar_red_ni_ledger(
    db, active_app_service, proxmox
):
    sessions, service_id, node, _, admin_id = active_app_service

    admin = await db.get(Usuario, admin_id)
    # Detener primero el servicio
    await orquestacion_service.detener_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    # Simular fallo en Proxmox durante delete_lxc (vzdestroy)
    original_delete = proxmox.delete_lxc
    def fail_delete(node_name, vmid):
        upid = proxmox._task(node_name, vmid, "delete")
        proxmox.configure_task(node_name, upid, [{"status": "stopped", "exitstatus": "ERROR: storage locked"}])
        return upid

    proxmox.delete_lxc = fail_delete

    # Intentar eliminar servicio
    admin = await db.get(Usuario, admin_id)
    res_del = await orquestacion_service.eliminar_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res_del.status_code == 202
    await db.commit()

    # Procesar eliminación fallida
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    service = await db.get(Servicio, service_id)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    ledger = await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service_id))
    network = await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id == identity.id))

    # NO se debe confirmar ausencia ni liberar recursos
    assert identity.ausencia_confirmada_at is None
    assert identity.estado == "incierta"
    assert ledger.liberado_at is None
    assert ledger.estado == "incierto"
    assert network.liberada_at is None


async def test_oferta_retirada_permite_operar_instancia_existente(
    db, active_app_service, proxmox
):
    sessions, service_id, node, order_id, admin_id = active_app_service

    service = await db.get(Servicio, service_id)
    # Retirar la oferta/configuración en el catálogo
    config = await db.get(ConfiguracionDespliegue, service.configuracion_despliegue_id)
    config.estado = "retirada"
    config.retirada_at = clock.now()
    template = await db.get(RecursoTemplate, service.template_id)
    template.oferta_disponible = False
    await db.commit()

    admin = await db.get(Usuario, admin_id)
    # Las instancias existentes deben poder seguir operando normalmente (ej. detener)
    res_stop = await orquestacion_service.detener_servicio(
        db, service_id, admin, clave=str(uuid4())
    )
    assert res_stop.status_code == 202
    await db.commit()

    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    service = await db.get(Servicio, service_id)
    assert service.estado == EstadoServicio.STOPPED


async def test_cobertura_vencida_bloquea_reinicio(
    db, active_app_service, proxmox
):
    sessions, service_id, node, order_id, admin_id = active_app_service

    # Vencer todas las vigencias autorizadas del servicio
    vigencias = (await db.scalars(
        select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == service_id)
    )).all()
    for v in vigencias:
        v.fin_exclusivo_at = clock.now() - timedelta(minutes=5)
    await db.commit()

    admin = await db.get(Usuario, admin_id)
    # Intentar reiniciar con vigencia vencida
    with pytest.raises(Exception) as exc_info:
        await orquestacion_service.reiniciar_servicio(
            db, service_id, admin, clave=str(uuid4())
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["codigo"] == "sin_cobertura_actual"



@pytest.mark.parametrize('cleanup_confirmed',[False,True])
async def test_baja_releases_host_rules_before_releasing_vmid_network_and_capacity(db,active_app_service,proxmox,cleanup_confirmed):
    from infra.applications.job.protocol import PROTOCOL,fingerprint
    sessions,service_id,node,_,admin_id=active_app_service
    calls=[]
    class CleanupNode:
        async def execute(self,request,**kwargs):
            assert request['action']=='cleanup';calls.append(dict(request))
            assert str(request['nonce']) and request['vmid'] not in proxmox.estados
            return ({'protocol':PROTOCOL,'ok':True,'action':'cleanup','data':{'released':True,'fingerprint':fingerprint(request)}}
                if cleanup_confirmed else {'protocol':PROTOCOL,'ok':False,'error':'UNCONFIRMED'})
    result=await orquestacion_service.eliminar_servicio(db,service_id,await db.get(Usuario,admin_id),clave='delete-with-network-cleanup')
    await db.commit()
    for _ in range(4):
        await wake(db);await procesar_una(sessions,pve=proxmox,runner=CleanupNode())
    db.expire_all();service=await db.get(Servicio,service_id)
    ledger=await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id==service_id))
    network=await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id==service.identidad_infraestructura_id))
    assert calls
    assert bool(service.deleted_at)==cleanup_confirmed
    assert bool(ledger.liberado_at)==cleanup_confirmed
    assert bool(network.liberada_at)==cleanup_confirmed
    if not cleanup_confirmed:assert ledger.disk_bytes_retenidos>0
