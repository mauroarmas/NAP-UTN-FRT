#!/usr/bin/env python3
"""Medición de rendimiento de consola administrativa (US4 - T087 / SC-004):
Captura a consulta p95 <= 5 s, apertura <= 3 s y comprobación de ausencia
de secretos en fragmentos y base de datos.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import statistics
import time
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.models.consola_operacion import ConsolaOperacion, ConsolaFragmento
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.operacion_service import LeaseOperacion
from app.services.consola_operacion_service import emitir_hito, ingerir, consultar
from app.utils.clock import clock


from infra.applications.job.protocol import public_identity

SENSITIVE_PATTERNS = [
    "PRIVATE KEY",
    "password",
    "secreto-admin",
    "api_key",
    "bearer ",
    "BEGIN OPENSSH",
]


async def run_measurement(db_url: str = "sqlite+aiosqlite:///:memory:"):
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        from app.database import Base
        await conn.run_sync(Base.metadata.create_all)

    latencies_capture_to_query = []
    open_latencies = []

    async with session_factory() as db:
        identity = IdentidadInfraestructura(
            cluster_id=str(uuid4()),
            nodo="pve1",
            vmid=801,
            pool_catedra="nap-apps",
            nonce_cifrado="bench-nonce-1234",
        )
        db.add(identity)
        await db.flush()

        owner = uuid4()
        operation = OperacionInfraestructura(
            tipo="desplegar",
            identidad_infraestructura_id=identity.id,
            actor_tipo="sistema",
            actor_id_normalizado="benchmark",
            idempotency_key=str(uuid4()),
            request_hash="b" * 64,
            estado="en_curso",
            fase="preparacion",
            lease_owner=owner,
            lease_generation=1,
            lease_until=clock.now() + timedelta(minutes=5),
            contexto_seguro={"job_fingerprint": "f" * 64},
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
        await db.commit()

        # Ingerir 200 mensajes en lotes simulando salida continua
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
            "configuracion_sha256": "c" * 64,
            "perfil": {"id": "docker-ubuntu24", "revision": 1, "sha256": "a" * 64},
            "after": 0,
            "limit_bytes": 65536,
        }

        user_admin = type("User", (), {"id": 1, "rol": "admin"})()

        boot_id = str(uuid4())
        for batch_idx in range(10):
            seqs = list(range(batch_idx * 20 + 1, (batch_idx + 1) * 20 + 1))
            capture_times = []
            items = []
            for s in seqs:
                t_cap = clock.now()
                capture_times.append(t_cap)
                items.append({
                    "execution_id": str(attempt.execution_id),
                    "source_seq": s,
                    "captured_at": t_cap.isoformat().replace("+00:00", "Z"),
                    "fase": "instalacion",
                    "stream": "stdout",
                    "texto_depurado": f"Línea de log #{s} de proceso benchmarking.",
                })

            response_data = {
                "protocol": "nap-application-job/1",
                "ok": True,
                "action": "read",
                "data": {
                    **public_identity(request),
                    "fingerprint": "f" * 64,
                    "node_boot_id": boot_id,
                    "estado": "ejecutando",
                    "fase": "instalacion",
                    "last_source_seq": seqs[-1],
                    "acknowledged_seq": 0,
                    "resultado": None,
                    "error_codigo": None,
                    "items": items,
                    "dropped_ranges": [],
                },
            }

            t0 = time.perf_counter()
            await ingerir(db, lease, request=request, response=response_data)
            await db.commit()
            ingest_duration = time.perf_counter() - t0

            # Medir latencia de consulta
            t_query_start = time.perf_counter()
            consola = await consultar(db, operation.id, usuario=user_admin)
            query_duration = time.perf_counter() - t_query_start

            open_latencies.append(query_duration)

            for t_cap in capture_times:
                diff = (clock.now() - t_cap).total_seconds()
                latencies_capture_to_query.append(diff)

        # Análisis de secretos en base de datos
        fragments = list((await db.scalars(select(ConsolaFragmento).where(ConsolaFragmento.operacion_raiz_id == operation.id))).all())
        secretos_encontrados = []
        for frag in fragments:
            for pat in SENSITIVE_PATTERNS:
                if pat.lower() in frag.texto_depurado.lower():
                    secretos_encontrados.append((frag.seq, pat))

    p95_capture_to_query = statistics.quantiles(latencies_capture_to_query, n=20)[18] if len(latencies_capture_to_query) >= 20 else max(latencies_capture_to_query)
    max_open_latency = max(open_latencies)
    avg_open_latency = statistics.mean(open_latencies)

    report = {
        "fecha": datetime.now(timezone.utc).isoformat(),
        "total_mensajes": len(fragments),
        "latencia_captura_a_pantalla_p95_s": round(p95_capture_to_query, 4),
        "latencia_apertura_max_s": round(max_open_latency, 4),
        "latencia_apertura_promedio_s": round(avg_open_latency, 4),
        "objetivo_p95_cumplido": p95_capture_to_query <= 5.0,
        "objetivo_apertura_cumplido": max_open_latency <= 3.0,
        "secretos_encontrados_en_db": len(secretos_encontrados),
    }

    await engine.dispose()
    return report


if __name__ == "__main__":
    result = asyncio.run(run_measurement())
    print(json.dumps(result, indent=2))
