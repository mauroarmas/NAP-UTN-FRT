"""Helpers para dar de alta datos en la base de pruebas."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.pedido import Pedido, EstadoPedido
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario, RolUsuario
from app.utils.security import get_password_hash


async def crear_catedra(
    db: AsyncSession,
    nombre: str = "Cátedra de Prueba",
    cuota_vcpus: int = 4,
    cuota_ram_mb: int = 4096,
    cuota_storage_gb: int = 16,
) -> Catedra:
    catedra = Catedra(
        nombre=nombre,
        cuota_vcpus=cuota_vcpus,
        cuota_ram_mb=cuota_ram_mb,
        cuota_storage_gb=cuota_storage_gb,
    )
    db.add(catedra)
    await db.commit()
    await db.refresh(catedra)
    return catedra


async def crear_usuario(
    db: AsyncSession,
    username: str,
    rol: RolUsuario = RolUsuario.CATEDRA_ADMIN,
    catedra_id: int | None = None,
    password: str = "secreto123",
) -> Usuario:
    usuario = Usuario(
        username=username,
        email=f"{username}@test.local",
        nombre=username.title(),
        password_hash=get_password_hash(password),
        rol=rol,
        catedra_id=catedra_id,
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
) -> RecursoTemplate:
    template = RecursoTemplate(
        nombre=nombre,
        tipo=tipo,
        default_vcpus=vcpus,
        default_ram_mb=ram_mb,
        default_disk_gb=disk_gb,
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
    template_id: int,
    estado: EstadoPedido = EstadoPedido.APROBADO,
    vmid_reservado: str | None = None,
) -> Pedido:
    pedido = Pedido(
        catedra_id=catedra_id,
        solicitante_id=solicitante_id,
        template_id=template_id,
        estado=estado,
        vmid_reservado=vmid_reservado,
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
