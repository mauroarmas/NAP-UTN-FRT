import asyncio
import logging
import ssl
from datetime import datetime
from uuid import UUID
from urllib.parse import quote
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.models.pedido import Pedido, EstadoPedido, TipoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.servicio import (
    ServicioResponse,
    ServicioUpdate,
    ServicioPausadoResponse,
    DesplegarRequest,
    DesplegarSnapshotRequest,
    OrdenServicioRequest,
)
from app.services import historial_service
from app.services.acceso_service import catedras_visibles
from app.services.acceso_service import requiere_acceso_servicio
from app.services.inactividad_service import evaluar_actividad, reactivar
from app.services.vencimiento_service import tiene_renovacion_pendiente
from app.services.orquestacion_service import (
    desplegar_pedido,
    detener_servicio,
    iniciar_servicio,
    reiniciar_servicio,
    eliminar_servicio,
    requiere_propio_o_admin,
    sincronizar_estado,
    sincronizar_estados,
)
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

logger = logging.getLogger(__name__)

from app.schemas.servicio import RenovacionRequest, ModificacionVigenciaRequest
from app.schemas.servicio import AccesoServicioResponse, AccesoReveladoResponse, RevelarAccesoRequest, VerificarAccesoRequest
from app.schemas.regularizacion import EvaluarRegularizacion,ConfirmarRegularizacion,ArchivarDuplicado

router = APIRouter(prefix="/servicios", tags=["Servicios"])


