"""El silencio no es lo mismo que la inactividad.

Es la prueba más importante de la feature. Si la recolección de métricas se cae,
la ausencia de datos se parece a cero uso: sin una regla de cobertura mínima, el
sistema apagaría servicios en plena cursada.

Un falso positivo acá es más caro que no pausar nunca nada: no pausar solo
desperdicia capacidad, apagar de más interrumpe el trabajo de alguien.
"""

from datetime import datetime, timedelta

from app.models.metrica import MetricaSnapshot
from app.models.servicio import EstadoServicio
from app.services import inactividad_service
from tests import factories


async def _servicio_corriendo(db, catedra, template, vmid="300"):
    return await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid=vmid,
        estado=EstadoServicio.RUNNING,
    )


async def _sembrar_metricas(db, servicio_id, cantidad, cpu=0.0, net=0.0):
    """Reparte `cantidad` de muestras a lo largo de la ventana de observación."""
    ahora = datetime.utcnow()
    paso = inactividad_service.VENTANA_INACTIVIDAD / max(cantidad, 1)
    for i in range(cantidad):
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


async def test_sin_ninguna_metrica_no_se_pausa(db, proxmox, catedra, template):
    """El caso de la recolección nunca ejecutada."""
    servicio = await _servicio_corriendo(db, catedra, template)

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    assert resultado["avisados"] == []
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.pausa_programada_at is None


async def test_con_cobertura_insuficiente_no_se_pausa(db, proxmox, catedra, template):
    """El caso de la recolección caída a mitad de la ventana.

    Hay datos, y todos dicen "sin uso", pero son demasiado pocos para afirmar
    nada sobre la ventana completa.
    """
    servicio = await _servicio_corriendo(db, catedra, template)
    esperadas = inactividad_service._muestras_esperadas(
        inactividad_service.VENTANA_INACTIVIDAD
    )
    # La mitad de lo esperado: por debajo del umbral de cobertura.
    await _sembrar_metricas(db, servicio.id, esperadas // 2, cpu=0.0, net=0.0)

    veredicto = await inactividad_service.evaluar_actividad(db, servicio)

    assert veredicto["inactivo"] is False
    assert veredicto["motivo"] == "sin_cobertura"
    assert "no es inactividad" in veredicto["detalle"]


async def test_el_motivo_de_no_pausar_queda_registrado(db, proxmox, catedra, template):
    """Distinguir "no lo usó nadie" de "no lo miramos" tiene que ser auditable."""
    servicio = await _servicio_corriendo(db, catedra, template)

    resultado = await inactividad_service.evaluar_inactividad(db)

    omitidos = {o["id"]: o["motivo"] for o in resultado["omitidos"]}
    assert omitidos[servicio.id] == "sin_cobertura"


async def test_con_cobertura_suficiente_y_sin_uso_si_se_evalua_inactivo(
    db, proxmox, catedra, template
):
    """Contraprueba: con datos suficientes, el heurístico sí actúa.

    Sin esto, las pruebas anteriores pasarían aunque la detección estuviera rota
    de forma que nunca pausa nada.
    """
    servicio = await _servicio_corriendo(db, catedra, template)
    esperadas = inactividad_service._muestras_esperadas(
        inactividad_service.VENTANA_INACTIVIDAD
    )
    await _sembrar_metricas(db, servicio.id, esperadas, cpu=0.0, net=0.0)

    veredicto = await inactividad_service.evaluar_actividad(db, servicio)

    assert veredicto["inactivo"] is True
    assert veredicto["motivo"] == "sin_uso"


async def test_los_servicios_preexistentes_no_se_pausan_por_falta_de_historial(
    db, proxmox, catedra, template
):
    """Al aplicar el cambio no hay historial de métricas para nadie.

    La regla de cobertura ya los protege: no hace falta código especial de
    migración para evitar una pausa masiva el primer día.
    """
    for i in range(3):
        await _servicio_corriendo(db, catedra, template, vmid=f"31{i}")

    resultado = await inactividad_service.evaluar_inactividad(db)

    assert resultado["afectados"] == 0
    assert len(resultado["omitidos"]) == 3
    assert all(o["motivo"] == "sin_cobertura" for o in resultado["omitidos"])
