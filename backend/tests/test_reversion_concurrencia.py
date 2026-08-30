"""Compuerta constitucional de la reversión: los dos lados de la atomicidad.

Revertir **libera** capacidad, o sea que decide sobre ella, y por eso cae de
lleno en la exigencia de la constitución v3.0.0: escenario de concurrencia y al
menos un camino de fallo.

Los dos defectos posibles son opuestos y ambos son caros:

- **Liberar dos veces** (T007) infla el saldo libre por encima de la capacidad
  real, y el administrador termina aprobando sobre recursos que no existen —
  exactamente el defecto que la feature 004 vino a cerrar, entrando por una
  operación nueva.
- **Liberar a medias** (T008) deja capacidad soltada sobre un pedido que sigue
  aprobado: el invariante I3, la mitad opuesta.

Nota sobre el entorno: las pruebas corren sobre SQLite, donde el advisory lock
de PostgreSQL no existe (el motor ya serializa las escrituras). Lo que se
verifica acá es la otra mitad de la defensa, observable en ambos motores: que la
segunda reversión relea el estado y encuentre el pedido fuera de APROBADO.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.pedido import EstadoPedido, Pedido
from app.services import capacidad_service, pedido_service
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 8,
        "maxmem": 16 * 1024**3,
        "maxdisk": 100 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _aprobado(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


async def test_dos_reversiones_simultaneas_liberan_una_sola_vez(
    engine, client, db, catedra, usuario_catedra, template, admin, auth_admin
):
    """FR-004, FR-005, SC-006, I1 — el escenario que puede dejar el sistema peor.

    Se entrelazan a propósito dos sesiones independientes, como dos peticiones
    HTTP reales: **ambas leen el pedido aprobado antes de que ninguna escriba**,
    que es exactamente el orden que produce la doble liberación.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    antes = await capacidad_service.panorama(db)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as sesion_a, Session() as sesion_b:
        # Las dos ven el pedido todavía aprobado.
        assert (await sesion_a.get(Pedido, pedido.id)).estado == EstadoPedido.APROBADO
        assert (await sesion_b.get(Pedido, pedido.id)).estado == EstadoPedido.APROBADO

        await pedido_service.revertir_aprobacion(
            sesion_a, pedido.id, admin, motivo="me equivoqué de pedido"
        )

        with pytest.raises(Exception) as fallo:
            await pedido_service.revertir_aprobacion(
                sesion_b, pedido.id, admin, motivo="yo también lo estaba revirtiendo"
            )

    assert fallo.value.status_code == 409
    assert fallo.value.detail["codigo"] == "ya_revertido"

    despues = await capacidad_service.panorama(db)
    assert (
        despues["libre"]["vcpus"] == antes["libre"]["vcpus"] + template.default_vcpus
    ), (
        "la capacidad libre debe subir exactamente una vez: si sube el doble, el "
        "administrador aprobará sobre recursos que no existen"
    )


async def test_un_fallo_a_mitad_de_camino_no_deja_nada_a_medias(
    engine, client, db, catedra, usuario_catedra, template, admin, auth_admin, monkeypatch
):
    """FR-004, P3, I3 — el camino de fallo.

    Se simula una falla **después** de liberar la reserva y **antes** de
    confirmar el cambio de estado. La transacción tiene que revertirse entera:
    un pedido que sigue aprobado con la capacidad ya soltada sería peor que el
    defecto original, porque el saldo libre contaría como disponible algo que en
    realidad está comprometido.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    comprometida = await capacidad_service.panorama(db)

    def _explota(*args, **kwargs):
        raise RuntimeError("la base se cayó justo después de liberar la reserva")

    monkeypatch.setattr(pedido_service, "cambiar_estado", _explota)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as sesion:
        with pytest.raises(RuntimeError):
            await pedido_service.revertir_aprobacion(
                sesion, pedido.id, admin, motivo="esta reversión no va a terminar"
            )

    # Se comprueba desde una sesión limpia: lo que importa es lo que quedó en la
    # base, no lo que crea la sesión que falló.
    async with Session() as verificacion:
        quedo = await verificacion.get(Pedido, pedido.id)
        assert quedo.estado == EstadoPedido.APROBADO, "el pedido no puede quedar revertido a medias"
        assert quedo.reserva_vcpus == template.default_vcpus
        assert quedo.reserva_ram_mb == template.default_ram_mb
        assert quedo.reserva_disk_gb == template.default_disk_gb
        assert quedo.reserva_expira_at is not None

        despues = await capacidad_service.panorama(verificacion)
        assert despues["libre"] == comprometida["libre"], (
            "nunca puede haber capacidad liberada sobre un pedido que sigue aprobado (I3)"
        )