@router.post('/{servicio_id}/regularizacion/evaluar')
async def evaluar_regularizacion(servicio_id: int, body: EvaluarRegularizacion, response: Response,
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services import regularizacion_service
    response.headers['Cache-Control'] = 'no-store'
    return await regularizacion_service.evaluar(db,servicio_id,actor=current_user,canonical_id=body.canonico_id)


async def _decision_regularizacion(db,servicio_id,body,current_user,clave,*,archivar=False):
    from app.services import regularizacion_service
    from app.utils.responses import respuesta_decision
    try:
        action=regularizacion_service.archivar_duplicado if archivar else regularizacion_service.confirmar
        result=await action(db,servicio_id,actor=current_user,body=body,clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post('/{servicio_id}/regularizacion')
async def confirmar_regularizacion(servicio_id: int,body: ConfirmarRegularizacion,
    clave: str = Header(alias='Idempotency-Key'),current_user: Usuario = Depends(require_admin),db: AsyncSession = Depends(get_db)):
    return await _decision_regularizacion(db,servicio_id,body,current_user,clave)


@router.post('/{servicio_id}/regularizacion/archivar-duplicado')
async def archivar_duplicado_legacy(servicio_id: int,body: ArchivarDuplicado,
    clave: str = Header(alias='Idempotency-Key'),current_user: Usuario = Depends(require_admin),db: AsyncSession = Depends(get_db)):
    return await _decision_regularizacion(db,servicio_id,body,current_user,clave,archivar=True)


@router.get('/{servicio_id}/historial')
async def historial_del_servicio(servicio_id: int, current_user: Usuario = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    from app.models.servicio_historial import ServicioHistorial
    await requiere_acceso_servicio(db, current_user, servicio_id)
    entries = (await db.scalars(select(ServicioHistorial).where(ServicioHistorial.servicio_id == servicio_id)
                               .order_by(ServicioHistorial.created_at, ServicioHistorial.id))).all()
    return [{'id': entry.id, 'estado_anterior': entry.estado_anterior, 'estado_nuevo': entry.estado_nuevo,
             'comentario': entry.comentario, 'actor_tipo': entry.actor_tipo or ('usuario' if entry.usuario_id else 'sistema'),
             'usuario_id': entry.usuario_id, 'created_at': entry.created_at} for entry in entries]


@router.get('/{servicio_id}/acceso', response_model=AccesoServicioResponse)
async def acceso_del_servicio(servicio_id: int, response: Response, current_user: Usuario = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    from app.services import service_access_service
    response.headers['Cache-Control'] = 'no-store'
    return await service_access_service.metadatos(db, actor=current_user, servicio_id=servicio_id)


@router.post('/{servicio_id}/acceso/revelar', response_model=AccesoReveladoResponse)
async def revelar_acceso(servicio_id: int, body: RevelarAccesoRequest, response: Response,
    current_user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services import service_access_service
    response.headers['Cache-Control'] = 'no-store'
    try:
        result = await service_access_service.revelar(db, actor=current_user, servicio_id=servicio_id)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


@router.post('/{servicio_id}/verificar-acceso')
async def verificar_acceso(servicio_id: int, body: VerificarAccesoRequest,
    key: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db)):
    from app.services import verificacion_acceso_service
    from app.utils.responses import respuesta_decision
    try:
        result = await verificacion_acceso_service.verificar(db, actor=current_user, servicio_id=servicio_id, body=body, clave=key)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.get('/{servicio_id}/consola')
async def consola_del_servicio(servicio_id: int, current_user: Usuario = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    await requiere_acceso_servicio(db, current_user, servicio_id)
    # No se habilita un enlace nativo sin la comprobación institucional T101.
    raise HTTPException(status_code=409, detail={'codigo': 'consola_no_habilitada',
        'mensaje': 'Falta comprobar aislamiento y revocación de sesiones de consola'})


@router.get("/", response_model=list[ServicioResponse])
async def listar_servicios(
    modelo_servicio: Literal['iaas', 'paas', 'saas'] | None = None,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista servicios vigentes. Admin ve todos, cátedra ve solo los suyos.

    Devuelve el último estado registrado y la fecha/fuente de confirmación.
    El worker reconcilia infraestructura; esta consulta no hace llamadas a PVE.
    """
    query = excluir_dados_de_baja(select(Servicio), Servicio).order_by(
        Servicio.deployed_at.desc()
    )
    if modelo_servicio:
        query = query.where(Servicio.modelo_servicio == modelo_servicio)

    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(
            Servicio.catedra_id.in_(await catedras_visibles(db, current_user))
        )

    result = await db.execute(query)
    return await sincronizar_estados(db, list(result.scalars().all()), usuario=current_user)


@router.get("/pausados", response_model=list[ServicioPausadoResponse])
async def listar_pausados(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Servicios pausados, del más antiguo al más reciente.

    Pausar libera cómputo y memoria, pero **no** almacenamiento. Un servicio
    pausado hace meses sigue ocupando disco sin que nadie lo note, así que el
    administrador necesita verlos juntos para decidir cuáles dar de baja.
    """
    result = await db.execute(
        excluir_dados_de_baja(select(Servicio), Servicio)
        .where(Servicio.estado == EstadoServicio.PAUSED)
        .order_by(Servicio.pausado_auto_at.asc().nulls_last())
    )
    ahora = datetime.utcnow()
    return [
        ServicioPausadoResponse(
            id=s.id,
            catedra_id=s.catedra_id,
            hostname=s.hostname,
            ram_asignada_mb=s.ram_asignada_mb,
            disk_asignado_gb=s.disk_asignado_gb,
            pausado_auto_at=s.pausado_auto_at,
            dias_pausado=(
                (ahora - s.pausado_auto_at).days if s.pausado_auto_at else None
            ),
        )
        for s in result.scalars().all()
    ]


@router.get("/exentos-inactivos", response_model=list[ServicioResponse])
async def listar_exentos_inactivos(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Servicios marcados "siempre encendido" que igual están sin uso.

    La exención existe para proteger a los servicios que deben seguir arriba sin
    tráfico aparente, pero tiene el riesgo espejo de que todo el mundo la marque
    y el pausado automático deje de recuperar nada. Esta lista es el contrapeso:
    hace visible el uso de la excepción sin quitársela a nadie.
    """
    result = await db.execute(
        excluir_dados_de_baja(select(Servicio), Servicio).where(
            Servicio.exento_pausado.is_(True),
            Servicio.estado == EstadoServicio.RUNNING,
        )
    )
    inactivos = []
    for servicio in result.scalars().all():
        veredicto = await evaluar_actividad(db, servicio)
        if veredicto["inactivo"]:
            inactivos.append(servicio)
    return inactivos


@router.get("/{servicio_id}", response_model=ServicioResponse)
async def obtener_servicio(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene el último estado, las operaciones y la cobertura del servicio."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    return await sincronizar_estado(db, servicio, usuario=current_user)


@router.post("/desplegar/{pedido_id}")
async def desplegar(pedido_id: int, body: DesplegarSnapshotRequest,
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.admision_service import desplegar as admitir
    from app.utils.responses import respuesta_decision
    try:
        result = await admitir(db, pedido_id, actor=current_user, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{servicio_id}/start")
async def iniciar(servicio_id: int, body: OrdenServicioRequest = OrdenServicioRequest(),
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.utils.responses import respuesta_decision
    try:
        result = await iniciar_servicio(db, servicio_id, current_user, clave=clave, motivo=body.motivo)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


async def _orden(db, servicio_id, user, *, tipo, clave):
    from app.services.operacion_service import admitir_orden
    from app.utils.responses import respuesta_decision
    try:
        result = await admitir_orden(db, servicio_id, tipo=tipo, usuario=user, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{servicio_id}/stop")
async def detener(servicio_id: int, body: DesplegarSnapshotRequest = DesplegarSnapshotRequest(),
    clave: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await _orden(db, servicio_id, current_user, tipo='detener', clave=clave)


@router.post("/{servicio_id}/restart")
@router.post("/{servicio_id}/reboot")
async def reiniciar(servicio_id: int, body: DesplegarSnapshotRequest = DesplegarSnapshotRequest(),
    clave: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await _orden(db, servicio_id, current_user, tipo='reiniciar', clave=clave)


@router.get("/{servicio_id}/metricas")
async def metricas_en_tiempo_real(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consulta y devuelve las métricas en tiempo real de Proxmox para este servicio."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    from app.services.metricas_service import capturar_snapshot_servicio, obtener_ultimo_snapshot
    snapshot = await capturar_snapshot_servicio(db, servicio)
    if not snapshot:
        snapshot = await obtener_ultimo_snapshot(db, servicio.id)

    return {
        "servicio_id": servicio_id,
        "estado": servicio.estado.value,
        "cpu_usage_percent": snapshot.cpu_usage_percent if snapshot else 0.0,
        "ram_usage_mb": snapshot.ram_usage_mb if snapshot else 0.0,
        "disk_usage_gb": snapshot.disk_usage_gb if snapshot else 0.0,
        "net_in_bytes": snapshot.net_in_bytes if snapshot else 0.0,
        "net_out_bytes": snapshot.net_out_bytes if snapshot else 0.0,
        "timestamp": snapshot.timestamp if snapshot else datetime.utcnow(),
    }


@router.post("/{servicio_id}/reactivar")
async def reactivar_servicio(servicio_id: int, body: OrdenServicioRequest = OrdenServicioRequest(),
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await iniciar(servicio_id, body, clave, current_user, db)


async def _solicitar_renovacion(db, servicio_id, actor, body, clave, sustituye_id=None):
    from app.services.renovacion_service import solicitar
    from app.utils.responses import respuesta_decision
    try:
        result = await solicitar(db, servicio_id, actor=actor, body=body, clave=clave, sustituye_id=sustituye_id)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{servicio_id}/renovar", status_code=201)
async def renovar_servicio(servicio_id: int, body: RenovacionRequest, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _solicitar_renovacion(db, servicio_id, current_user, body, clave)


@router.post("/{servicio_id}/vigencias/{vigencia_id}/modificaciones", status_code=201)
async def modificar_vigencia(servicio_id: int, vigencia_id: UUID, body: ModificacionVigenciaRequest,
    clave: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _solicitar_renovacion(db, servicio_id, current_user, body, clave, sustituye_id=vigencia_id)


@router.patch("/{servicio_id}", response_model=ServicioResponse)
async def actualizar_servicio(
    servicio_id: int,
    data: ServicioUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cambia la exención de inactividad; las vigencias requieren otra decisión."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    if data.exento_pausado is not None:
        servicio.exento_pausado = data.exento_pausado
        # Marcarlo exento cancela cualquier pausa anunciada: sería incoherente
        # avisar de una pausa que ya no va a ocurrir.
        if data.exento_pausado:
            servicio.pausa_programada_at = None
            servicio.aviso_pausa_at = None


    await db.commit()
    await db.refresh(servicio)
    return (await sincronizar_estados(db, [servicio], usuario=current_user))[0]


@router.get("/consola/proxmox-base")
async def base_consola_proxmox(current_user: Usuario = Depends(get_current_user)):
    raise HTTPException(status_code=405, detail='Usá la consola del servicio concreto autorizado')


@router.delete("/{servicio_id}")
async def eliminar(servicio_id: int, body: DesplegarSnapshotRequest = DesplegarSnapshotRequest(),
    clave: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db)):
    return await _orden(db, servicio_id, current_user, tipo='eliminar', clave=clave)


@router.get("/{servicio_id}/status")
async def estado_en_proxmox(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consulta el estado real del contenedor directamente en Proxmox."""
    from app.services.proxmox_client import get_proxmox_client

    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    if not servicio.proxmox_vmid or not servicio.proxmox_node:
        raise HTTPException(status_code=400, detail="Servicio sin VMID asignado")

    try:
        pve = get_proxmox_client()
        status = pve.get_lxc_status(servicio.proxmox_node, int(servicio.proxmox_vmid))
        # Consultar el estado real es también la ocasión de corregir el registro.
        await sincronizar_estado(db, servicio)
        return {
            "servicio_id": servicio_id,
            "vmid": servicio.proxmox_vmid,
            "node": servicio.proxmox_node,
            "estado": servicio.estado.value,
            "proxmox_status": status,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error consultando Proxmox: {str(exc)}")
