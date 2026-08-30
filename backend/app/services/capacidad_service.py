"""Capacidad del clúster, reserva al aprobar y expiración de reservas.

Fuente única de la contabilidad de capacidad. Reemplaza a la vieja cuota por
cátedra: lo que se eliminó es el *techo declarado por adelantado*, no la
contabilidad — esa se conserva y pasa a ejercerse contra la capacidad real del
clúster en el momento de la aprobación.

Dos mecanismos que suelen confundirse y que resuelven problemas distintos:

- El **bloqueo** serializa la sección crítica, para que dos transacciones
  concurrentes no lean el mismo saldo libre y ambas reserven. Es integridad.
- El **token** detecta que quien confirma está mirando números viejos (la
  pantalla abierta hace media hora, otro admin que aprobó en el medio). Es
  calidad de la decisión.

Con el bloqueo solo, una aprobación sobre datos viejos pasaría — correctamente
serializada, pero mal informada. Con el token solo, quedaría una ventana real
entre el recálculo y el INSERT.
"""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido, Pedido, TipoPedido
from app.models.servicio import EstadoServicio, Servicio
from app.services import historial_service, scheduler
from app.services.proxmox_client import get_proxmox_client

logger = logging.getLogger(__name__)

# Plazo entre aprobar y desplegar. Vencido, la reserva se libera sola: una
# capacidad comprometida que nunca se materializa es una fuga tan silenciosa
# como un contenedor huérfano.
RESERVA_VIGENCIA = timedelta(hours=24)

CLAVE_BLOQUEO = 4001  # arbitraria pero fija: identifica esta sección crítica


