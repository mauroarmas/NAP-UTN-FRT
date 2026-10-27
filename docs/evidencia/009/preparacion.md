# Preparación de implementación — T001–T007

Fecha: 2026-10-20. Conserva el [baseline](baseline.md) y los cambios previos del usuario. Estas pruebas usan dobles y PostgreSQL temporal; no acreditan integración institucional.

| Tarea | Resultado verificado |
|---|---|
| T001 | Revisión y head Alembic registrados; 320 pasan y un fallo anterior al cambio. |
| T002 | requirements.lock resuelto con uv 0.11.31 para Python 3.12, hashes y dependencias directas de cifrado/schema/auditoría/pruebas/Alembic. Instalación con verificación de hashes; uv pip check: 105 paquetes compatibles. |
| T003 | Vitest 5.0.5, Testing Library y Playwright 1.64.1 fijados. Un test de ingreso rechazado pasa en jsdom; un recorrido sin sesión pasa en Chromium contra SPA compilada. Red de aplicación simulada. |
| T004 | PostgreSQL 16 temporal, loopback 55432, esquema aleatorio por test y sesiones independientes. Nueve pruebas de destino seguro/conexiones pasan. No se modifica public ni una base operativa. |
| T005 | Dobles ampliados (inventario, tareas diferidas/fallidas, identidad, reloj y runner), tres cátedras y bloqueo de red real. Veinticuatro regresiones seleccionadas backend y tres controles de red/procesos infra pasan. |
| T006 | Digest oficial de Node 22 consultado con imagetools y ejecutado sin red: v22.23.3. Build Docker del stage builder exitoso con ese digest; imagen local nap009-frontend-test. READMEs con ejecución aislada. |
| T007 | Workflow YAML validado: backend, PostgreSQL, frontend, contratos e infra (matriz que ejecuta cada suite y falla con cero tests). Comprobaciones locales equivalentes ejecutadas; workflow remoto todavía no disparado. |

Regresión completa tras preparación: **329 pasan y un fallo**, 147,88 s. Es exactamente el fallo antiguo de test_escenario_5_abm_templates_y_limite_constitucional, pendiente de T134; no se silencia ni excluye en CI. Las nueve pruebas adicionales pasan. Esta fase no cambia el comportamiento del portal ni declara verde la suite completa.

Frontend: lint termina con código 0 y las dieciséis advertencias existentes; Vitest 1/1 y Playwright 1/1. Build Docker Node 22 conserva la advertencia de chunk grande; su corrección corresponde a T116. Ambos schemas pasan metavalidación Draft 2020-12 y los trece ejemplos JSON se parsean mediante backend/scripts/validar_contratos.py.

En el sandbox se observaron restricciones sobre SQLite asíncrono, sockets y servidor de navegador; las comprobaciones que lo requerían se repitieron fuera con autorización. Las suites infra continúan bloqueando red/procesos mediante sus fixtures aun cuando pytest corre fuera. Los resultados no provienen de llamadas al clúster real.

Archivos de herramientas/ignore revisados según el proyecto real: Git y Docker; no hay ESLint/Prettier/Terraform/Helm ni publicación npm (private=true). Se añadieron únicamente patrones faltantes para logs/cachés/builds/reportes. Los comandos y destinos de prueba están en backend/README.md y frontend/README.md.
