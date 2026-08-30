"""Dos decisiones simultáneas sobre la misma capacidad disponible.
Compuerta de la constitución v2.0.0: el código que decide sobre capacidad tiene
que probarse con al menos un escenario de concurrencia, porque su fallo
característico no aparece en una ejecución aislada — aparece cuando dos
decisiones individualmente correctas se toman a la vez.

Nota sobre el entorno: las pruebas corren sobre SQLite, donde el advisory lock
de PostgreSQL no existe (el motor ya serializa las escrituras). Lo que se
verifica acá es la otra mitad de la defensa, que sí es observable en ambos
motores: que una confirmación basada en números viejos no se complete.
"""


import pytest

from app.models.pedido import EstadoPedido
from app.services import capacidad_service
from tests import factories

NODO_JUSTO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        # Capacidad para exactamente un pedido del template de prueba.
        "maxcpu": 1,
        "maxmem": 512 * 1024**2,
        "maxdisk": 4 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster_justo(proxmox):
    proxmox.nodos = NODO_JUSTO
    return proxmox


async def _dos_pedidos(db, catedra, usuario, template):
    return (
        await factories.crear_pedido(
            db,
            catedra_id=catedra.id,
            solicitante_id=usuario.id,
            template_id=template.id,
            estado=EstadoPedido.SOLICITADO,
        ),
        await factories.crear_pedido(
            db,
            catedra_id=catedra.id,
            solicitante_id=usuario.id,
            template_id=template.id,
            estado=EstadoPedido.SOLICITADO,
        ),
    )


async def test_dos_admins_con_el_mismo_token_solo_uno_aprueba(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El escenario real: dos personas mirando la misma pantalla.

    Ambas abren su pedido cuando hay capacidad para uno solo, así que las dos
    ven el mismo saldo libre y el mismo token. La primera que confirma se lleva
    la capacidad; la segunda debe encontrarse con que sus números ya no valen.
    """
    uno, dos = await _dos_pedidos(db, catedra, usuario_catedra, template)

    ev_uno = await client.get(f"/pedidos/{uno.id}/evaluacion", headers=auth_admin)
    ev_dos = await client.get(f"/pedidos/{dos.id}/evaluacion", headers=auth_admin)
    # Misma foto de capacidad para los dos: nadie aprobó todavía.
    assert ev_uno.json()["capacidad_token"] == ev_dos.json()["capacidad_token"]

    primera = await client.post(
        f"/pedidos/{uno.id}/aprobar",
        json={"capacidad_token": ev_uno.json()["capacidad_token"]},
        headers=auth_admin,
    )
    segunda = await client.post(
        f"/pedidos/{dos.id}/aprobar",
        json={"capacidad_token": ev_dos.json()["capacidad_token"]},
        headers=auth_admin,
    )

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["detail"]["codigo"] == "token_desactualizado"


async def test_aprobaciones_en_sesiones_distintas_no_pierden_reserva(
    engine, db, catedra, usuario_catedra, template, admin
):
    """Dos aprobaciones en sesiones independientes, entrelazadas.

    Cada petición HTTP real usa su propia sesión de base. Acá se reproduce eso
    con dos sesiones separadas y se las entrelaza a propósito: **ambas leen la
    capacidad antes de que ninguna escriba**, que es exactamente el orden que
    produce el defecto.

    Sobre el alcance de lo que esta prueba puede demostrar: el paralelismo real
    no es observable sobre SQLite en memoria, donde todas las sesiones comparten
    una única conexión y el motor serializa las escrituras. La exclusión mutua
    en producción la da el advisory lock de PostgreSQL. Lo que sí queda probado
    acá, y es independiente del motor, es que la contabilidad no pierde ni
    duplica reservas cuando dos decisiones se toman sobre la misma foto.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services.pedido_service import aprobar_pedido

    uno, dos = await _dos_pedidos(db, catedra, usuario_catedra, template)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as sesion_a, Session() as sesion_b:
        # Las dos miran la capacidad antes de que ninguna escriba.
        antes_a = await capacidad_service.panorama(sesion_a)
        antes_b = await capacidad_service.panorama(sesion_b)
        assert antes_a["capacidad_token"] == antes_b["capacidad_token"]

        await aprobar_pedido(
            sesion_a, uno.id, admin, justificacion_capacidad="urgencia de cursada"
        )
        await aprobar_pedido(
            sesion_b, dos.id, admin, justificacion_capacidad="urgencia de cursada"
        )

    estado = await capacidad_service.panorama(db)
    assert estado["reservado"]["vcpus"] == 2 * template.default_vcpus, (
        "la capacidad reservada debe reflejar exactamente lo aprobado: "
        "ni de más (doble conteo) ni de menos (reserva perdida por la carrera)"
    )


async def test_la_reserva_no_se_cuenta_dos_veces_al_desplegar(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Al existir el servicio, el pedido deja de contar como reserva.

    Es la propiedad que hace que la reserva derivada no pueda desincronizarse:
    no hay un paso de "convertir reserva en consumo" que pueda fallar a medias.
    """
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)

    con_reserva = await capacidad_service.panorama(db)
    assert con_reserva["reservado"]["vcpus"] == template.default_vcpus

    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        pedido_id=pedido.id,
        proxmox_vmid="180",
        vcpus=template.default_vcpus,
        ram_mb=template.default_ram_mb,
        disk_gb=template.default_disk_gb,
    )

    desplegado = await capacidad_service.panorama(db)
    assert desplegado["reservado"]["vcpus"] == 0, "ya no es una reserva"
    assert desplegado["desplegado"]["vcpus"] == template.default_vcpus
    # Lo comprometido no cambió: la reserva se volvió consumo, no se sumó.
    assert desplegado["comprometido"]["vcpus"] == con_reserva["comprometido"]["vcpus"]
