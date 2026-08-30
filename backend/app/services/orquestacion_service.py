"""Servicio de orquestación: despliega y gestiona recursos reales en Proxmox VE."""

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido, TipoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario, RolUsuario
from app.services.proxmox_client import get_proxmox_client
from app.services import historial_service
from app.services.acceso_service import es_visible
from app.services.vencimiento_service import vencimiento_por_defecto
from app.services.pedido_service import cambiar_estado

logger = logging.getLogger(__name__)


# Traducción del `status` que reporta Proxmox al estado que persiste el portal.
# Lo que Proxmox no sepa clasificar no se mapea: preferimos no tocar el registro
# antes que inventar un estado (ver `sincronizar_estados`).
_ESTADO_POR_STATUS_PROXMOX = {
    "running": EstadoServicio.RUNNING,
    "stopped": EstadoServicio.STOPPED,
    "paused": EstadoServicio.PAUSED,
    "suspended": EstadoServicio.PAUSED,
}



async def requiere_propio_o_admin(
    db: AsyncSession, servicio: Servicio, usuario: Usuario
) -> None:
    """
    Autorización de servicios: admin pasa siempre; cátedra solo sobre lo suyo.

    Centraliza el chequeo que antes estaba duplicado en cada endpoint de
    lectura (``obtener_servicio``, ``estado_en_proxmox``) y que las acciones
    de apagar/encender/reiniciar/consola multiplicarían si se siguiera
    duplicando.

    "Lo suyo" pasó de ser una cátedra a ser un conjunto: una persona puede
    tener varias. La pertenencia se resuelve en ``acceso_service``, que es la
    única fuente de esa respuesta.
    """
    if usuario.rol == RolUsuario.ADMIN:
        return
    if not await es_visible(db, usuario, servicio.catedra_id):
        raise HTTPException(status_code=403, detail="Sin permisos")


def _estados_reales_del_cluster() -> dict[int, EstadoServicio] | None:
    """
    Estado real de cada LXC del clúster, indexado por VMID.

    Una sola llamada a `cluster/resources` cubre todos los nodos, así que
    reconciliar N servicios no cuesta N requests contra Proxmox.

    Devuelve ``None`` si Proxmox no responde (clúster apagado, red caída): en
    ese caso no se sabe nada del estado real y el portal conserva lo último
    conocido en lugar de marcar todo como caído.
    """
    try:
        recursos = get_proxmox_client().listar_lxc_del_cluster()
    except Exception as exc:
        logger.warning(f"No se pudo consultar el estado real de los contenedores: {exc}")
        return None

    estados: dict[int, EstadoServicio] = {}
    for recurso in recursos:
        vmid = recurso.get("vmid")
        estado = _ESTADO_POR_STATUS_PROXMOX.get(recurso.get("status"))
        if vmid is not None and estado is not None:
            estados[int(vmid)] = estado
    return estados


def _existe_en_el_cluster(pve, vmid: int) -> bool | None:
    """
    ¿El contenedor sigue existiendo en el clúster? ``None`` si no se pudo saber.

    La distinción importa: "no existe" habilita cerrar el registro, mientras
    que "no se pudo verificar" obliga a ser conservador y no marcar nada.
    """
    try:
        return any(
            int(r.get("vmid", -1)) == vmid for r in pve.listar_lxc_del_cluster()
        )
    except Exception as exc:
        logger.warning(f"No se pudo verificar si el VMID {vmid} sigue en el clúster: {exc}")
        return None


