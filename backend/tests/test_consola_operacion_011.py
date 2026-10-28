"""Pruebas de consola administrativa de lectura (US4 - T077):
Contrato GET, cursores after/before/through_seq, tail inicial, límites,
recorte/expiración, no-store y admin vigente por página.
"""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest

from app.models.consola_operacion import ConsolaOperacion, ConsolaFragmento
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.operacion_service import LeaseOperacion
from app.services.consola_operacion_service import emitir_hito, ingerir
from app.utils.clock import clock
from tests.test_ingesta_consola_011 import batch


@pytest.fixture
async def setup_operacion_consola(db):
    """Crea una operación, identidad e intento con fragmentos de consola para pruebas."""
    identity = IdentidadInfraestructura(
        cluster_id=str(uuid4()),
        nodo="pve1",
        vmid=601,
        pool_catedra="nap-apps",
        nonce_cifrado="fixture-test-consola",
    )
    db.add(identity)
    await db.flush()

    owner = uuid4()
    operation = OperacionInfraestructura(
        tipo="desplegar",
        identidad_infraestructura_id=identity.id,
        actor_tipo="sistema",
        actor_id_normalizado="fixture",
        idempotency_key=str(uuid4()),
        request_hash="a" * 64,
        estado="en_curso",
        fase="preparacion",
        lease_owner=owner,
        lease_generation=1,
        lease_until=clock.now() + timedelta(minutes=2),
        contexto_seguro={"job_fingerprint": "f" * 64},
    )
    db.add(operation)
    await db.flush()

    attempt = IntentoDespliegue(
        operacion_id=operation.id,
        operacion_raiz_id=operation.id,
        numero=1,
        identidad_infraestructura_id=identity.id,
        configuracion_sha256="b" * 64,
        estado="ejecutando",
    )
    db.add(attempt)
    await db.commit()

    lease = LeaseOperacion(operation.id, owner, 1)
    # Hito del portal (seq 1)
    await emitir_hito(db, lease, hito="creando_recurso")
    await db.commit()

    # Fragmentos del runner (seq 2 y 3)
    request = {
        "protocol": "nap-application-job/1",
        "action": "read",
        "operation_id": str(operation.id),
        "operacion_raiz_id": str(operation.id),
        "intento_id": str(attempt.id),
        "execution_id": str(attempt.execution_id),
        "lease_generation": 1,
        "cluster_uuid": identity.cluster_id,
        "node": identity.nodo,
        "vmid": identity.vmid,
        "resource_uuid": str(identity.resource_uuid),
        "pool": identity.pool_catedra,
        "nonce": "e" * 64,
        "configuracion_sha256": "b" * 64,
        "perfil": {"id": "docker-ubuntu24", "revision": 1, "sha256": "a" * 64},
        "after": 0,
        "limit_bytes": 65536,
    }
    job = SimpleNamespace(
        identity=identity,
        operation=operation,
        attempt=attempt,
        request=request,
        lease=lease,
        boot=str(uuid4()),
    )
    await ingerir(db, lease, request=request, response=batch(job, sequences=(1, 2)))
    await db.commit()

    return SimpleNamespace(
        identity=identity,
        operation=operation,
        attempt=attempt,
        lease=lease,
        job=job,
    )


async def test_consola_requiere_autenticacion_y_rol_admin(
    client, setup_operacion_consola, auth_catedra, auth_admin
):
    op_id = setup_operacion_consola.operation.id

    # 1. Sin autenticación -> 401
    resp = await client.get(f"/operaciones/{op_id}/consola")
    assert resp.status_code == 401

    # 2. Con rol docente / cátedra -> 403
    resp = await client.get(f"/operaciones/{op_id}/consola", headers=auth_catedra)
    assert resp.status_code == 403

    # 3. Con rol admin -> 200
    resp = await client.get(f"/operaciones/{op_id}/consola", headers=auth_admin)
    assert resp.status_code == 200


async def test_consola_operacion_no_encontrada(client, auth_admin):
    resp = await client.get(f"/operaciones/{uuid4()}/consola", headers=auth_admin)
    assert resp.status_code == 404
    detail = resp.json().get("detail", {})
    assert detail.get("codigo") == "operacion_no_encontrada"


