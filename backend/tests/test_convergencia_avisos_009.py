from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from app.models.vigencia import VigenciaAutorizada
from app.models.notificacion import Notificacion
from app.services.vencimiento_service import aplicar_vencimientos
from app.services.vigencia_service import resolver_fechas
from app.utils.clock import clock
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


async def test_vencimiento_crea_avisos_y_correo_una_vez(db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, admin):
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    period = await db.scalar(select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == service.id))
    today = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    dates = resolver_fechas(today, today+timedelta(days=2), 'America/Argentina/Tucuman')
    period.inicio_at, period.fin_exclusivo_at = dates.inicio_at, dates.fin_exclusivo_at
    period.desde_local, period.hasta_local = dates.desde, dates.hasta
    await db.commit()
    for _ in range(2):
        await aplicar_vencimientos(db)
    rows = list((await db.scalars(select(Notificacion))).all())
    assert {(row.destinatario_usuario_id, row.canal) for row in rows} == {
        (usuario_catedra.id, 'portal'), (usuario_catedra.id, 'email'), (admin.id, 'portal'), (admin.id, 'email')}
    assert len(rows) == 4
    assert all(row.payload['tipo'] == 'vencimiento_proximo' and dates.hasta.isoformat() in row.payload['texto'] for row in rows)