async def sincronizar_estados(
    db: AsyncSession,
    servicios: list[Servicio],
) -> list[Servicio]:
    """
    Reconcilia el estado guardado de cada servicio con el real en Proxmox.

    Proxmox es la fuente de verdad: el registro del portal se desfasa cuando el
    clúster se apaga y vuelve, cuando alguien toca el contenedor desde Proxmox,
    o cuando una acción falla a mitad de camino. Sin esta reconciliación la
    vista ofrecía "Detener" sobre un contenedor ya apagado y rechazaba
    "Iniciar" con un 409 porque el registro seguía diciendo RUNNING.

    Marca cada servicio con dos atributos de instancia (no persistidos) para
    que el frontend pueda decir la verdad en cada caso:

      - `estado_sincronizado`: el estado se confirmó contra Proxmox.
      - `existe_en_proxmox`: True/False, o None si no se pudo averiguar.

    Un contenedor que ya no figura en el clúster no cambia de estado — el
    registro conserva el último conocido y queda marcado como inexistente. Dar
    de baja el registro es una decisión del administrador, no un efecto
    colateral de listar.
    """
    reales = _estados_reales_del_cluster()
    cambios = 0

    for servicio in servicios:
        real = None
        if reales is not None and servicio.proxmox_vmid:
            real = reales.get(int(servicio.proxmox_vmid))

        servicio.estado_sincronizado = real is not None
        # Sin VMID nunca hubo contenedor, y sin respuesta del clúster no hay
        # nada que afirmar: en ambos casos "no se sabe", que no es lo mismo
        # que "no existe".
        desconocido = reales is None or not servicio.proxmox_vmid
        servicio.existe_en_proxmox = None if desconocido else real is not None

        if real is None or servicio.estado == real:
            continue

        # Una pausa del portal se ejecuta deteniendo el contenedor, así que
        # Proxmox lo reporta como "stopped" — igual que si lo hubiera apagado la
        # cátedra. Sin esta excepción, la sincronización borraría la marca de
        # pausa en la primera consulta y se perdería la distinción entre "lo
        # apagué yo" y "me lo pausó el sistema", que es justamente lo que la
        # cátedra necesita saber. La distinción vive en el portal porque en
        # Proxmox no existe.
        if servicio.pausado_auto_at is not None and real == EstadoServicio.STOPPED:
            continue

        # Si en cambio el contenedor volvió a arrancar (alguien lo encendió
        # desde Proxmox), la pausa dejó de ser cierta y la marca se limpia.
        if servicio.pausado_auto_at is not None and real == EstadoServicio.RUNNING:
            servicio.pausado_auto_at = None
            servicio.pausa_programada_at = None
            servicio.aviso_pausa_at = None

        logger.info(
            f"Servicio {servicio.id} (VMID={servicio.proxmox_vmid}): estado "
            f"registrado {servicio.estado.value} → real {real.value}"
        )
        servicio.estado = real
        cambios += 1

    if cambios:
        await db.commit()

    return servicios


async def sincronizar_estado(db: AsyncSession, servicio: Servicio) -> Servicio:
    """Reconcilia un único servicio contra Proxmox. Ver `sincronizar_estados`."""
    await sincronizar_estados(db, [servicio])
    return servicio


def _generar_hostname(catedra_id: int, pedido_id: int) -> str:
    """Genera un hostname único para el contenedor."""
    return f"cat{catedra_id}-svc{pedido_id}"


def _construir_config_lxc(
    vmid: int,
    hostname: str,
    template: RecursoTemplate,
    pedido: Pedido,
    node: str,
    storage: str = "local-lvm",
) -> dict:
    """
    Construye los parámetros de creación del LXC para la API de Proxmox.

    Los recursos (cores, memoria, disco) salen de lo que el pedido **reservó al
    aprobarse**, no de los valores actuales del template. La plantilla aporta el
    resto: la imagen del sistema operativo y los overrides de `config_extra`.

    El motivo es la correspondencia entre lo aprobado y lo entregado (FR-018):
    aprobar compromete capacidad y guarda esos tres números en el pedido. Si acá
    se leyera el template, editarlo entre la aprobación y el despliegue haría que
    el contenedor naciera con recursos que nadie aprobó, sobrecomprometiendo el
    clúster sin dejar rastro. La reserva es el contrato; el template solo define
    el punto de partida en el momento de pedir.
    """
    config = {
        "vmid": vmid,
        "hostname": hostname,
        "cores": pedido.reserva_vcpus,
        "memory": pedido.reserva_ram_mb,
        "rootfs": f"{storage}:{pedido.reserva_disk_gb}",
        "net0": "name=eth0,bridge=vmbr0,ip=dhcp",
        "start": 1,          # arranca automáticamente al crear
        "unprivileged": 1,   # contenedor sin privilegios (más seguro)
    }

    # Si el template tiene un OS template configurado, usarlo
    if template.os_template:
        config["ostemplate"] = template.os_template

    # Mergear config_extra del template si existe (permite overrides avanzados)
    if template.config_extra:
        config.update(template.config_extra)

    return config


