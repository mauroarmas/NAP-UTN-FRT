"""API de estado de identidades de consola para administración (feature 022)."""
from app.models.identidad_consola import IdentidadConsola


async def _fila(db, usuario, estado='lista', pools=('catedra-3',), error=None):
    fila = IdentidadConsola(usuario_id=usuario.id, identidad=f'nap-u{usuario.id}@pve', password_cifrada='CIFRADO-SECRETO',
        estado=estado, pools_aplicados=list(pools), ultimo_error_seguro=error)
    db.add(fila)
    await db.commit()
    return fila


async def test_administracion_ve_el_estado_sin_credenciales_ni_identidad_tecnica(client, db, usuario_catedra, auth_admin):
    await _fila(db, usuario_catedra, estado='con_error', error='No se pudo confirmar')
    respuesta = await client.get('/admin/identidades-consola', headers=auth_admin)
    assert respuesta.status_code == 200, respuesta.text
    [fila] = respuesta.json()
    assert fila['usuario_id'] == usuario_catedra.id and fila['estado'] == 'con_error' and fila['pools_aplicados'] == ['catedra-3']
    assert set(fila) == {'usuario_id', 'nombre', 'estado', 'pools_aplicados', 'ultimo_error_seguro', 'reconciliada_at'}
    assert 'CIFRADO-SECRETO' not in respuesta.text and f'nap-u{usuario_catedra.id}@pve' not in respuesta.text


async def test_se_puede_filtrar_por_estado(client, db, usuario_catedra, admin, auth_admin):
    await _fila(db, usuario_catedra, estado='lista')
    await _fila(db, admin, estado='con_error')
    todas = (await client.get('/admin/identidades-consola', headers=auth_admin)).json()
    con_error = (await client.get('/admin/identidades-consola?estado=con_error', headers=auth_admin)).json()
    assert len(todas) == 2 and [f['usuario_id'] for f in con_error] == [admin.id]
    assert (await client.get('/admin/identidades-consola?estado=inventado', headers=auth_admin)).status_code == 422


async def test_solo_administracion_las_ve_o_reintenta(client, db, usuario_catedra, auth_catedra):
    await _fila(db, usuario_catedra)
    assert (await client.get('/admin/identidades-consola', headers=auth_catedra)).status_code == 403
    r = await client.post(f'/admin/identidades-consola/{usuario_catedra.id}/reintentar', headers=auth_catedra | {'Idempotency-Key': 'x'})
    assert r.status_code == 403


async def test_reintentar_marca_a_la_persona_para_la_proxima_pasada(client, db, usuario_catedra, auth_admin):
    fila = await _fila(db, usuario_catedra, estado='con_error', error='No se pudo confirmar')
    fila.reconciliada_at = None
    r = await client.post(f'/admin/identidades-consola/{usuario_catedra.id}/reintentar', headers=auth_admin | {'Idempotency-Key': 'reintento-1'})
    assert r.status_code == 202 and r.json()['estado'] == 'reintento_solicitado'
    await db.refresh(fila)
    assert fila.estado == 'en_preparacion' and fila.reconciliada_at is None


async def test_reintentar_a_quien_no_tiene_identidad_es_404_y_exige_clave_de_idempotencia(client, db, usuario_catedra, auth_admin):
    uid = usuario_catedra.id        # el rollback de la 404 expira los objetos de la sesión compartida
    r = await client.post(f'/admin/identidades-consola/{uid}/reintentar', headers=auth_admin | {'Idempotency-Key': 'k'})
    assert r.status_code == 404
    r = await client.post(f'/admin/identidades-consola/{uid}/reintentar', headers=auth_admin)
    assert r.status_code == 422
