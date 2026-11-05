"""Sesiones de la terminal web (feature 022): cupo por persona, latido, cierre solicitado y auditoría SIN contenido.

El estado vivo de cada terminal está en el proceso que la sirve, pero el cupo, los cierres pedidos desde otros caminos
(retiro, baja, detención, cuenta) y la auditoría viven en la base: así funcionan con más de un proceso y sobreviven a reinicios.
Nada de lo que la persona teclea o ve se guarda jamás.
"""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update

from app.models.evento_seguridad import EventoSeguridad
from app.models.servicio import Servicio
from app.models.sesion_terminal import SesionTerminal
from app.models.usuario import Usuario
from app.utils.clock import clock, db_utc
from app.utils.errors import error

LATIDO_VIGENTE_SEGUNDOS = 60


def _auditar(db, sesion, accion, motivo=None):
    db.add(EventoSeguridad(actor_usuario_id=sesion.usuario_id, accion=accion, resultado='completado',
        referencia=f'servicio:{sesion.servicio_id}', motivo=motivo))


async def _cerrar_fila(db, sesion, motivo):
    ahora = clock.now()
    sesion.cerrada_at, sesion.motivo_cierre = ahora, motivo
    sesion.duracion_s = max(0, int((ahora - db_utc(sesion.abierta_at)).total_seconds()))
    _auditar(db, sesion, 'terminal_cerrada', f'{motivo}; duracion={sesion.duracion_s}s; nodo={sesion.nodo}')


async def abrir(sessions, *, usuario_id, servicio_id, nodo, limite):
    """Reserva un cupo de la persona o falla con `limite_sesiones`. Serializa por persona para que dos aperturas simultáneas no lo superen."""
    async with sessions() as db, db.begin():
        await db.execute(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
        corte = clock.now() - timedelta(seconds=LATIDO_VIGENTE_SEGUNDOS)
        abiertas = (await db.scalars(select(SesionTerminal).where(SesionTerminal.usuario_id == usuario_id,
            SesionTerminal.cerrada_at.is_(None)))).all()
        vigentes = 0
        for sesion in abiertas:
            if db_utc(sesion.ultimo_latido_at) < corte:       # sesión huérfana (proceso caído o navegador ido): libera el cupo
                await _cerrar_fila(db, sesion, 'error')
            else:
                vigentes += 1
        if vigentes >= limite:
            raise error(429, 'limite_sesiones',
                f'Ya tenés {vigentes} terminales abiertas (el máximo es {limite}). Cerrá una para abrir otra.')
        sesion = SesionTerminal(usuario_id=usuario_id, servicio_id=servicio_id, nodo=nodo)
        db.add(sesion)
        await db.flush()
        _auditar(db, sesion, 'terminal_abierta', f'nodo={nodo}')
        return sesion.id


async def latido(sessions, sesion_id, *, ultima_entrada=None):
    async with sessions() as db, db.begin():
        valores = {'ultimo_latido_at': clock.now()}
        if ultima_entrada is not None:
            valores['ultima_entrada_at'] = ultima_entrada
        await db.execute(update(SesionTerminal).where(SesionTerminal.id == sesion_id, SesionTerminal.cerrada_at.is_(None)).values(**valores))


async def consultar(sessions, sesion_id):
    """(cierre_solicitado_at, motivo_solicitud, cerrada) — lo que el relay revisa cada pocos segundos."""
    async with sessions() as db:
        sesion = await db.scalar(select(SesionTerminal).where(SesionTerminal.id == sesion_id).execution_options(populate_existing=True))
        if sesion is None:
            return None, None, True
        return sesion.cierre_solicitado_at, sesion.motivo_solicitud, sesion.cerrada_at is not None


async def cerrar(sessions, sesion_id, motivo):
    """Cierra la fila una sola vez (idempotente) y deja la auditoría; devuelve la duración o None si ya estaba cerrada."""
    async with sessions() as db, db.begin():
        sesion = await db.scalar(select(SesionTerminal).where(SesionTerminal.id == sesion_id).with_for_update())
        if sesion is None or sesion.cerrada_at is not None:
            return None
        await _cerrar_fila(db, sesion, motivo)
        return sesion.duracion_s


async def solicitar_cierre(db, *, motivo, usuario_id=None, servicio_id=None, catedra_ids=None):
    """Pide cerrar las terminales abiertas de una persona, de un servicio o de las cátedras indicadas (ej.: retiro, baja, detención)."""
    consulta = select(SesionTerminal).where(SesionTerminal.cerrada_at.is_(None), SesionTerminal.cierre_solicitado_at.is_(None))
    if usuario_id is not None:
        consulta = consulta.where(SesionTerminal.usuario_id == usuario_id)
    if servicio_id is not None:
        consulta = consulta.where(SesionTerminal.servicio_id == servicio_id)
    if catedra_ids is not None:
        consulta = consulta.where(SesionTerminal.servicio_id.in_(select(Servicio.id).where(Servicio.catedra_id.in_(list(catedra_ids)))))
    sesiones = (await db.scalars(consulta)).all()
    for sesion in sesiones:
        sesion.cierre_solicitado_at, sesion.motivo_solicitud = clock.now(), motivo
    return len(sesiones)


async def cerrar_abiertas_al_arrancar(sessions):
    """Al arrancar el portal no puede haber terminales vivas: las filas abiertas se cierran con su motivo."""
    async with sessions() as db, db.begin():
        abiertas = (await db.scalars(select(SesionTerminal).where(SesionTerminal.cerrada_at.is_(None)))).all()
        for sesion in abiertas:
            await _cerrar_fila(db, sesion, 'reinicio_portal')
        return len(abiertas)


async def abiertas(db):
    """Para administración: sesiones abiertas sin contenido."""
    filas = (await db.scalars(select(SesionTerminal).where(SesionTerminal.cerrada_at.is_(None)).order_by(SesionTerminal.abierta_at))).all()
    return [{'id': str(f.id), 'usuario_id': f.usuario_id, 'servicio_id': f.servicio_id, 'nodo': f.nodo,
             'abierta_at': f.abierta_at, 'ultima_entrada_at': f.ultima_entrada_at} for f in filas]
