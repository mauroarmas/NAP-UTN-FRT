"""Migración conservadora: prueba de datos propios, no adopción por hostname."""
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException

from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.utils.secretos import configured_keyring
from tests import factories
from tests.legacy_helpers import guardar,leer
from tests.capacity_helpers import perfil_capacidad,materializado  # noqa:F401


async def legacy(db,catedra,usuario_catedra,template):
    request=await factories.crear_pedido(db,catedra.id,usuario_catedra.id,template.id,
        estado=EstadoPedido.ERROR)
    await guardar(db,'pedidos',request.id,reserva_vcpus=2,reserva_ram_mb=1024,reserva_disk_gb=40)
    service=await factories.crear_servicio(db,catedra.id,template.id,pedido_id=request.id,disk_gb=40)
    await guardar(db,'servicios',service.id,credenciales_acceso={'usuario':'viejo','password':'private-legacy-password'})
    await db.commit()
    return request,service


async def test_plan_is_read_only_and_contains_no_plaintext(db,catedra,usuario_catedra,template):
    from app.services.backfill_cierre_service import planificar
    request,service=await legacy(db,catedra,usuario_catedra,template)
    report=await planificar(db)
    assert 'private-legacy-password' not in str(report)
    await db.refresh(request);await db.refresh(service)
    assert request.asignacion_snapshot is None
    assert (await leer(db,'servicios',service.id,'credenciales_acceso'))['password']=='private-legacy-password'


async def test_backfill_quarantines_legacy_secrets_and_preserves_unknown_period_and_operation(db,catedra,usuario_catedra,template):
    from app.services.backfill_cierre_service import planificar,aplicar
    from app.models.bitacora_cierre import BitacoraCierre
    request,service=await legacy(db,catedra,usuario_catedra,template)
    plan=await planificar(db)
    result=await aplicar(db,plan,operador='operador-fixture',referencia='copia-009-probada')
    await db.commit();await db.refresh(request);await db.refresh(service)
    assert 'private-legacy-password' not in str(result)
    assert request.asignacion_snapshot['disk_gb']==40
    assert request.asignacion_snapshot['origen']=='legado_cantidades_autorizadas'
    assert request.estado==EstadoPedido.ERROR and service.vence_at is None
    assert service.identidad_infraestructura_id is None
    assert await leer(db,'servicios',service.id,'credenciales_acceso') is None and service.disponibilidad_aplicacion=='no_verificada'
    audit=await db.scalar(select(BitacoraCierre).where(BitacoraCierre.entidad_tipo=='servicio',BitacoraCierre.entidad_id==str(service.id)))
    assert audit and audit.legado_cifrado
    saved=configured_keyring().decrypt(audit.legado_cifrado,context=f'cierre:{audit.id}:legado')
    assert saved['credenciales_acceso']['password']=='private-legacy-password'
    before=await db.scalar(select(func.count()).select_from(BitacoraCierre))
    replay=await aplicar(db,await planificar(db),operador='operador-fixture',referencia='copia-009-probada')
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(BitacoraCierre))==before
    assert replay['requiere_regularizacion'] and replay['pendientes']


async def test_stale_reviewed_plan_rejects_before_any_migration(db,catedra,usuario_catedra,template):
    from app.services.backfill_cierre_service import planificar,aplicar
    request,service=await legacy(db,catedra,usuario_catedra,template)
    plan=await planificar(db)
    service.ram_asignada_mb=2048;await db.commit()
    with pytest.raises(HTTPException) as exc:
        await aplicar(db,plan,operador='operador-fixture',referencia='copia-prueba')
    assert exc.value.status_code==409 and exc.value.detail['codigo']=='plan_desactualizado'
    await db.refresh(service);assert await leer(db,'servicios',service.id,'credenciales_acceso') is not None


