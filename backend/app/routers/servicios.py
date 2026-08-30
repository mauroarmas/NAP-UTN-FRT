import asyncio
import logging
import ssl
from datetime import datetime
from urllib.parse import quote

import websockets
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
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
    ConsolaTicketResponse,
)
from app.services import historial_service
from app.services.acceso_service import catedras_visibles
from app.services.inactividad_service import evaluar_actividad, reactivar
from app.services.vencimiento_service import tiene_renovacion_pendiente
from app.services.orquestacion_service import (
    desplegar_pedido,
    detener_servicio,
    iniciar_servicio,
    reiniciar_servicio,
    eliminar_servicio,
    emitir_ticket_consola,
    consumir_ticket_consola,
    requiere_propio_o_admin,
    sincronizar_estado,
    sincronizar_estados,
)
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/servicios", tags=["Servicios"])


@router.get("/", response_model=list[ServicioResponse])
async def listar_servicios(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista servicios vigentes. Admin ve todos, cátedra ve solo los suyos.

    El estado que devuelve es el real del clúster, no el último que quedó
    guardado: se reconcilia contra Proxmox en cada consulta (una sola llamada
    para toda la lista) para que los botones de encender/apagar correspondan a
    lo que el contenedor está haciendo ahora.
    """
    query = excluir_dados_de_baja(select(Servicio), Servicio).order_by(
        Servicio.deployed_at.desc()
    )

    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(
            Servicio.catedra_id.in_(await catedras_visibles(db, current_user))
        )

    result = await db.execute(query)
    return await sincronizar_estados(db, list(result.scalars().all()))


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
    """Obtiene un servicio vigente por ID, con el estado reconciliado contra Proxmox."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    return await sincronizar_estado(db, servicio)


@router.post("/desplegar/{pedido_id}", response_model=ServicioResponse)
async def desplegar(
    pedido_id: int,
    body: DesplegarRequest = DesplegarRequest(),
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Despliega un pedido APROBADO creando el LXC en Proxmox VE.
    Ejecuta la transición completa: APROBADO → EN_DESPLIEGUE → ACTIVO (o ERROR).
    """
    return await desplegar_pedido(
        db=db,
        pedido_id=pedido_id,
        admin=current_user,
        node=body.node,
        storage=body.storage,
    )


@router.post("/{servicio_id}/start", response_model=ServicioResponse)
async def iniciar(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Inicia un servicio detenido en Proxmox. La cátedra puede iniciar los propios."""
    return await iniciar_servicio(db, servicio_id, current_user)


@router.post("/{servicio_id}/stop", response_model=ServicioResponse)
async def detener(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detiene un servicio en ejecución en Proxmox. La cátedra puede detener los propios."""
    return await detener_servicio(db, servicio_id, current_user)


@router.post("/{servicio_id}/restart", response_model=ServicioResponse)
async def reiniciar(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reinicia un servicio en ejecución en Proxmox. La cátedra puede reiniciar los propios."""
    return await reiniciar_servicio(db, servicio_id, current_user)


@router.post("/{servicio_id}/reactivar", response_model=ServicioResponse)
async def reactivar_servicio(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vuelve a encender un servicio pausado. La cátedra puede hacerlo sola.

    No requiere pedido nuevo ni aprobación: si hiciera falta, el pausado
    automático sería una denegación de servicio encubierta.

    Códigos: 200 reactivado · 403 el servicio no es de una cátedra propia ·
    409 el servicio no está pausado, o el clúster no tiene capacidad libre (en
    ese caso queda pausado, nunca en error) · 502 falló la infraestructura.
    """
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)
    return await reactivar(db, servicio, current_user)


@router.post("/{servicio_id}/renovar", status_code=201)
async def renovar_servicio(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Solicita extender la fecha de fin de un servicio.

    Crea un pedido de renovación que atraviesa el mismo circuito de aprobación
    que un pedido nuevo: el administrador lo ve con la misma información de
    capacidad. Así el mismo punto de control que otorga los recursos es el que
    los recupera.

    No reserva capacidad: el servicio ya está desplegado y ya cuenta como
    consumo. Contarlo otra vez sería contabilidad doble.

    Códigos: 201 solicitud creada · 403 el servicio no es de una cátedra propia ·
    409 ya hay una renovación pendiente de resolución.
    """
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )
    await requiere_propio_o_admin(db, servicio, current_user)

    if await tiene_renovacion_pendiente(db, servicio.id):
        raise HTTPException(
            status_code=409,
            detail="Ya hay una renovación pendiente para este servicio",
        )

    pedido = Pedido(
        catedra_id=servicio.catedra_id,
        solicitante_id=current_user.id,
        template_id=servicio.template_id,
        estado=EstadoPedido.SOLICITADO,
        tipo=TipoPedido.RENOVACION,
        servicio_id=servicio.id,
    )
    db.add(pedido)
    await db.flush()
    db.add(
        historial_service.registrar_pedido(
            pedido.id,
            "nuevo",
            EstadoPedido.SOLICITADO.value,
            comentario=f"Renovación solicitada para el servicio #{servicio.id}",
            usuario=current_user,
        )
    )
    await db.commit()
    await db.refresh(pedido)

    return {
        "pedido_id": pedido.id,
        "servicio_id": servicio.id,
        "estado": pedido.estado.value,
        "mensaje": "La renovación quedó pendiente de aprobación",
    }


@router.patch("/{servicio_id}", response_model=ServicioResponse)
async def actualizar_servicio(
    servicio_id: int,
    data: ServicioUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marca "siempre encendido" (cátedra) y fecha de vencimiento (admin)."""
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

    if data.vence_at is not None:
        if current_user.rol != RolUsuario.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Solo un administrador puede cambiar la fecha de vencimiento",
            )
        servicio.vence_at = data.vence_at
        servicio.aviso_vencimiento_at = None

    await db.commit()
    await db.refresh(servicio)
    return servicio


@router.get("/consola/proxmox-base")
async def base_consola_proxmox(current_user: Usuario = Depends(require_admin)):
    """
    Devuelve la URL base de la interfaz de Proxmox, para que el admin pueda
    abrir la consola nativa en otra pestaña.

    Solo administrador: la cátedra nunca debe llegar a la interfaz de Proxmox
    (Principio I de la constitución). El admin sí tiene cuenta propia en
    Proxmox, así que para él es un atajo, no una vía de escape del portal.
    """
    settings = get_settings()
    return {"base_url": f"https://{settings.proxmox_host}:{settings.proxmox_port}"}


@router.post("/{servicio_id}/console-ticket", response_model=ConsolaTicketResponse)
async def pedir_ticket_consola(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Emite un ticket de un solo uso para abrir la consola interactiva del servicio.

    El navegador usa este ticket (no credenciales de Proxmox) para abrir el
    WebSocket de `/servicios/{servicio_id}/console`.

    EN PAUSA (2026-08-15): la consola embebida quedó sin resolver del lado de
    Proxmox y, hasta definir con la cátedra cómo debe gestionarse el acceso al
    contenedor, este endpoint queda restringido a administrador y sin uso desde
    el frontend. Ver DUDAS-ENTREVISTA.md y specs/003-gestion-servicios-catedra.
    """
    return await emitir_ticket_consola(db, servicio_id, current_user)


@router.websocket("/{servicio_id}/console")
async def consola(websocket: WebSocket, servicio_id: int):
    """
    Proxy de consola interactiva: el navegador solo habla con este endpoint.

    Nunca se le devuelve al navegador el host/puerto/ticket de Proxmox — el
    backend abre su propia conexión saliente hacia el `vncwebsocket` de Proxmox
    y relay los bytes en ambas direcciones (Principio I de la constitución;
    ver research.md R2 de la spec 003). Requiere un ticket de un solo uso
    emitido previamente por `POST /servicios/{servicio_id}/console-ticket`.

    EN PAUSA (2026-08-15): el relay se conecta y autentica bien contra Proxmox
    pero la sesión muere sin transmitir. Hipótesis principal sin confirmar:
    Proxmox no acepta API tokens para el websocket de consola y hace falta un
    ticket de sesión (`POST /access/ticket` con usuario+contraseña). El código
    queda acá a la espera de esa definición; ningún cliente lo usa hoy.
    """
    ticket = websocket.query_params.get("ticket")
    datos = consumir_ticket_consola(servicio_id, ticket) if ticket else None
    if datos is None:
        await websocket.close(code=4401, reason="Ticket de consola inválido o vencido")
        return

    # Recién acá se le pide el ticket a Proxmox — inmediatamente antes de
    # conectar, no en el POST previo (ver docstring de emitir_ticket_consola).
    from app.services.proxmox_client import get_proxmox_client

    try:
        termproxy = get_proxmox_client().abrir_termproxy(datos["node"], datos["vmid"])
    except Exception as exc:
        logger.warning(f"No se pudo abrir la consola de servicio {servicio_id}: {exc}")
        await websocket.close(code=1011, reason="No se pudo abrir la consola")
        return

    await websocket.accept()

    settings = get_settings()
    proxmox_ws_url = (
        f"wss://{settings.proxmox_host}:{settings.proxmox_port}"
        f"/api2/json/nodes/{datos['node']}/lxc/{datos['vmid']}/vncwebsocket"
        f"?port={termproxy['port']}&vncticket={quote(termproxy['ticket'], safe='')}"
    )
    ssl_context = ssl.create_default_context()
    if not settings.proxmox_verify_ssl:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    # Autenticación de la conexión saliente: igual que el resto de ProxmoxClient,
    # por API token (no por cookie de sesión) — ver research.md R3 de la spec 003.
    auth_header = "PVEAPIToken={0}!{1}={2}".format(
        settings.proxmox_user, settings.proxmox_token_name, settings.proxmox_token_value
    )

    try:
        async with websockets.connect(
            proxmox_ws_url,
            additional_headers={"Authorization": auth_header},
            subprotocols=["binary"],
            ssl=ssl_context,
        ) as proxmox_ws:

            async def navegador_a_proxmox():
                try:
                    while True:
                        mensaje = await websocket.receive_bytes()
                        await proxmox_ws.send(mensaje)
                except WebSocketDisconnect:
                    pass

            async def proxmox_a_navegador():
                async for mensaje in proxmox_ws:
                    datos_binarios = mensaje if isinstance(mensaje, bytes) else mensaje.encode()
                    await websocket.send_bytes(datos_binarios)

            tareas = [
                asyncio.create_task(navegador_a_proxmox()),
                asyncio.create_task(proxmox_a_navegador()),
            ]
            _, pendientes = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
            for t in pendientes:
                t.cancel()
    except Exception as exc:
        logger.warning(f"Consola de servicio {servicio_id} cerrada con error: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.delete("/{servicio_id}")
async def eliminar(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Da de baja un servicio: libera su contenedor en Proxmox y marca el registro.

    La baja es lógica: la fila permanece para poder reconstruir el consumo
    histórico de la cátedra. Si no se pudo liberar el recurso real, el registro
    no se marca (evita contenedores vivos sin registro operativo).

    Códigos: 200 baja exitosa (o ya estaba dada de baja, idempotente) ·
    403 sin permisos de administrador · 404 servicio inexistente ·
    502 falló la liberación en Proxmox (el registro queda intacto).
    """
    return await eliminar_servicio(db, servicio_id, current_user)


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
