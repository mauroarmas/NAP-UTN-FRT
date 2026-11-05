from sqlalchemy import text

from tests.test_configuracion_operativa_009 import validated_offer  # noqa:F401


async def test_published_offer_is_validated_inside_a_postgresql_read_only_transaction(db,validated_offer):
    from app.services.preflight_service import inspeccionar_ofertas,inspeccionar_claves,inspeccionar_datos
    await db.execute(text('SET TRANSACTION READ ONLY'))
    assert (await inspeccionar_ofertas(db))['apto']
    assert (await inspeccionar_claves(db))['apto']
    report=await inspeccionar_datos(db)
    assert report['cantidades']['usuarios']>=1
    assert (await db.scalar(text('SHOW transaction_read_only')))=='on'