def _resolver_vmid(pve, pedido: Pedido, hostname: str) -> tuple[int, dict | None]:
    """
    Decide qué VMID usar para (re)desplegar un pedido.

    Devuelve `(vmid, contenedor_existente)`. Cuando `contenedor_existente` no es
    None se trata de un huérfano de un fallo parcial propio: el contenedor ya
    está creado en el clúster y debe adoptarse en lugar de crear otro.

    Matriz (ver contracts/api.md y research R2):
      sin reserva                        -> VMID nuevo
      reserva libre                      -> reutilizar
      reserva ocupada, hostname propio   -> adoptar
      reserva ocupada, hostname ajeno    -> VMID nuevo
    """
    if not pedido.vmid_reservado:
        return pve.get_next_vmid(), None

    reservado = int(pedido.vmid_reservado)
    ocupante = next(
        (
            r
            for r in pve.listar_lxc_del_cluster()
            if int(r.get("vmid", -1)) == reservado
        ),
        None,
    )

    if ocupante is None:
        # La reserva sigue libre: se reutiliza.
        return reservado, None

    if ocupante.get("name") == hostname:
        # Es nuestro: quedó creado por un fallo parcial anterior.
        logger.warning(
            f"VMID {reservado} ya existe con hostname propio '{hostname}'. "
            f"Se adopta el contenedor en lugar de crear uno nuevo."
        )
        return reservado, ocupante

    # Lo tomó un tercero: se descarta la reserva.
    logger.warning(
        f"VMID reservado {reservado} fue tomado por '{ocupante.get('name')}'. "
        f"Se solicita uno nuevo."
    )
    return pve.get_next_vmid(), None


