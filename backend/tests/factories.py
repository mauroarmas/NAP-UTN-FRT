"""Helpers para dar de alta datos en la base de pruebas."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.pedido import Pedido, EstadoPedido, ModeloServicio, VigenciaTipo
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario, RolUsuario
from app.utils.security import get_password_hash


async def crear_catedra(
    db: AsyncSession,
    nombre: str = "Cátedra de Prueba",
    titular_id: int | None = None,
) -> Catedra:
    catedra = Catedra(nombre=nombre, titular_id=titular_id)
    db.add(catedra)
    await db.commit()
    await db.refresh(catedra)
    return catedra


async def crear_usuario(
    db: AsyncSession,
    username: str,
    rol: RolUsuario = RolUsuario.CATEDRA_ADMIN,
    password: str = "secreto123",
) -> Usuario:
    usuario = Usuario(
        username=username,
        email=f"{username}@test.local",
        nombre=username.title(),
        password_hash=get_password_hash(password),
        rol=rol,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


async def crear_template(
    db: AsyncSession,
    nombre: str = "LXC Pequeño",
    vcpus: int = 1,
    ram_mb: int = 512,
    disk_gb: int = 4,
    tipo: TipoRecurso = TipoRecurso.LXC,
    modelo_servicio: ModeloServicio = ModeloServicio.IAAS,
    justificacion_disco: str | None = None,
) -> RecursoTemplate:
    template = RecursoTemplate(
        nombre=nombre,
        tipo=tipo,
        modelo_servicio=modelo_servicio,
        default_vcpus=vcpus,
        default_ram_mb=ram_mb,
        default_disk_gb=disk_gb,
        justificacion_disco=justificacion_disco,
        os_template="local:vztmpl/debian-12-standard.tar.zst",
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def crear_pedido(
    db: AsyncSession,
    catedra_id: int,
    solicitante_id: int,
    template_id: int | None = None,
    estado: EstadoPedido = EstadoPedido.APROBADO,
    vmid_reservado: str | None = None,
    modelo_servicio: ModeloServicio = ModeloServicio.IAAS,
    descripcion_requerimientos: str | None = None,
    vigencia_tipo: VigenciaTipo | None = None,
    vigencia_desde: datetime | None = None,
    vigencia_hasta: datetime | None = None,
    opciones_avanzadas: dict | None = None,
) -> Pedido:
    pedido = Pedido(
        catedra_id=catedra_id,
        solicitante_id=solicitante_id,
        template_id=template_id,
        estado=estado,
        vmid_reservado=vmid_reservado,
        modelo_servicio=modelo_servicio,
        descripcion_requerimientos=descripcion_requerimientos,
        vigencia_tipo=vigencia_tipo,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        opciones_avanzadas=opciones_avanzadas,
    )
    db.add(pedido)
    await db.commit()
    await db.refresh(pedido)
    return pedido


async def crear_servicio(
    db: AsyncSession,
    catedra_id: int,
    template_id: int,
    pedido_id: int | None = None,
    proxmox_vmid: str | None = "100",
    proxmox_node: str | None = "pve1",
    estado: EstadoServicio = EstadoServicio.RUNNING,
    vcpus: int = 1,
    ram_mb: int = 512,
    disk_gb: int = 4,
) -> Servicio:
    servicio = Servicio(
        catedra_id=catedra_id,
        pedido_id=pedido_id,
        template_id=template_id,
        proxmox_vmid=proxmox_vmid,
        proxmox_node=proxmox_node,
        estado=estado,
        hostname=f"cat{catedra_id}-svc{pedido_id}",
        vcpus_asignados=vcpus,
        ram_asignada_mb=ram_mb,
        disk_asignado_gb=disk_gb,
        deployed_at=datetime.utcnow(),
    )
    db.add(servicio)
    await db.commit()
    await db.refresh(servicio)
    return servicio