async def test_consola_tail_inicial_y_cabeceras_no_store(
    client, setup_operacion_consola, auth_admin
):
    op = setup_operacion_consola.operation
    resp = await client.get(f"/operaciones/{op.id}/consola", headers=auth_admin)
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-store"

    data = resp.json()
    assert data["operation_id"] == str(op.id)
    assert data["operacion_raiz_id"] == str(op.id)
    assert data["estado"] == "en_curso"
    assert data["fase"] == "creacion"
    assert data["intento_efectivo"] == 1
    assert data["first_retained_seq"] == 1
    assert data["last_seq"] == 3
    assert data["truncated"] is False
    assert data["expired"] is False
    assert len(data["items"]) == 3

    # Orden ascendente por seq
    seqs = [it["seq"] for it in data["items"]]
    assert seqs == [1, 2, 3]

    # Tipos de streams y textos depurados
    assert data["items"][0]["stream"] == "sistema"
    assert data["items"][0]["texto_depurado"] == "Creando el recurso de la aplicación."
    assert data["items"][1]["stream"] == "stdout"
    assert "Paquete instalado" in data["items"][1]["texto_depurado"]


async def test_consola_cursores_after_y_before_mutuamente_excluyentes(
    client, setup_operacion_consola, auth_admin
):
    op_id = setup_operacion_consola.operation.id

    # 1. Ambos parámetros -> 422
    resp = await client.get(
        f"/operaciones/{op_id}/consola?after=1&before=3", headers=auth_admin
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", {})
    assert detail.get("codigo") == "parametros_consulta_invalidos"

    # 2. after=1 -> items con seq > 1 (seq 2 y 3)
    resp = await client.get(
        f"/operaciones/{op_id}/consola?after=1", headers=auth_admin
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [it["seq"] for it in items] == [2, 3]
    assert resp.json()["next_cursor"] == 3

    # 3. before=3 -> items con seq < 3 (seq 1 y 2)
    resp = await client.get(
        f"/operaciones/{op_id}/consola?before=3", headers=auth_admin
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [it["seq"] for it in items] == [1, 2]
    assert resp.json()["previous_cursor"] == 1


async def test_consola_through_seq_para_exportacion(
    client, setup_operacion_consola, auth_admin
):
    op_id = setup_operacion_consola.operation.id

    # Congelar through_seq=2 (ignora seq 3)
    resp = await client.get(
        f"/operaciones/{op_id}/consola?through_seq=2", headers=auth_admin
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [it["seq"] for it in items] == [1, 2]


async def test_consola_after_detras_del_rango_retenido_salta_a_disponible(
    client, setup_operacion_consola, auth_admin, db
):
    op_id = setup_operacion_consola.operation.id

    # Simular recorte: eliminar fragmentos 1 y 2
    header = await db.get(ConsolaOperacion, op_id)
    header.first_retained_seq = 3
    header.truncated = True
    header.dropped_messages = 2
    await db.commit()

    # Consultar con after=0 (detrás de first_retained_seq)
    resp = await client.get(
        f"/operaciones/{op_id}/consola?after=0", headers=auth_admin
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["truncated"] is True
    assert data["first_retained_seq"] == 3
    # Debe devolver el rango disponible comenzando en first_retained_seq (seq 3)
    assert [it["seq"] for it in data["items"]] == [3]


async def test_consola_expirada_devuelve_cabecera_y_resultado_sin_404(
    client, setup_operacion_consola, auth_admin, db
):
    op_id = setup_operacion_consola.operation.id

    # Marcar expirada en cabecera
    header = await db.get(ConsolaOperacion, op_id)
    header.expired = True
    header.ultimo_resultado_seguro = {
        "hito": "disponible",
        "texto": "La aplicación está disponible.",
    }
    await db.commit()

    resp = await client.get(f"/operaciones/{op_id}/consola", headers=auth_admin)
    assert resp.status_code == 200
    data = resp.json()
    assert data["expired"] is True
    assert data["resultado_final"] == {
        "hito": "disponible",
        "texto": "La aplicación está disponible.",
    }


async def test_consola_creacion_fallida_antes_de_job_nodo(client, db, auth_admin):
    """Verifica que si la creación falla antes de existir un job de nodo, la consola
    devuelve los hitos seguros del portal y el resultado final sin error 404 ni 500."""
    identity = IdentidadInfraestructura(
        cluster_id=str(uuid4()),
        nodo="pve1",
        vmid=602,
        pool_catedra="nap-apps",
        nonce_cifrado="fixture-test-fallo-pre-job",
    )
    db.add(identity)
    await db.flush()

    owner = uuid4()
    operation = OperacionInfraestructura(
        tipo="desplegar",
        identidad_infraestructura_id=identity.id,
        actor_tipo="sistema",
        actor_id_normalizado="fixture",
        idempotency_key=str(uuid4()),
        request_hash="b" * 64,
        estado="en_curso",
        fase="preparacion",
        lease_owner=owner,
        lease_generation=1,
        lease_until=clock.now() + timedelta(minutes=2),
        contexto_seguro={},
    )
    db.add(operation)
    await db.flush()

    attempt = IntentoDespliegue(
        operacion_id=operation.id,
        operacion_raiz_id=operation.id,
        numero=1,
        identidad_infraestructura_id=identity.id,
        configuracion_sha256="c" * 64,
        estado="ejecutando",
    )
    db.add(attempt)
    await db.commit()

    lease = LeaseOperacion(operation.id, owner, 1)
    await emitir_hito(db, lease, hito="creando_recurso")
    await emitir_hito(db, lease, hito="fallo")
    operation.estado = "fallida"
    attempt.estado = "fallido"
    await db.commit()

    resp = await client.get(
        f"/operaciones/{operation.id}/consola", headers=auth_admin
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "fallida"
    assert data["fase"] == "finalizada"
    assert len(data["items"]) == 2
    assert data["items"][0]["texto_depurado"] == "Creando el recurso de la aplicación."
    assert data["items"][1]["texto_depurado"] == "No se pudo completar el despliegue."
    assert data["resultado_final"] == {
        "hito": "fallo",
        "texto": "No se pudo completar el despliegue.",
    }


async def test_consola_limite_bytes_valido_y_rechazo_fuera_de_rango(
    client, setup_operacion_consola, auth_admin
):
    op_id = setup_operacion_consola.operation.id

    # 1. Fuera de rango: limit_bytes=0 o > 65536 -> 422
    resp = await client.get(
        f"/operaciones/{op_id}/consola?limit_bytes=0", headers=auth_admin
    )
    assert resp.status_code == 422

    resp = await client.get(
        f"/operaciones/{op_id}/consola?limit_bytes=70000", headers=auth_admin
    )
    assert resp.status_code == 422

    # 2. Límite pequeño que sólo permita 1 fragmento
    resp = await client.get(
        f"/operaciones/{op_id}/consola?after=1&limit_bytes=45", headers=auth_admin
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["seq"] == 2
    assert data["has_more"] is True


async def test_consola_resuelve_raiz_desde_operacion_hija(
    client, setup_operacion_consola, auth_admin, db
):
    op = setup_operacion_consola.operation
    identity = setup_operacion_consola.identity

    # Cerrar la operación previa para permitir una nueva operación sobre la identidad
    op.estado = "fallida"
    await db.commit()

    # Crear una segunda operación (reintento/reparación) que apunta a op.id como raíz
    child_op = OperacionInfraestructura(
        tipo="reparar",
        operacion_raiz_id=op.id,
        identidad_infraestructura_id=identity.id,
        actor_tipo="sistema",
        actor_id_normalizado="fixture",
        idempotency_key=str(uuid4()),
        request_hash="c" * 64,
        estado="en_curso",
        fase="instalacion",
    )
    db.add(child_op)
    await db.commit()

    # Consultar la consola usando child_op.id
    resp = await client.get(
        f"/operaciones/{child_op.id}/consola", headers=auth_admin
    )
    assert resp.status_code == 200
    data = resp.json()
    # operation_id es la consultada, operacion_raiz_id es la raíz
    assert data["operation_id"] == str(child_op.id)
    assert data["operacion_raiz_id"] == str(op.id)
    # Los fragmentos corresponden a la raíz común
    assert len(data["items"]) == 3
