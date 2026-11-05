"""Listado de pedidos paginado: orden, cursor sin repetidos ni saltos, filtros, búsqueda en el servidor y alcance."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.models.pedido import EstadoPedido, Pedido
from tests import factories


async def crear(db, catedra, usuario, template, n, **kw):
    """`n` pedidos con `created_at` distintos y crecientes (el último creado es el más reciente)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = []
    for i in range(n):
        p = await factories.crear_pedido(db, catedra_id=catedra.id, solicitante_id=usuario.id, template_id=template.id, **kw)
        await db.execute(update(Pedido).where(Pedido.id == p.id).values(created_at=base + timedelta(minutes=i)))
        ids.append(p.id)
    await db.commit()
    return ids


async def recorrer(client, headers, **params):
    """Sigue los cursores hasta el final y devuelve las páginas."""
    paginas, cursor = [], None
    while True:
        r = await client.get('/pedidos/', headers=headers, params={**params, **({'cursor': cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        paginas.append(r.json())
        cursor = r.json()['next_cursor']
        if not cursor:
            return paginas


async def test_pagina_por_defecto_y_forma_de_la_respuesta(client, db, catedra, usuario_catedra, template, auth_admin):
    await crear(db, catedra, usuario_catedra, template, 25)
    r = await client.get('/pedidos/', headers=auth_admin)
    cuerpo = r.json()
    assert set(cuerpo) == {'items', 'next_cursor'}
    assert len(cuerpo['items']) == 20 and cuerpo['next_cursor']


async def test_el_cursor_recorre_todo_sin_repetir_ni_saltar_y_del_mas_reciente(client, db, catedra, usuario_catedra, template, auth_admin):
    ids = await crear(db, catedra, usuario_catedra, template, 23)
    paginas = await recorrer(client, auth_admin, limit=10)
    vistos = [p['id'] for pg in paginas for p in pg['items']]
    assert [len(pg['items']) for pg in paginas] == [10, 10, 3]
    assert vistos == list(reversed(ids))
    assert paginas[-1]['next_cursor'] is None


async def test_si_justo_cabe_en_una_pagina_no_hay_cursor(client, db, catedra, usuario_catedra, template, auth_admin):
    await crear(db, catedra, usuario_catedra, template, 5)
    r = await client.get('/pedidos/', headers=auth_admin, params={'limit': 5})
    assert len(r.json()['items']) == 5 and r.json()['next_cursor'] is None


async def test_empates_de_fecha_se_desempatan_por_id(client, db, catedra, usuario_catedra, template, auth_admin):
    ids = await crear(db, catedra, usuario_catedra, template, 6)
    await db.execute(update(Pedido).where(Pedido.id.in_(ids)).values(created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)))
    await db.commit()
    vistos = [p['id'] for pg in await recorrer(client, auth_admin, limit=2) for p in pg['items']]
    assert vistos == sorted(ids, reverse=True)


async def test_limite_y_cursor_invalidos(client, auth_admin):
    for limite in (0, 101):
        assert (await client.get('/pedidos/', headers=auth_admin, params={'limit': limite})).status_code == 422
    r = await client.get('/pedidos/', headers=auth_admin, params={'cursor': 'no-es-un-cursor'})
    assert r.status_code == 422 and r.json()['detail']['codigo'] == 'cursor_invalido'


async def test_el_filtro_de_estado_se_aplica_antes_de_paginar(client, db, catedra, usuario_catedra, template, auth_admin):
    await crear(db, catedra, usuario_catedra, template, 7, estado=EstadoPedido.APROBADO)
    await crear(db, catedra, usuario_catedra, template, 4, estado=EstadoPedido.RECHAZADO)
    paginas = await recorrer(client, auth_admin, estado='rechazado', limit=3)
    assert sum(len(pg['items']) for pg in paginas) == 4
    assert all(p['estado'] == 'rechazado' for pg in paginas for p in pg['items'])


async def test_la_busqueda_filtra_en_el_servidor_antes_de_paginar(client, db, catedra, usuario_catedra, template, auth_admin):
    ids = await crear(db, catedra, usuario_catedra, template, 12)
    await crear(db, catedra, usuario_catedra, template, 3, descripcion_requerimientos='Laboratorio de Redes')
    buscados = await recorrer(client, auth_admin, q='redes', limit=2)
    assert sum(len(pg['items']) for pg in buscados) == 3
    # por número (con o sin «#»), por servicio y por cátedra
    for q in (f'#{ids[0]}', str(ids[0])):
        r = await client.get('/pedidos/', headers=auth_admin, params={'q': q})
        assert ids[0] in [p['id'] for p in r.json()['items']]
    for q in (template.nombre, catedra.nombre):
        assert len(await recorrer(client, auth_admin, q=q.lower(), limit=100)) >= 1
        r = await client.get('/pedidos/', headers=auth_admin, params={'q': q.upper(), 'limit': 100})
        assert len(r.json()['items']) == 15
    r = await client.get('/pedidos/', headers=auth_admin, params={'q': 'no-existe-nada'})
    assert r.json() == {'items': [], 'next_cursor': None}


async def test_la_busqueda_encuentra_por_la_etiqueta_visible_del_estado_y_no_trata_comodines(client, db, catedra, usuario_catedra, template, auth_admin):
    await crear(db, catedra, usuario_catedra, template, 2, estado=EstadoPedido.REQUIERE_AJUSTE)
    await crear(db, catedra, usuario_catedra, template, 3, estado=EstadoPedido.APROBADO)
    r = await client.get('/pedidos/', headers=auth_admin, params={'q': 'aclaración'})
    assert [p['estado'] for p in r.json()['items']] == ['requiere_ajuste'] * 2
    for comodin in ('%', '_'):
        r = await client.get('/pedidos/', headers=auth_admin, params={'q': comodin})
        assert r.json()['items'] == []


async def test_la_catedra_solo_pagina_y_busca_lo_suyo(client, db, catedra, usuario_catedra, template, auth_catedra):
    propios = await crear(db, catedra, usuario_catedra, template, 4)
    ajena = await factories.crear_catedra(db, nombre='Cátedra Ajena Paginación')
    otro = await factories.crear_usuario(db, 'ajeno-paginacion')
    await crear(db, ajena, otro, template, 6)
    vistos = {p['id'] for pg in await recorrer(client, auth_catedra, limit=3) for p in pg['items']}
    assert vistos == set(propios)
    r = await client.get('/pedidos/', headers=auth_catedra, params={'q': 'ajena'})
    assert r.json()['items'] == []
