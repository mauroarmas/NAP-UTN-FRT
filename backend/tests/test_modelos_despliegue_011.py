"""Integridad local de los modelos; concurrencia se prueba en PostgreSQL."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.schemas.configuracion_despliegue import validar_documento, digest_configuracion
from app.models.cierre_base import utc_now


async def make_configuration(db, actor, document, **kwargs):
    document = validar_documento(document)
    fields = dict(codigo='campus-demo', revision=1,
        origen=document['origen'], modelo_servicio=document['modelo_servicio'], documento=document,
        sha256=digest_configuracion(document), perfil_id=document['perfil']['id'],
        perfil_revision=document['perfil']['revision'], perfil_sha256=document['perfil']['sha256'],
        validaciones={'referencia': True, 'estructura': True, 'instalacion': False}, creado_por=actor.id)
    fields.update(kwargs)
    row = ConfiguracionDespliegue(**fields)
    db.add(row); await db.flush()
    return row


async def test_validated_revision_can_only_retire(db, admin, documento_docker):
    row = await make_configuration(db, admin, documento_docker)
    await db.commit()
    for field, changed in [('documento', {**row.documento, 'variables': {'OTHER': 'value'}}),
                           ('sha256', '0'*64), ('revision', 2), ('validaciones', {'instalacion': True})]:
        original = deepcopy(getattr(row, field))
        with pytest.raises(ValueError, match='inmutable'):
            async with db.begin_nested():
                setattr(row, field, changed)
                await db.flush()
        # A failed flush invalidates the savepoint; reload the persistent row.
        await db.refresh(row)
        assert getattr(row, field) == original
    row.estado = 'retirada'; row.retirada_at = utc_now(); await db.flush(); await db.commit()
    with pytest.raises(ValueError):
        async with db.begin_nested():
            row.estado = 'validada'; await db.flush()
    await db.refresh(row)
    with pytest.raises(ValueError):
        async with db.begin_nested():
            await db.delete(row); await db.flush()


async def test_configuration_hash_profile_and_document_must_agree(db, admin, documento_docker):
    # A canonical document cannot be inserted with a hash from another decision.
    with pytest.raises(ValueError):
        async with db.begin_nested():
            await make_configuration(db, admin, documento_docker, perfil_revision=2)


async def test_unique_family_revision(db, admin, documento_docker):
    await make_configuration(db, admin, documento_docker); await db.commit()
    with pytest.raises(IntegrityError):
        async with db.begin_nested(): await make_configuration(db, admin, documento_docker)


async def test_template_allows_historical_iaas_and_rejects_both_origins(db, admin, documento_docker):
    from app.models.recurso_template import RecursoTemplate
    from app.models.definicion_servicio import DefinicionServicio
    row = await make_configuration(db, admin, documento_docker)
    legacy = DefinicionServicio(codigo='legacy', version='1.0.0', modelo_servicio='iaas', producto='linux')
    db.add(legacy); await db.flush()
    template = RecursoTemplate(nombre='Ubuntu histórico')
    db.add(template); await db.flush()
    assert template.configuracion_despliegue_id is None and template.definicion_version_id is None
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(RecursoTemplate(nombre='Mezclado', configuracion_despliegue_id=row.id, definicion_version_id=legacy.id))
            await db.flush()


def test_console_constraints_cover_producer_and_attempt_identity():
    from app.models.consola_operacion import ConsolaOperacion, ConsolaFragmento
    from app.models.intento_despliegue import IntentoDespliegue
    from app.models.reserva_red_aplicacion import ReservaRedAplicacion
    assert ConsolaOperacion.__table__.c.operacion_raiz_id.primary_key
    constraints = {c.name for c in ConsolaFragmento.__table__.constraints}
    assert {'uq_consola_evento_productor', 'ck_consola_productor', 'fk_consola_intento_identidad'} <= constraints
    assert any(i.name == 'uq_red_direccion_activa' and i.unique for i in ReservaRedAplicacion.__table__.indexes)
    assert any(c.name == 'uq_intento_raiz_numero' for c in IntentoDespliegue.__table__.constraints)
