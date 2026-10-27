"""Ciclo completo del pausado por inactividad.

El orden importa: primero se avisa, después se espera, recién entonces se pausa.
Un servicio que se apaga sin aviso previo es indistinguible de una falla para
quien lo estaba usando.
"""

from datetime import timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.metrica import MetricaSnapshot
from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.services import inactividad_service
from app.utils.clock import clock
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _sembrar(db, servicio_id, cpu=0.0, net_delta=0):
    """Cobertura suficiente (>= 80% de intervalos de 60s confirmados)."""
    fin = clock.now().replace(second=0, microsecond=0) - timedelta(minutes=1)
    esperadas = int(
        inactividad_service._muestras_esperadas(inactividad_service.VENTANA_INACTIVIDAD)
        * 0.8
    )
    filas = [
        dict(
            servicio_id=servicio_id,
            timestamp=fin - timedelta(minutes=esperadas - i - 1),
            intervalo_at=fin - timedelta(minutes=esperadas - i - 1),
            calidad="confirmada",
            estado_observado="running",
            cpu_usage_percent=cpu if i == 0 else 0.0,
            ram_usage_mb=128,
            disk_usage_gb=1,
            net_in_bytes=1000,
            net_out_bytes=1000,
            net_in_delta=net_delta if i == 0 else 0,
            net_out_delta=0,
            duracion_observada_s=60,
        )
        for i in range(esperadas)
    ]
    await db.execute(insert(MetricaSnapshot), filas)
    await db.commit()


async def _servicio_ocioso(db, proxmox, catedra, usuario, template, vmid=400):
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=vmid
    )
    proxmox.start_lxc("pve1", vmid)
    servicio.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos = 2
    ledger.ram_mb_retenida = 1024
    await db.commit()
    await _sembrar(db, servicio.id)
    return servicio


async def test_primero_avisa_y_no_pausa(
    db, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_ocioso(db, proxmox, catedra, usuario_catedra, template)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0, "no debe pausar en la primera pasada"
    assert servicio.id in resultado["avisados"]
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.aviso_pausa_at is not None
    assert servicio.pausa_programada_at is not None


async def test_durante_la_gracia_no_pausa(
    db, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_ocioso(db, proxmox, catedra, usuario_catedra, template)
    await inactividad_service.evaluar_inactividad(db)

    # Segunda pasada, todavía dentro del período de gracia.
    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_la_actividad_cancela_la_pausa_anunciada(
    db, proxmox, catedra, usuario_catedra, template
):
    """Si el servicio vuelve a usarse, el aviso no se cumple."""
    servicio = await _servicio_ocioso(db, proxmox, catedra, usuario_catedra, template)
    await inactividad_service.evaluar_inactividad(db)
    assert servicio.pausa_programada_at is not None

    # Llega actividad real: se reemplazan las muestras por unas con uso.
    await db.execute(
        MetricaSnapshot.__table__.delete().where(
            MetricaSnapshot.servicio_id == servicio.id
        )
    )
    await db.commit()
    await _sembrar(db, servicio.id, cpu=45.0, net_delta=50_000_000)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert servicio.id in resultado["cancelados"]
    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None
    assert servicio.aviso_pausa_at is None
    assert servicio.estado == EstadoServicio.RUNNING


async def test_vencida_la_gracia_pausa_y_detiene_el_contenedor(
    db, engine, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_ocioso(
        db, proxmox, catedra, usuario_catedra, template, vmid=400
    )
    await inactividad_service.evaluar_inactividad(db)

    # Se adelanta el fin de la gracia en lugar de esperar 48 horas.
    servicio.pausa_programada_at = clock.now().replace(tzinfo=None) - timedelta(minutes=1)
    await db.commit()

    resultado = await inactividad_service.evaluar_inactividad(db)
    assert resultado["afectados"] == 1

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.pausado_auto_at is not None
    # Lo que libera CPU y RAM de verdad es detener, no suspender.
    assert ("pve1", 400) in proxmox.detenidos


async def test_la_pausa_queda_registrada_con_el_sistema_como_autor(
    db, engine, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_ocioso(
        db, proxmox, catedra, usuario_catedra, template, vmid=401
    )
    await inactividad_service.evaluar_inactividad(db)
    servicio.pausa_programada_at = clock.now().replace(tzinfo=None) - timedelta(minutes=1)
    await db.commit()
    await inactividad_service.evaluar_inactividad(db)

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial)
                .where(ServicioHistorial.servicio_id == servicio.id)
                .order_by(ServicioHistorial.id)
            )
        )
        .scalars()
        .all()
    )

    confirmadas = [e for e in entradas if e.estado_nuevo == EstadoServicio.PAUSED.value]
    assert len(confirmadas) == 1
    assert confirmadas[0].usuario_id is None, "lo ejecutó el sistema, no una persona"
    assert "pausar" in confirmadas[0].comentario.lower()


async def test_el_exento_no_se_pausa(
    db, proxmox, catedra, usuario_catedra, template
):
    """"Siempre encendido": un servidor sin tráfico puede ser el que debe seguir."""
    servicio = await _servicio_ocioso(
        db, proxmox, catedra, usuario_catedra, template, vmid=402
    )
    servicio.exento_pausado = True
    await db.commit()

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    assert {"id": servicio.id, "motivo": "siempre_encendido"} in resultado["omitidos"]
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_no_pausa_con_una_operacion_del_portal_en_curso(
    db, proxmox, catedra, usuario_catedra, template
):
    """Pausar en medio de un despliegue dejaría el recurso en un estado ambiguo."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.EN_DESPLIEGUE,
    )
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        pedido_id=pedido.id,
        proxmox_vmid="410",
        estado=EstadoServicio.RUNNING,
    )
    await _sembrar(db, servicio.id)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    assert {"id": servicio.id, "motivo": "operacion_en_curso"} in resultado["omitidos"]


async def test_la_sincronizacion_no_borra_la_marca_de_pausa(
    db, engine, proxmox, catedra, usuario_catedra, template
):
    """Las lecturas ordinarias (sincronizar_estados) no alteran la marca de pausa."""
    from app.services.orquestacion_service import sincronizar_estados

    servicio = await _servicio_ocioso(
        db, proxmox, catedra, usuario_catedra, template, vmid=420
    )
    await inactividad_service.evaluar_inactividad(db)
    servicio.pausa_programada_at = clock.now().replace(tzinfo=None) - timedelta(minutes=1)
    await db.commit()
    await inactividad_service.evaluar_inactividad(db)

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED

    await sincronizar_estados(db, [servicio])

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED, (
        "el 'stopped' de Proxmox no debe degradar la pausa a apagado"
    )
    assert servicio.pausado_auto_at is not None


async def test_encenderlo_desde_el_portal_limpia_la_marca(
    client, db, engine, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Cuando el contenedor vuelve a iniciarse y confirmarse, la marca de pausa se limpia."""
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario_catedra, template, vmid=430
    )
    servicio.pausado_auto_at = clock.now().replace(tzinfo=None)
    await db.commit()

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_admin | {"Idempotency-Key": "start-430"},
        json={},
    )
    assert r.status_code == 202

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.pausado_auto_at is None
