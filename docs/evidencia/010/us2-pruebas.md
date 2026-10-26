# US2 — validación local

Fecha: 2026-10-25. Árbol de trabajo 010 sin commit; no se construyó una imagen operativa ni se conectó al builder/PVE real.

Se ejecutaron pruebas de revisión técnica 1:N, deduplicación, rol/CAS/JSON cerrado, bloqueo de publicación directa, manifiesto 1.1, evidencia sin proveedor obligatoria, leases y resultado de generación antigua. El pipeline integrado usa builder/runner/PVE simulados y sesiones nuevas por fase: resolver → confirmar inputs → construir → distribuir → dos identidades y LXC → bootstrap → lista para comprobar → descarte → cancel → eliminación → cleanup. Se repite perdiendo la respuesta después de create; mantiene exactamente dos recursos. Un fallo de cleanup retiene presupuesto hasta el reintento confirmado; el artefacto permanece.

Comandos finales desde la raíz:

```bash
backend/venv/bin/python -m pytest -c backend/pytest.ini -q backend/tests/test_ensayo_pipeline_010.py backend/tests/test_ensayo_worker_010.py backend/tests/test_biblioteca_redaccion_010.py
backend/venv/bin/python -m pytest -c backend/pytest.ini -q backend/tests/test_ensayo_limpieza_010.py backend/tests/test_ensayos_api_010.py
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/builder/tests infra/runner/tests infra/services/tests infra/laboratorio/tests
```

Resultados: **5 passed** (pipeline, reconciliación, leases, redacción); **9 passed** (API/vencimiento por fase); **141 passed, 4 skipped** (infraestructura; omisiones de integración explícita). Infra incluye cancel anterior a build, cierre conservado tras reinicio, reintento de cancel interrumpido, esquema cerrado, lectura segura/recarga del registro, distribución atómica con hashes, saneamiento Draw.io, bootstrap HTTPS idempotente y rechazo de identidad ajena. El builder mantiene el rootfs temporal en el mismo filesystem presupuestado y sólo mueve al directorio final un resultado completo.

PostgreSQL real aislado: **4 passed** en `tests/postgres/test_ensayo_capacidad_010.py`: primera reserva con scope vacío compartido entre hosts, dos ensayos por último saldo, ensayo contra aprobación y dos workers sobre una operación. Las reservas PVE son indivisibles para ambos LXC; capacidad y filas se bloquean en orden común. SQLite no se usa como prueba de concurrencia.

Frontend: prueba recuperación de revisión/ensayo, conservación tras error, estados vencido/descartado y limpieza pendiente. Playwright cubre recarga, entradas fijadas y descarte durable; las suites generales se detallan en [regresion.md](regresion.md).

Esto acredita implementación local y fallos simulados. **T052 continúa pendiente**: faltan host builder y perfiles operativos, receta comprometida, paquete real y dos LXC comprobados. Nunca se registra evidencia sintética como evidencia operativa.
