"""Pruebas de despliegue programado (US3 - T067):
Reloj controlado, inicio inclusivo local, tick duplicado,
revisión reemplazada, baja/revocación, perfil bloqueado,
gracia desde max(aprobación, inicio) y autor sistema sin CT anticipado.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func

from app.models.pedido import Pedido, EstadoPedido
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.schemas.asignacion import AprobacionEfectiva
from app.services import admision_service, evaluacion_service, capacidad_service
from app.services.despliegue_programado_service import procesar_agenda
from app.utils.clock import clock, db_utc
from tests.test_admision_aplicaciones_011 import app_order
from tests.capacity_helpers import perfil_capacidad, seleccion
from tests.test_reserva_red_aplicacion_011 import red_aplicaciones_011
from infra.applications.tests.conftest import profile_entry


@pytest.fixture
def future_dates():
    return {
        "tipo": "personalizado",
        "desde": "2027-03-01",
        "hasta": "2027-06-30",
    }


async def test_inicio_inclusivo_local_despacha_orden_con_autor_sistema_sin_ct_anticipado(
    db, admin, app_order, proxmox, future_dates, monkeypatch
):
    app = app_order
    # Configurar fechas futuras
    app.body["vigencia"] = future_dates
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )

    # 1. Aprobar con despliegue programado para el inicio
    payload = {
        **app.body,
        "capacidad_token": evaluation["capacidad_token"],
        "solicitar_despliegue": "programado",
    }
    result = await admision_service.aprobar(
        db, app.pedido.id, actor=admin, payload=payload, clave="future-app-1"
    )
    await db.commit()
    assert result.status_code == 200
    assert result.resultado["disponibilidad"] == "programado_al_inicio"

    pedido = await db.get(Pedido, app.pedido.id)
    assert pedido.despliegue_programado_at is not None
    assert pedido.despliegue_revision_programada == pedido.revision_decision
    # Sin contenedores anticipados
    assert len(proxmox.creados) == 0
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura)) == 0

    # 2. Tick antes de la fecha inicial: no despacha
    res_tick_antes = await procesar_agenda(db)
    assert res_tick_antes["afectados"] == 0
    assert len(proxmox.creados) == 0

    # 3. Avanzar reloj controlado a la fecha inicial
    target_time = db_utc(pedido.despliegue_programado_at) + timedelta(minutes=5)
    monkeypatch.setattr(clock, "now", lambda: target_time)

    # 4. Tick alcanzado: despacha con autor sistema
    res_tick = await procesar_agenda(db)
    assert res_tick["afectados"] == 1
    assert pedido.id in res_tick["detalle"]

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.EN_DESPLIEGUE
    assert pedido.despliegue_programado_at is None

    operation = await db.scalar(
        select(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id == pedido.id)
    )
    assert operation is not None
    assert operation.actor_tipo == "sistema"
    assert operation.actor_id_normalizado == "despliegue_programado"
    assert operation.contexto_seguro["origen"] == "despliegue_programado"

    # 5. Tick duplicado es idempotente
    res_dup = await procesar_agenda(db)
    assert res_dup["afectados"] == 0


async def test_revision_reemplazada_invalida_agenda_anterior(
    db, admin, app_order, future_dates, monkeypatch
):
    app = app_order
    app.body["vigencia"] = future_dates
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )
    payload = {
        **app.body,
        "capacidad_token": evaluation["capacidad_token"],
        "solicitar_despliegue": "programado",
    }
    await admision_service.aprobar(
        db, app.pedido.id, actor=admin, payload=payload, clave="rev-replace-1"
    )
    await db.commit()

    pedido = await db.get(Pedido, app.pedido.id)
    target_time = db_utc(pedido.despliegue_programado_at) + timedelta(minutes=5)

    # Simulamos que la revisión fue incrementada por una nueva decisión administrativa
    pedido.revision_decision += 1
    await db.commit()

    monkeypatch.setattr(clock, "now", lambda: target_time)
    res = await procesar_agenda(db)
    assert res["afectados"] == 0
    assert any(item["motivo"] == "revision_obsoleta" for item in res["omitidos"])
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura)) == 0


async def test_baja_o_rechazo_cancela_agenda(
    db, admin, app_order, future_dates, monkeypatch
):
    app = app_order
    app.body["vigencia"] = future_dates
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )
    payload = {
        **app.body,
        "capacidad_token": evaluation["capacidad_token"],
        "solicitar_despliegue": "programado",
    }
    await admision_service.aprobar(
        db, app.pedido.id, actor=admin, payload=payload, clave="cancel-sched-1"
    )
    await db.commit()

    pedido = await db.get(Pedido, app.pedido.id)
    target_time = db_utc(pedido.despliegue_programado_at) + timedelta(minutes=5)

    # El pedido se cancela
    pedido.estado = EstadoPedido.CANCELADO
    await db.commit()

    monkeypatch.setattr(clock, "now", lambda: target_time)
    res = await procesar_agenda(db)
    assert res["afectados"] == 0
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura)) == 0


async def test_perfil_bloqueado_impide_despacho(
    db, admin, app_order, future_dates, monkeypatch
):
    app = app_order
    app.body["vigencia"] = future_dates
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )
    payload = {
        **app.body,
        "capacidad_token": evaluation["capacidad_token"],
        "solicitar_despliegue": "programado",
    }
    await admision_service.aprobar(
        db, app.pedido.id, actor=admin, payload=payload, clave="blocked-prof-1"
    )
    await db.commit()

    pedido = await db.get(Pedido, app.pedido.id)
    target_time = db_utc(pedido.despliegue_programado_at) + timedelta(minutes=5)

    # Bloquear el perfil antes de la fecha inicial
    app.entry.update(estado="bloqueado", motivo_codigo="ADMIN_BLOCKED")

    monkeypatch.setattr(clock, "now", lambda: target_time)
    res = await procesar_agenda(db)
    assert res["afectados"] == 0
    assert any(item["motivo"] == "perfil_bloqueado" for item in res["omitidos"])
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura)) == 0


async def test_gracia_reserva_desde_max_aprobacion_inicio(
    db, admin, app_order, future_dates, monkeypatch
):
    app = app_order
    app.body["vigencia"] = future_dates
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )
    payload = {
        **app.body,
        "capacidad_token": evaluation["capacidad_token"],
        "solicitar_despliegue": "programado",
    }
    await admision_service.aprobar(
        db, app.pedido.id, actor=admin, payload=payload, clave="grace-period-1"
    )
    await db.commit()

    commitment = await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == app.pedido.id)
    )
    assert commitment is not None
    # La reserva vence 24h después del inicio futuro, no 24h después de la aprobación
    period_start = datetime(2027, 3, 1, 3, 0, tzinfo=timezone.utc)
    assert db_utc(commitment.expira_at) >= period_start + timedelta(hours=23)

    # Avanzar el reloj un mes (antes del inicio): la reserva no debe expirar
    one_month_later = clock.now() + timedelta(days=30)
    monkeypatch.setattr(clock, "now", lambda: one_month_later)
    res_expirar = await capacidad_service.expirar_reservas(db)
    assert res_expirar["afectados"] == 0
    await db.refresh(commitment)
    assert commitment.liberado_at is None
    assert commitment.estado == "reservado"


def test_decisiones_contradictorias_son_rechazadas_con_error(future_dates):
    # Desplegar inmediatamente = True con solicitar_despliegue = programado
    with pytest.raises(ValidationError):
        AprobacionEfectiva(
            asignacion={"template_id": 1, "tamano": "small", "vcpus": 1, "ram_mb": 512, "disk_gb": 4},
            vigencia=future_dates,
            capacidad_token="token-test",
            desplegar_inmediatamente=True,
            solicitar_despliegue="programado",
        )

    # Desplegar inmediatamente = True con solicitar_despliegue = False
    with pytest.raises(ValidationError):
        AprobacionEfectiva(
            asignacion={"template_id": 1, "tamano": "small", "vcpus": 1, "ram_mb": 512, "disk_gb": 4},
            vigencia=future_dates,
            capacidad_token="token-test",
            desplegar_inmediatamente=True,
            solicitar_despliegue=False,
        )
