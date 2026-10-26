from uuid import uuid4
from copy import deepcopy

from fastapi import HTTPException
import pytest
from sqlalchemy import select, func

from app.models.secreto_despliegue import SecretoDespliegue
from app.models.pedido import TipoPedido
from app.services.secreto_despliegue_service import asegurar, revelar_acceso, para_dispatch, huella_entrada
from app.utils.secretos import configured_keyring, SecretError
from tests import factories
from tests.test_modelos_despliegue_011 import make_configuration


@pytest.fixture
async def pedido_app(db, admin, usuario_catedra, catedra, template, documento_docker):
    config = await make_configuration(db, admin, documento_docker)
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id)
    pedido.configuracion_despliegue_id = config.id
    await db.commit()
    return pedido


async def test_retries_keep_references_and_other_order_gets_new_secret(db, admin, pedido_app):
    refs = await asegurar(db, pedido_app.id, usuario=admin)
    await db.commit()
    assert refs == await asegurar(db, pedido_app.id, usuario=admin)
    pedido_app.vmid_reservado = '502'
    await db.commit()
    assert refs == await asegurar(db, pedido_app.id, usuario=admin)
    assert set(refs[0]) == {'id', 'nombre', 'revision'}
    first = await db.scalar(select(SecretoDespliegue))
    other = await factories.crear_pedido(db, pedido_app.catedra_id, pedido_app.solicitante_id, pedido_app.template_id)
    other.configuracion_despliegue_id = pedido_app.configuracion_despliegue_id
    otherrefs = await asegurar(db, other.id, usuario=admin)
    assert refs != otherrefs
    second = await db.scalar(select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == other.id))
    keyring = configured_keyring()
    value = keyring.decrypt(first.valor_cifrado, context=f'deployment:{first.pedido_id}:{first.nombre}:1')
    assert len(value) >= 32
    assert keyring.decrypt(second.valor_cifrado, context=f'deployment:{second.pedido_id}:{second.nombre}:1') != value
    assert value not in str(refs) and value not in str(pedido_app.asignacion_snapshot)
    with pytest.raises(SecretError):
        keyring.decrypt(first.valor_cifrado, context=f'deployment:{second.pedido_id}:{first.nombre}:1')


async def test_supplied_input_is_encrypted_write_only_and_replay_does_not_replace(db, admin, usuario_catedra, catedra, template, documento_docker):
    documento_docker['secretos'][0]['modo'] = 'por_pedido'
    config = await make_configuration(db, admin, documento_docker)
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id)
    pedido.configuracion_despliegue_id = config.id
    private = 'fixture-sensitive-input'
    with pytest.raises(HTTPException): await asegurar(db, pedido.id, usuario=admin)
    refs = await asegurar(db, pedido.id, usuario=admin, aportados={'APP_PASSWORD': private})
    await db.commit()
    assert await asegurar(db, pedido.id, usuario=admin) == refs
    assert await asegurar(db, pedido.id, usuario=admin, aportados={'APP_PASSWORD': private}) == refs
    with pytest.raises(HTTPException) as caught:
        await asegurar(db, pedido.id, usuario=admin, aportados={'APP_PASSWORD': 'different-fixture-sensitive'})
    assert private not in str(caught.value.detail) and 'different-fixture-sensitive' not in str(caught.value.detail)
    assert private not in (await db.scalar(select(SecretoDespliegue))).valor_cifrado
    assert await db.scalar(select(func.count()).select_from(SecretoDespliegue)) == 1


