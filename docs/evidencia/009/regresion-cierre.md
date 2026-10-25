> Registro histórico del 22/10/2026. La ejecución actual y sus límites están en [convergencia.md](convergencia.md). Las métricas citadas aquí no se atribuyen al código actualizado; prevalecen los datos del archivo de rendimiento identificado y el estado vigente de tasks.md. T101 figura marcada por ensayos locales; la aceptación universitaria sigue pendiente.

# Regresión general de cierre — T134 completada

Fecha de cierre: 2026-10-22. Todas las suites automatizadas de backend, PostgreSQL, frontend, contratos e infraestructura aprueban sin fallos bajo la política y contratos vigentes de la feature 009. Durante la adaptación de las 26 suites heredadas no se flexibilizó ningún control de seguridad, idempotencia, capacidad, vigencia ni validación de esquemas del backend. No se ejecutaron transportes reales de PVE ni SMTP durante pytest/Playwright.

## Resultados finales de T134 (2026-10-22)

| Suite / Comprobación | Comando | Resultado | Duración |
|---|---|---|---|
| Backend completo (SQLite + dobles) | `backend/venv/bin/pytest backend/tests --ignore=backend/tests/postgres -q` | **666 aprobadas, 0 fallidas** | 442,03 s (7 min 22 s) |
| Backend PostgreSQL 16 (aislado por esquema) | `TEST_DATABASE_URL=... backend/venv/bin/pytest --require-postgres -q backend/tests/postgres` | **99 aprobadas, 0 fallidas** | 204,94 s (3 min 24 s) |
| Contratos y JSON Schemas (Draft 2020-12) | `backend/venv/bin/python backend/scripts/validar_contratos.py` | **2 schemas OK, 13 ejemplos JSON válidos** | 0,25 s |
| Infra — `infra/runner/tests` | `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests` | **32 aprobadas, 4 omitidas (opt-in)** | 0,66 s |
| Infra — `infra/services/tests` | `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/services/tests` | **41 aprobadas, 0 fallidas** | 2,88 s |
| Infra — `infra/laboratorio/tests` | `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/laboratorio/tests` | **57 aprobadas, 0 fallidas** | 0,76 s |
| Infra — conjunto completo | `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests infra/laboratorio/tests` | **130 aprobadas, 4 omitidas** | 2,95 s |
| Frontend — Vitest (unitarias/componentes) | `npm --prefix frontend run test -- --run` | **10 archivos, 41 aprobadas, 0 fallidas** | 17,29 s |
| Frontend — Playwright E2E (Chromium) | `npm --prefix frontend run test:e2e` | **21 aprobadas, 0 fallidas** | 60,0 s |
| Frontend — Linter (`oxlint`) | `npm --prefix frontend run lint` | **0 errores, 8 advertencias heredadas** | 0,04 s |
| Frontend — Build de producción | `npm --prefix frontend run build` | **Compilación exitosa (bundle dividido)** | 1,10 s |
| Quickstart E2E (`test_quickstart_e2e.py`) | `backend/venv/bin/pytest backend/tests/test_quickstart_e2e.py -q` | **6 aprobadas, 0 fallidas** | 15,4 s |
| SC-008 en navegador (10 contextos, 100 servicios, 12,96M muestras) | `npm --prefix frontend run test:performance -- --config ... --execute` | **Aprobado**: p95 Pedidos 1567,9 ms (100 %), Servicios 2747,2 ms (98 %), Métricas 2472,3 ms (100 %) | Ver [rendimiento-navegador.json](rendimiento-navegador.json) |

## Resumen de adaptaciones en suites heredadas y hallazgos resueltos

1. **Expectativa obsoleta del tope de disco en `test_quickstart_e2e.py`**:
   - Se actualizó `test_escenario_5_abm_templates_y_limite_constitucional` conforme a T134 y a la eliminación del tope artificial de 8 GB: las ofertas nuevas exigen `definicion_version_id` publicada compatible (`422 definicion_requerida` si se omite) y aceptan discos mayores (p. ej. 16 GiB), manteniendo coherencia con `test_templates_admin.py` y `test_templates_edicion.py`.
2. **Contratos de solicitud, evaluación explícita, aprobación e idempotencia**:
   - Todas las mutaciones de pedidos, vigencias, calendarios, verificación de acceso y órdenes de infraestructura envían `Idempotency-Key` y respetan los esquemas cerrados (`extra='forbid'`).
   - La aprobación evalúa explícitamente mediante `POST /pedidos/{id}/evaluacion`, ligando selección, destino, vigencia y `capacidad_token`.
   - Reenviar y cancelar pedidos en `requiere_ajuste` son operaciones exclusivamente administrativas (`FR-003`, `A01`); el rol cátedra recibe `403`.
3. **Autoridad única de capacidad y operaciones asíncronas (`HTTP 202` + worker)**:
   - Las pruebas de capacidad, caducidad de reservas, reversión de aprobación, liberación y reactivación verifican `CompromisoCapacidad` (ledger) y `asignacion_snapshot` en lugar de las columnas retiradas (`reserva_*`).
   - Las órdenes de despliegue, inicio, detención, reinicio y baja devuelven `202 Accepted` con `OperacionInfraestructura` y se confirman mediante ejecución explícita del worker (`procesar_una`) con dobles de PVE y runner, más registro de evidencia `acceso_instancia` y `POST /servicios/{id}/verificar-acceso` cuando el caso requiere un servicio `ACTIVO` / `utilizable`.
   - En `operacion_service.admitir_orden`, se validó que una orden manual de detención (`detener`) enviada por un usuario sobre un servicio que ya se encuentra detenido y sin cómputo retenido se rechace con `409 estado_incompatible`, preservando la idempotencia interna para automatismos de sistema.
4. **Inactividad, intervalos confirmados y vencimientos**:
   - Las suites `test_inactividad_pausado.py`, `test_inactividad_sin_metricas.py`, `test_vencimiento_renovacion.py` y `test_vencimiento_renovacion_pendiente.py` construyen intervalos de un minuto con cobertura suficiente (`>= 80 %` en 7 días), deltas de red no negativos, identidad de infraestructura verificada (`IdentidadInfraestructura`) y vigencias autorizadas (`VigenciaAutorizada`).
5. **Notificaciones y outbox transaccional**:
   - `solicitud_service.crear`, `solicitud_service.reenviar` y `pedido_service.transicionar` encolan avisos en el outbox transaccional (`notificaciones`) respetando `recibir_notificaciones_email` y deduplicación por `(evento_clave, destinatario_normalizado, canal)`, sin ejecutar SMTP sincrónicamente dentro de la petición HTTP.

## Alcance y separación de evidencias

Esta regresión completa **T134** en simulación y base PostgreSQL 16 aislada. **No sustituye** las tareas de integración física e institucional pendientes para el entorno real / VM Proxmox (**T101**, **T102**, **T119** con responsable de cátedra, **T131** y **T133**).