async def _ejecutar_despliegue(
    db: AsyncSession,
    pedido: Pedido,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Aprovisiona el recurso en Proxmox para un pedido que ya está en EN_DESPLIEGUE.

    Punto de entrada compartido por el despliegue inicial y el reintento: ambos
    caminos difieren solo en la validación del estado previo, de modo que no
    puedan divergir (research R5).

    En caso de falla transiciona el pedido a ERROR y levanta 502.
    """
    template = await db.get(RecursoTemplate, pedido.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template del pedido no encontrado")

    # Solo LXC por ahora (QEMU se agrega en iteración futura)
    if template.tipo != TipoRecurso.LXC:
        raise HTTPException(
            status_code=400,
            detail="Solo se soporta despliegue de contenedores LXC en esta versión",
        )

    pve = get_proxmox_client()
    hostname = _generar_hostname(pedido.catedra_id, pedido.id)

    try:
        vmid, adoptado = _resolver_vmid(pve, pedido, hostname)

        # Persistir la reserva ANTES de tocar Proxmox: si la creación falla, el
        # VMID queda registrado y un reintento puede reutilizarlo (research R1).
        if pedido.vmid_reservado != str(vmid):
            pedido.vmid_reservado = str(vmid)
            await db.commit()

        if adoptado is not None:
            node = adoptado.get("node") or node
            logger.info(f"Adoptando contenedor existente VMID={vmid} en nodo {node}")
        else:
            # Elegir nodo automáticamente si no se especificó
            if not node:
                nodes = pve.get_nodes()
                online = [n for n in nodes if n.get("status") == "online"]
                if not online:
                    raise RuntimeError("No hay nodos Proxmox disponibles (online)")
                # Elegir el nodo con menos carga de CPU
                node = min(online, key=lambda n: n.get("cpu", 1))["node"]

            config = _construir_config_lxc(
                vmid, hostname, template, pedido, node, storage
            )

            logger.info(
                f"Desplegando LXC: VMID={vmid}, hostname={hostname}, node={node}, "
                f"template={template.nombre}"
            )

            # Proxmox devuelve un identificador de tarea y vuelve enseguida: la
            # creación real ocurre después. Hay que esperarla, o un fallo dentro
            # de la tarea (plantilla inexistente, disco lleno, VMID en conflicto)
            # pasaría inadvertido y el portal registraría como desplegado un
            # contenedor que nunca existió.
            task_id = pve.create_lxc(node, **config)
            pve.esperar_task(node, task_id)

            logger.info(f"LXC creado en Proxmox. Task: {task_id}, VMID: {vmid}")

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Error al desplegar pedido {pedido.id}: {error_msg}")

        # Transicionar a ERROR con descripción
        await cambiar_estado(
            db=db,
            pedido_id=pedido.id,
            nuevo_estado_str=EstadoPedido.ERROR.value,
            usuario=admin,
            comentario=f"Error Proxmox: {error_msg[:200]}",
            origen_sistema=True,
        )

        raise HTTPException(
            status_code=502,
            detail=f"Error al crear recurso en Proxmox: {error_msg}",
        )

    # --- Registrar Servicio en la DB ---
    servicio = Servicio(
        catedra_id=pedido.catedra_id,
        pedido_id=pedido.id,
        template_id=pedido.template_id,
        proxmox_vmid=str(vmid),
        proxmox_node=node,
        tipo=template.tipo.value,
        estado=EstadoServicio.RUNNING,
        hostname=hostname,
        # Lo reservado, lo desplegado y lo registrado tienen que coincidir
        # siempre (FR-018): si acá se guardara el template, el consumo que el
        # portal contabiliza dejaría de ser el que el clúster tiene de verdad.
        vcpus_asignados=pedido.reserva_vcpus,
        ram_asignada_mb=pedido.reserva_ram_mb,
        disk_asignado_gb=pedido.reserva_disk_gb,
        deployed_at=datetime.utcnow(),
        # Todo servicio nace con fecha de fin conocida. Es la vía determinista
        # de recuperación de capacidad: no depende de medir nada, y la cátedra
        # sabe desde el primer día hasta cuándo lo tiene.
        vence_at=vencimiento_por_defecto(),
    )
    db.add(servicio)
    await db.flush()

    # --- Transicionar pedido a ACTIVO ---
    detalle = "adoptado" if adoptado is not None else "desplegado"
    await cambiar_estado(
        db=db,
        pedido_id=pedido.id,
        nuevo_estado_str=EstadoPedido.ACTIVO.value,
        usuario=admin,
        comentario=(
            f"Contenedor {detalle}: VMID={vmid}, nodo={node}, hostname={hostname}"
        ),
        origen_sistema=True,
    )

    await db.commit()
    await db.refresh(servicio)

    logger.info(f"Pedido {pedido.id} desplegado exitosamente → Servicio ID={servicio.id}")
    return servicio


async def desplegar_pedido(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Orquesta el despliegue completo de un pedido APROBADO:
    1. Valida que el pedido esté en estado APROBADO
    2. Transiciona a EN_DESPLIEGUE
    3. Delega el aprovisionamiento en `_ejecutar_despliegue`

    En caso de falla, el pedido queda en ERROR con el mensaje.
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido or pedido.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado != EstadoPedido.APROBADO:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden desplegar pedidos APROBADOS. Estado actual: {pedido.estado.value}",
        )

    # Un alta y una renovación atraviesan la misma máquina de estados, pero la
    # transición a ACTIVO la concreta un ejecutor distinto: una crea un
    # contenedor, la otra solo corre la fecha de fin de uno que ya existe.
    # Reutilizar el circuito es lo que hace que "renovar es pedirlo de nuevo"
    # sea literal y no una copia parecida.
    es_renovacion = pedido.tipo == TipoPedido.RENOVACION
    comentario = (
        "Aplicando renovación" if es_renovacion else "Iniciando despliegue en Proxmox VE"
    )

    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.EN_DESPLIEGUE.value,
        usuario=admin,
        comentario=comentario,
        origen_sistema=True,
    )

    if es_renovacion:
        return await _ejecutar_renovacion(db, pedido, admin)

    return await _ejecutar_despliegue(db, pedido, admin, node, storage)


async def _ejecutar_renovacion(
    db: AsyncSession, pedido: Pedido, admin: Usuario
) -> Servicio:
    """Corre la fecha de vencimiento del servicio. No toca Proxmox.

    El servicio conserva su id, sus datos y su contenedor: renovar no recrea
    nada. Si lo recreara, la cátedra perdería todo lo que tenía adentro cada vez
    que le extienden el plazo.
    """
    servicio = await db.get(Servicio, pedido.servicio_id) if pedido.servicio_id else None
    if servicio is None or servicio.deleted_at is not None:
        await cambiar_estado(
            db=db,
            pedido_id=pedido.id,
            nuevo_estado_str=EstadoPedido.ERROR.value,
            usuario=admin,
            comentario="El servicio a renovar ya no existe",
            origen_sistema=True,
        )
        raise HTTPException(
            status_code=409, detail="El servicio a renovar ya no existe"
        )

    anterior = servicio.vence_at
    # Se extiende desde hoy, no desde el vencimiento viejo: una renovación
    # aprobada tarde no debería valer menos que una aprobada a tiempo.
    servicio.vence_at = vencimiento_por_defecto()
    servicio.aviso_vencimiento_at = None

    db.add(
        historial_service.registrar_servicio(
            servicio.id,
            servicio.estado.value,
            servicio.estado.value,
            comentario=(
                f"Renovado: vencía el {anterior:%Y-%m-%d}, "
                f"ahora vence el {servicio.vence_at:%Y-%m-%d}"
                if anterior
                else f"Renovado: vence el {servicio.vence_at:%Y-%m-%d}"
            ),
            usuario=admin,
        )
    )
    await db.commit()

    await cambiar_estado(
        db=db,
        pedido_id=pedido.id,
        nuevo_estado_str=EstadoPedido.ACTIVO.value,
        usuario=admin,
        comentario=f"Renovación aplicada hasta el {servicio.vence_at:%Y-%m-%d}",
        origen_sistema=True,
    )

    await db.refresh(servicio)
    return servicio


async def reintentar_despliegue(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Reintenta el despliegue de un pedido que quedó en ERROR.

    Es el ejecutor real de la transición ERROR → EN_DESPLIEGUE, que la máquina de
    estados declaraba válida pero que ningún código concretaba: el pedido quedaba
    atascado sin posibilidad de recuperación (research R5).

    Es pseudo-idempotente: reutiliza el VMID reservado o adopta el contenedor si
    quedó creado por un fallo parcial, de modo que repetirlo no duplica recursos.
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido or pedido.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado != EstadoPedido.ERROR:
        raise HTTPException(
            status_code=409,
            detail=(
                "Solo se pueden reintentar pedidos en estado ERROR. "
                f"Estado actual: {pedido.estado.value}"
            ),
        )

    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.EN_DESPLIEGUE.value,
        usuario=admin,
        comentario="Reintentando despliegue en Proxmox VE",
        origen_sistema=True,
    )

    return await _ejecutar_despliegue(db, pedido, admin, node, storage)


async def detener_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """Detiene un servicio activo en Proxmox. La cátedra puede detener los propios."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    await requiere_propio_o_admin(db, servicio, usuario)

    # Contra el estado real, no contra el que quedó guardado: si el contenedor
    # ya está apagado en Proxmox, el 409 dice la verdad.
    await sincronizar_estado(db, servicio)

    if servicio.estado != EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está en ejecución (estado: {servicio.estado.value})",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.stop_lxc(servicio.proxmox_node, vmid)
        servicio.estado = EstadoServicio.STOPPED
        servicio.estado_sincronizado = True
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} detenido (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al detener: {str(exc)}")

    return servicio


async def iniciar_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """
    Inicia un servicio que no está corriendo. La cátedra puede iniciar los propios.

    Acepta cualquier estado que no sea RUNNING (detenido, pausado o en error):
    encender es la salida natural de todos ellos, y ese es justo el caso en que
    el portal quedó desfasado y hay que poder recuperar el contenedor. El
    estado se reconcilia antes contra Proxmox para no rechazar un arranque
    válido por un registro viejo.
    """
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    await requiere_propio_o_admin(db, servicio, usuario)

    await sincronizar_estado(db, servicio)

    if servicio.estado == EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail="El servicio ya está en ejecución",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.start_lxc(servicio.proxmox_node, vmid)
        servicio.estado = EstadoServicio.RUNNING
        servicio.estado_sincronizado = True
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} iniciado (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al iniciar: {str(exc)}")

    return servicio


async def reiniciar_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """Reinicia un servicio en ejecución en Proxmox. La cátedra puede reiniciar los propios."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    await requiere_propio_o_admin(db, servicio, usuario)

    await sincronizar_estado(db, servicio)

    if servicio.estado != EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está en ejecución (estado: {servicio.estado.value})",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.reboot_lxc(servicio.proxmox_node, vmid)
        # El servicio sigue RUNNING antes y después: el reinicio lo gestiona
        # Proxmox internamente, no hay estado intermedio que persistir.
        logger.info(f"Servicio {servicio_id} reiniciado (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al reiniciar: {str(exc)}")

    return servicio




async def eliminar_servicio(
    db: AsyncSession,
    servicio_id: int,
    admin: Usuario,
) -> dict:
    """
    Da de baja un servicio: libera el contenedor en Proxmox y marca el registro.

    La baja es lógica: la fila permanece para poder reconstruir el consumo
    histórico de la cátedra aunque el contenedor ya no exista (FR-007).

    El orden importa: si no se pudo liberar el recurso real, el registro NO se
    marca como dado de baja (FR-010). Lo contrario dejaría un contenedor vivo
    consumiendo cuota del clúster sin figurar en ningún listado.
    """
    servicio = await db.get(Servicio, servicio_id)
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    if servicio.deleted_at is not None:
        return {
            "message": f"El servicio {servicio_id} ya estaba dado de baja",
            "vmid": servicio.proxmox_vmid,
            "deleted_at": servicio.deleted_at,
        }

    # Un servicio que nunca llegó a desplegarse no tiene recurso real que liberar
    if servicio.proxmox_vmid and servicio.proxmox_node:
        pve = get_proxmox_client()
        vmid = int(servicio.proxmox_vmid)
        node = servicio.proxmox_node
        try:
            # Detener primero si está corriendo: Proxmox se niega a destruir un
            # contenedor vivo. Hay que **esperar la tarea** de apagado, no dormir
            # un rato y confiar: el apagado es asíncrono como todo en Proxmox, y
            # una pausa fija falla en cuanto el clúster está cargado (visto en la
            # validación T041 del 2026-08-30: "unable to destroy CT - container
            # is running", con el stop ya enviado).
            status = pve.get_lxc_status(node, vmid)
            if status.get("status") == "running":
                pve.esperar_task(node, pve.stop_lxc(node, vmid))

            pve.esperar_task(node, pve.delete_lxc(node, vmid))
            logger.info(f"Servicio {servicio_id} eliminado de Proxmox (VMID={vmid})")

        except Exception as exc:
            # Que falle no siempre significa que el recurso siga ocupado: si el
            # contenedor ya no existe (lo borraron desde Proxmox), el objetivo
            # de FR-010 está cumplido igual y el registro debe poder cerrarse;
            # de lo contrario quedaría trabado para siempre. Solo se aborta si
            # el contenedor sigue vivo, o si no se puede verificar.
            if _existe_en_el_cluster(pve, vmid) is not False:
                raise HTTPException(
                    status_code=502,
                    detail=f"Error al eliminar en Proxmox: {str(exc)}",
                )
            logger.warning(
                f"El contenedor VMID={vmid} ya no existe en Proxmox ({exc}). "
                f"Se da de baja el registro del servicio {servicio_id} igualmente."
            )

    # Recién ahora, con el recurso real liberado, se marca la baja
    servicio.deleted_at = datetime.utcnow()
    await db.commit()

    return {
        "message": f"Servicio {servicio_id} dado de baja correctamente",
        "vmid": servicio.proxmox_vmid,
        "deleted_at": servicio.deleted_at,
    }