async def test_unauthorized_reader_denied_before_decryption_and_membership_is_current(db, admin, usuario_catedra, catedra, template, pedido_app, monkeypatch):
    await asegurar(db, pedido_app.id, usuario=admin); await db.commit()
    service = await factories.crear_servicio(db, catedra.id, template.id, pedido_app.id)
    service.configuracion_despliegue_id = pedido_app.configuracion_despliegue_id
    service.disponibilidad_aplicacion = 'utilizable'; await db.commit()
    values = await revelar_acceso(db, service.id, usuario=usuario_catedra)
    assert len(values['APP_PASSWORD']) >= 32
    stranger = await factories.crear_usuario(db, 'stranger-011')
    def must_not_decrypt(*args, **kwargs): raise AssertionError('descifrado antes de autorizar')
    monkeypatch.setattr('app.services.secreto_despliegue_service.configured_keyring', must_not_decrypt)
    with pytest.raises(HTTPException) as caught: await revelar_acceso(db, service.id, usuario=stranger)
    assert caught.value.status_code == 403
    catedra.titular_id = stranger.id; await db.commit()
    with pytest.raises(HTTPException): await revelar_acceso(db, service.id, usuario=usuario_catedra)


async def test_renewal_keeps_original_references_and_does_not_insert_new_rows(db, admin, usuario_catedra, catedra, template, pedido_app):
    refs = await asegurar(db, pedido_app.id, usuario=admin); await db.commit()
    service = await factories.crear_servicio(db, catedra.id, template.id, pedido_app.id)
    service.configuracion_despliegue_id = pedido_app.configuracion_despliegue_id
    renewal = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id)
    renewal.tipo = TipoPedido.RENOVACION; renewal.servicio_id = service.id
    await db.commit()
    assert await asegurar(db, renewal.id, usuario=admin) == refs
    assert await db.scalar(select(func.count()).select_from(SecretoDespliegue)) == 1


async def test_creation_requires_current_admin_and_dispatch_requires_current_lease(db, admin, usuario_catedra, pedido_app, monkeypatch):
    from app.models.operacion_infraestructura import OperacionInfraestructura
    from app.services.operacion_service import reclamar, LeaseOperacion
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    with pytest.raises(HTTPException): await asegurar(db, pedido_app.id, usuario=usuario_catedra)
    refs = await asegurar(db, pedido_app.id, usuario=admin)
    config = await db.get(ConfiguracionDespliegue, pedido_app.configuracion_despliegue_id)
    pedido_app.asignacion_snapshot = {'secretos': refs, 'configuracion_sha256': config.sha256}
    op = OperacionInfraestructura(tipo='desplegar', pedido_id=pedido_app.id,
        actor_tipo='sistema', actor_id_normalizado='fixture', idempotency_key='secret-worker', request_hash='a'*64,
        contexto_seguro={'configuracion_sha256': config.sha256})
    db.add(op); await db.commit()
    lease = await reclamar(db, owner=uuid4()); await db.commit()
    values = await para_dispatch(db, lease)
    assert len(values['APP_PASSWORD']) >= 32
    assert values['APP_PASSWORD'] not in str(op.contexto_seguro)
    with pytest.raises(HTTPException):
        await para_dispatch(db, LeaseOperacion(lease.id, uuid4(), lease.generation))


def test_contextual_hmac_is_stable_but_not_reusable_for_another_order():
    value = {'APP_PASSWORD': 'fixture-sensitive-input'}
    first = huella_entrada(71, value)
    assert first == huella_entrada(71, deepcopy(value))
    assert first != huella_entrada(72, value) and value['APP_PASSWORD'] not in first
    ring = configured_keyring()
    assert ring.fingerprint(value, context='deployment-input:71', key_id=ring.active) == first


def test_hmac_replay_can_verify_previous_key_after_rotation():
    from cryptography.fernet import Fernet
    from app.utils.secretos import Keyring
    keys = {'old': Fernet.generate_key().decode(), 'new': Fernet.generate_key().decode()}
    before = Keyring(keys, active='old').fingerprint({'value': 'fixture'}, context='deployment-input:71')
    after = Keyring(keys, active='new')
    assert after.fingerprint({'value': 'fixture'}, context='deployment-input:71', key_id='old') == before
    assert after.fingerprint({'value': 'fixture'}, context='deployment-input:71') != before