class BloqueoCapacidad:
    """Serializa verificación y reserva.

    En PostgreSQL toma un advisory lock de transacción, que se libera solo al
    terminar la transacción. En SQLite no hace nada: el motor ya serializa las
    escrituras, así que las pruebas ejercitan la misma ruta de código sin
    necesitar un mecanismo que no existe.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def __aenter__(self):
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            await self.db.execute(
                select(func.pg_advisory_xact_lock(CLAVE_BLOQUEO))
            )
        return self

    async def __aexit__(self, *exc):
        return False


def bloqueo_capacidad(db: AsyncSession) -> BloqueoCapacidad:
    return BloqueoCapacidad(db)


def _capacidad_fisica(pve) -> dict:
    """Capacidad de los nodos online del clúster."""
    online = [n for n in pve.get_nodes() if n.get("status") == "online"]
    return {
        "vcpus": sum(n.get("maxcpu", 0) for n in online),
        "ram_mb": sum(n.get("maxmem", 0) for n in online) // (1024 * 1024),
        "storage_gb": sum(n.get("maxdisk", 0) for n in online) // (1024**3),
    }


def reservas_vigentes_where():
    """Condición que define una reserva viva.

    Un pedido aprobado de tipo alta cuyo servicio todavía no existe. La reserva
    no es una tabla: es ese estado. Así no hay dos fuentes de verdad que puedan
    divergir, y convertir la reserva en consumo real no es una operación que
    pueda fallar a medias.
    """
    ahora = datetime.utcnow()
    return (
        Pedido.estado == EstadoPedido.APROBADO,
        Pedido.deleted_at.is_(None),
        Pedido.tipo == TipoPedido.ALTA,
        ~Pedido.servicio.has(),
        or_(Pedido.reserva_expira_at.is_(None), Pedido.reserva_expira_at > ahora),
    )


async def _desplegado(db: AsyncSession) -> dict:
    """Consumo de los servicios vigentes.

    vCPU y RAM solo cuentan si el servicio está corriendo: un servicio pausado
    liberó de verdad su cómputo. El disco cuenta siempre, incluso pausado,
    porque pausar no libera almacenamiento.
    """
    corriendo = Servicio.estado == EstadoServicio.RUNNING
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(case((corriendo, Servicio.vcpus_asignados), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((corriendo, Servicio.ram_asignada_mb), else_=0)), 0
            ),
            func.coalesce(func.sum(Servicio.disk_asignado_gb), 0),
        ).where(Servicio.deleted_at.is_(None))
    )
    vcpus, ram, disk = result.one()
    return {"vcpus": int(vcpus), "ram_mb": int(ram), "storage_gb": int(disk)}


async def _reservado(db: AsyncSession) -> dict:
    result = await db.execute(
        select(
            func.coalesce(func.sum(Pedido.reserva_vcpus), 0),
            func.coalesce(func.sum(Pedido.reserva_ram_mb), 0),
            func.coalesce(func.sum(Pedido.reserva_disk_gb), 0),
        ).where(*reservas_vigentes_where())
    )
    vcpus, ram, disk = result.one()
    return {"vcpus": int(vcpus), "ram_mb": int(ram), "storage_gb": int(disk)}


async def _ram_en_riesgo(db: AsyncSession) -> int:
    """Memoria que haría falta si todos los pausados se reactivaran a la vez.

    Sirve para anticipar qué reactivaciones van a fallar, antes de que le fallen
    a una cátedra.
    """
    result = await db.execute(
        select(func.coalesce(func.sum(Servicio.ram_asignada_mb), 0)).where(
            Servicio.estado == EstadoServicio.PAUSED,
            Servicio.deleted_at.is_(None),
        )
    )
    return int(result.scalar_one())


def _token(comprometido: dict) -> str:
    """Huella corta del estado de capacidad comprometida."""
    crudo = f"{comprometido['vcpus']}|{comprometido['ram_mb']}|{comprometido['storage_gb']}"
    return hashlib.sha256(crudo.encode()).hexdigest()[:12]


async def panorama(db: AsyncSession, pve=None) -> dict:
    """Foto completa de capacidad, recalculada en el momento.

    Nunca se cachea: un número de capacidad viejo es exactamente el problema que
    esta feature existe para evitar.
    """
    pve = pve or get_proxmox_client()
    fisica = _capacidad_fisica(pve)
    desplegado = await _desplegado(db)
    reservado = await _reservado(db)

    comprometido = {k: desplegado[k] + reservado[k] for k in fisica}
    libre = {k: fisica[k] - comprometido[k] for k in fisica}

    return {
        "fisica": fisica,
        "desplegado": desplegado,
        "reservado": reservado,
        "comprometido": comprometido,
        "libre": libre,
        "ram_en_riesgo_mb": await _ram_en_riesgo(db),
        "capacidad_token": _token(comprometido),
    }


def costo_de(template) -> dict:
    return {
        "vcpus": template.default_vcpus,
        "ram_mb": template.default_ram_mb,
        "storage_gb": template.default_disk_gb,
    }


def excede(libre: dict, costo: dict) -> bool:
    return any(costo[k] > libre[k] for k in costo)


async def consumo_de_catedra(db: AsyncSession, catedra_id: int) -> dict:
    result = await db.execute(
        select(
            func.coalesce(func.sum(Servicio.vcpus_asignados), 0),
            func.coalesce(func.sum(Servicio.ram_asignada_mb), 0),
            func.coalesce(func.sum(Servicio.disk_asignado_gb), 0),
        ).where(Servicio.catedra_id == catedra_id, Servicio.deleted_at.is_(None))
    )
    vcpus, ram, disk = result.one()
    return {"vcpus": int(vcpus), "ram_mb": int(ram), "storage_gb": int(disk)}


def liberar_reserva(pedido: Pedido) -> dict:
    """Deja de comprometer la capacidad de un pedido. Devuelve lo que liberó.

    Definición **única** de qué significa liberar, compartida por los dos
    caminos que lo hacen: el vencimiento automático y la reversión que ejecuta
    un administrador. Dos copias de esta lógica podrían divergir, y divergir acá
    es capacidad fantasma — comprometida en la contabilidad, sin nada detrás.

    Es idempotente: sobre una reserva ya en cero no hace nada y devuelve ceros.
    Eso cubre sin caso especial a las renovaciones, que reservan cero porque su
    servicio ya cuenta como consumo desplegado.

    No hace commit. Quien la llama decide en qué transacción cae, que es lo que
    permite que la liberación y el cambio de estado sean indivisibles.
    """
    liberado = {
        "vcpus": pedido.reserva_vcpus or 0,
        "ram_mb": pedido.reserva_ram_mb or 0,
        "storage_gb": pedido.reserva_disk_gb or 0,
    }
    pedido.reserva_vcpus = 0
    pedido.reserva_ram_mb = 0
    pedido.reserva_disk_gb = 0
    # Sin esto la reserva liberada seguiría teniendo un vencimiento pendiente y
    # el trabajo periódico la volvería a "vencer", registrando en el historial
    # una expiración que ya no corresponde a nada.
    pedido.reserva_expira_at = None
    return liberado


# --- Trabajo periódico: expiración de reservas -----------------------------


async def expirar_reservas(db: AsyncSession) -> dict:
    """Libera las reservas cuyo despliegue nunca ocurrió.

    Deja el pedido en RECHAZADO con el motivo registrado y el sistema como
    autor. Es la transición APROBADO → RECHAZADO, que hasta esta feature no
    existía en la tabla de transiciones.
    """
    from app.services.pedido_service import transicion_del_sistema

    ahora = datetime.utcnow()
    result = await db.execute(
        select(Pedido).where(
            Pedido.estado == EstadoPedido.APROBADO,
            Pedido.deleted_at.is_(None),
            Pedido.tipo == TipoPedido.ALTA,
            ~Pedido.servicio.has(),
            Pedido.reserva_expira_at.is_not(None),
            Pedido.reserva_expira_at <= ahora,
        )
    )
    vencidos = result.scalars().all()

    for pedido in vencidos:
        await transicion_del_sistema(
            db,
            pedido,
            EstadoPedido.RECHAZADO,
            comentario=(
                f"Reserva vencida el {pedido.reserva_expira_at:%Y-%m-%d %H:%M}: "
                "el despliegue nunca se concretó y la capacidad se liberó"
            ),
        )
        pedido.motivo_rechazo = "Reserva de capacidad vencida sin despliegue"
        liberar_reserva(pedido)

    await db.commit()
    return {"afectados": len(vencidos), "detalle": [p.id for p in vencidos]}


scheduler.registrar("expirar_reservas", expirar_reservas, cada_minutos=30)