async def test_confirmed_legacy_mfa_is_encrypted_without_disabling_the_factor(db,admin):
    from app.services.backfill_cierre_service import planificar,aplicar
    await guardar(db,'usuarios',admin.id,totp_secret='JBSWY3DPEHPK3PXP');admin.totp_habilitado=True
    await db.commit()
    await aplicar(db,await planificar(db),operador='operador-fixture',referencia='copia-prueba')
    await db.commit();await db.refresh(admin)
    assert await leer(db,'usuarios',admin.id,'totp_secret') is None and admin.totp_habilitado
    assert configured_keyring().decrypt(admin.totp_secret_encrypted,context=f'totp:{admin.id}')=='JBSWY3DPEHPK3PXP'


async def test_owned_resource_gets_one_conservative_ledger_without_fabricating_definition_hashes(
    db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,
):
    from app.services.backfill_cierre_service import planificar,aplicar
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    service,ledger=await materializado(db,proxmox,catedra,usuario_catedra,template)
    await db.delete(ledger);await db.commit()  # Copia incompleta de ledger, sólo fixture.
    plan=await planificar(db,sondear=True,pve=proxmox)
    await aplicar(db,plan,operador='operador-fixture',referencia='inventario-prueba',pve=proxmox)
    await db.commit()
    ledger=await db.scalar(select(CompromisoCapacidad))
    assert ledger.estado=='incierto' and ledger.vcpus_retenidos>=2 and ledger.disk_bytes_retenidos>=10*1024**3
    identity=await db.get(IdentidadInfraestructura,service.identidad_infraestructura_id)
    assert identity.definition_sha256 is None and identity.bundle_sha256 is None


async def test_backfill_requires_accountable_operator_and_reference(db):
    from app.services.backfill_cierre_service import planificar,aplicar
    with pytest.raises(ValueError): await aplicar(db,await planificar(db),operador='',referencia='')


async def test_changed_marker_invalidates_a_reviewed_ledger_plan(db,proxmox,perfil_capacidad,catedra,usuario_catedra,template):
    from app.services.backfill_cierre_service import planificar,aplicar
    from app.models.compromiso_capacidad import CompromisoCapacidad
    service,ledger=await materializado(db,proxmox,catedra,usuario_catedra,template)
    await db.delete(ledger);await db.commit()
    plan=await planificar(db,sondear=True,pve=proxmox)
    proxmox.configuraciones[('pve1',100)]['description']='marca-ajena'
    with pytest.raises(HTTPException) as exc:
        await aplicar(db,plan,operador='operador-fixture',referencia='inventario-prueba',pve=proxmox)
    assert exc.value.detail['codigo']=='plan_desactualizado'
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==0


async def test_invalid_factor_stays_enabled_and_requires_assistance(db,admin):
    from app.services.backfill_cierre_service import planificar,aplicar
    await guardar(db,'usuarios',admin.id,totp_secret='INVALID-private-value');admin.totp_habilitado=True
    await db.commit()
    report=await aplicar(db,await planificar(db),operador='operador-fixture',referencia='copia-prueba')
    await db.commit();await db.refresh(admin)
    assert admin.totp_habilitado and admin.habilitacion_inconsistente and admin.totp_secret_encrypted is None
    assert 'INVALID-private-value' not in str(report)


async def test_only_frozen_audited_approval_can_rebuild_a_missing_period(
    db,client,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    from app.services.backfill_cierre_service import planificar,aplicar
    from app.models.vigencia import VigenciaAutorizada
    from tests.test_liberacion_009 import approved
    request=await approved(client,db,catedra,usuario_catedra,template,auth_admin)
    period=await db.scalar(select(VigenciaAutorizada))
    expected=(period.desde_local,period.hasta_local,period.inicio_at,period.fin_exclusivo_at)
    await db.delete(period);await db.commit()  # Copia incompleta para ensayo.
    await aplicar(db,await planificar(db),operador='operador-fixture',referencia='copia-incompleta')
    await db.commit()
    recovered=await db.scalar(select(VigenciaAutorizada))
    assert recovered and recovered.pedido_id==request.id
    from app.utils.clock import db_utc
    assert (recovered.desde_local,recovered.hasta_local,db_utc(recovered.inicio_at),db_utc(recovered.fin_exclusivo_at)) == (
        expected[0],expected[1],db_utc(expected[2]),db_utc(expected[3]))
    assert recovered.origen=='backfill_auditado'
