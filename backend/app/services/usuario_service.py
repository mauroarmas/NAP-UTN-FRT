"""Serialización de usuarios con sus cátedras a cargo.

Vive acá y no en un router porque lo necesitan dos: `/auth/me` y `/usuarios/*`.

El detalle que importa: la relación `Usuario.catedras` es de carga diferida, y
en SQLAlchemy async una carga diferida durante la serialización revienta con
`MissingGreenlet` — el error no aparece al construir el objeto sino al momento
en que FastAPI lee el atributo, así que es fácil que pase inadvertido hasta que
alguien intenta usar el endpoint. Por eso las cátedras se consultan
explícitamente en lugar de dejar que el ORM las resuelva solo.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.pedido import Pedido
from app.models.usuario import Usuario, RolUsuario
from app.schemas.usuario import UsuarioResponse


async def catedras_de(db: AsyncSession, usuario_id: int) -> list[Catedra]:
    """Cátedras de las que la persona es titular, por nombre.

    **No filtra por `activa`, y es deliberado.** Dar una cátedra de baja no
    detiene sus servicios: pueden seguir corriendo y consumiendo recursos
    reales, así que siguen necesitando un responsable a quien preguntarle. Si
    esta consulta ignorara las cátedras inactivas, se podría dar de baja al
    titular de una cátedra con contenedores encendidos y nadie a cargo.

    Es la razón por la que el mensaje de bloqueo dice "reasignalas" y no
    "dalas de baja": lo segundo no destraba nada (FR-017).
    """
    result = await db.execute(
        select(Catedra).where(Catedra.titular_id == usuario_id).order_by(Catedra.nombre)
    )
    return list(result.scalars().all())


async def con_catedras(db: AsyncSession, usuario: Usuario) -> UsuarioResponse:
    """Respuesta de usuario con sus cátedras anidadas.

    Van siempre: sin ellas no se puede saber, mirando un listado, de qué
    responde cada persona.
    """
    catedras = await catedras_de(db, usuario.id)
    return UsuarioResponse(
        id=usuario.id,
        username=usuario.username,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol.value,
        activo=usuario.activo,
        created_at=usuario.created_at,
        totp_habilitado=usuario.totp_habilitado,
        catedras=[{"id": c.id, "nombre": c.nombre} for c in catedras],
    )


async def tiene_historial(db: AsyncSession, usuario_id: int) -> bool:
    """¿Esta persona dejó rastro que haya que conservar?

    Un pedido creado o una cátedra a cargo alcanzan. Es lo que decide si
    retirarla es una baja lógica o un borrado real: donde no hay historia que
    preservar, borrar de verdad evita acumular cuentas mal tipeadas.
    """
    pedidos = await db.execute(
        select(func.count()).select_from(Pedido).where(Pedido.solicitante_id == usuario_id)
    )
    if pedidos.scalar_one():
        return True
    return bool(await catedras_de(db, usuario_id))


async def es_ultimo_admin_activo(db: AsyncSession, usuario_id: int) -> bool:
    """¿Sacar a esta persona dejaría al sistema sin ningún administrador?

    Se cuenta sobre administradores **activos**, no sobre filas: una cuenta dada
    de baja no puede administrar nada, así que no salva al sistema.

    Nota honesta sobre su alcance: por los endpoints actuales esta condición no
    llega a cumplirse nunca. Quien llama tiene que ser administrador activo, y el
    chequeo de "no podés darte de baja a vos mismo" corre antes, así que siempre
    queda otro administrador activo. Se conserva como defensa en profundidad —
    para cualquier camino futuro que retire cuentas sin pasar por ahí (un script,
    una baja masiva, un cambio de rol)—, no como una validación que hoy se
    ejercite en producción.
    """
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None or usuario.rol != RolUsuario.ADMIN or not usuario.activo:
        return False

    otros = await db.execute(
        select(func.count())
        .select_from(Usuario)
        .where(
            Usuario.rol == RolUsuario.ADMIN,
            Usuario.activo.is_(True),
            Usuario.id != usuario_id,
        )
    )
    return otros.scalar_one() == 0
