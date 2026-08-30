"""Ciclo completo del pausado por inactividad.

El orden importa: primero se avisa, después se espera, recién entonces se pausa.
Un servicio que se apaga sin aviso previo es indistinguible de una falla para
quien lo estaba usando.
"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.metrica import MetricaSnapshot
from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.services import inactividad_service
from tests import factories
from tests.fakes import ocupar


async def _sembrar(db, servicio_id, cpu=0.0, net=0.0):
    """Cobertura completa de la ventana con el nivel de actividad indicado."""
    ahora = datetime.utcnow()
    esperadas = inactividad_service._muestras_esperadas(
        inactividad_service.VENTANA_INACTIVIDAD
    )
    paso = inactividad_service.VENTANA_INACTIVIDAD / esperadas
    for i in range(esperadas):
        db.add(
            MetricaSnapshot(
                servicio_id=servicio_id,
                cpu_usage_percent=cpu,
                ram_usage_mb=128,
                disk_usage_gb=1,
                net_in_bytes=net,
                net_out_bytes=0,
                timestamp=ahora - paso * i,
            )
        )
    await db.commit()


async def _servicio_ocioso(db, catedra, template, vmid="400"):
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid=vmid,
        estado=EstadoServicio.RUNNING,
    )
    await _sembrar(db, servicio.id)
    return servicio


async def test_primero_avisa_y_no_pausa(db, proxmox, catedra, template):
    servicio = await _servicio_ocioso(db, catedra, template)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0, "no debe pausar en la primera pasada"
    assert servicio.id in resultado["avisados"]
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.aviso_pausa_at is not None
    assert servicio.pausa_programada_at is not None


async def test_durante_la_gracia_no_pausa(db, proxmox, catedra, template):
    servicio = await _servicio_ocioso(db, catedra, template)
    await inactividad_service.evaluar_inactividad(db)

    # Segunda pasada, todavía dentro del período de gracia.
    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_la_actividad_cancela_la_pausa_anunciada(db, proxmox, catedra, template):
    """Si el servicio vuelve a usarse, el aviso no se cumple."""
    servicio = await _servicio_ocioso(db, catedra, template)
    await inactividad_service.evaluar_inactividad(db)
    assert servicio.pausa_programada_at is not None

    # Llega actividad real: se reemplazan las muestras por unas con uso.
    await db.execute(
        MetricaSnapshot.__table__.delete().where(
            MetricaSnapshot.servicio_id == servicio.id
        )
    )
    await db.commit()
    await _sembrar(db, servicio.id, cpu=45.0, net=50_000_000)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert servicio.id in resultado["cancelados"]
    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None
    assert servicio.aviso_pausa_at is None
    assert servicio.estado == EstadoServicio.RUNNING


async def test_vencida_la_gracia_pausa_y_detiene_el_contenedor(
    db, proxmox, catedra, template
):
    servicio = await _servicio_ocioso(db, catedra, template)
    await inactividad_service.evaluar_inactividad(db)

    # Se adelanta el fin de la gracia en lugar de esperar 48 horas.
    servicio.pausa_programada_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 1
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.pausado_auto_at is not None
    # Lo que libera CPU y RAM de verdad es detener, no suspender.
    assert ("pve1", 400) in proxmox.detenidos


async def test_la_pausa_queda_registrada_con_el_sistema_como_autor(
    db, proxmox, catedra, template
):
    servicio = await _servicio_ocioso(db, catedra, template)
    await inactividad_service.evaluar_inactividad(db)
    servicio.pausa_programada_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()
    await inactividad_service.evaluar_inactividad(db)

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial).where(
                    ServicioHistorial.servicio_id == servicio.id
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(entradas) == 1
    assert entradas[0].estado_nuevo == EstadoServicio.PAUSED.value
    assert entradas[0].usuario_id is None, "lo ejecutó el sistema, no una persona"
    assert "Sin uso desde" in entradas[0].comentario
    # La cátedra tiene que saber que el disco sigue ocupado.
    assert "almacenamiento" in entradas[0].comentario.lower()


async def test_el_exento_no_se_pausa(db, proxmox, catedra, template):
    """"Siempre encendido": un servidor sin tráfico puede ser el que debe seguir."""
    servicio = await _servicio_ocioso(db, catedra, template)
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
    db, proxmox, catedra, template
):
    """Proxmox reporta "stopped" para una pausa del portal y para un apagado manual.

    La distinción vive en el portal: si la sincronización la pisara, la cátedra
    no podría saber si lo apagó ella o si se lo pausaron.
    """
    from app.services.orquestacion_service import sincronizar_estados

    servicio = await _servicio_ocioso(db, catedra, template, vmid="420")
    await inactividad_service.evaluar_inactividad(db)
    servicio.pausa_programada_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()
    await inactividad_service.evaluar_inactividad(db)
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED

    # El clúster reporta el contenedor detenido, que es lo que la pausa hizo.
    proxmox.recursos = [ocupar(420, "cat-svc", status="stopped")]
    await sincronizar_estados(db, [servicio])

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED, (
        "el 'stopped' de Proxmox no debe degradar la pausa a apagado"
    )
    assert servicio.pausado_auto_at is not None


async def test_encenderlo_desde_proxmox_limpia_la_marca(
    db, proxmox, catedra, template
):
    """Si el contenedor volvió a arrancar por fuera, la pausa dejó de ser cierta."""
    from app.services.orquestacion_service import sincronizar_estados

    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="430",
        estado=EstadoServicio.PAUSED,
    )
    servicio.pausado_auto_at = datetime.utcnow()
    await db.commit()

    # El clúster lo reporta corriendo: alguien lo encendió por fuera del portal.
    proxmox.recursos = [ocupar(430, "cat-svc", status="running")]
    await sincronizar_estados(db, [servicio])

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.pausado_auto_at is None
