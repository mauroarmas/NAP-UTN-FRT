# Baseline de implementación — feature 009

Fecha: 2026-10-20 (America/Argentina/Tucuman). Registro anterior a cambios de implementación; no acredita los criterios de la feature 009.

- Revisión: `90834285b7af6e73684c9973cf491798b861a586`, rama `008-notificaciones-email`.
- Head Alembic: `8b9c0d1e2f3a` (`python -m alembic heads`; sin conectar ni migrar una base).
- Python 3.12.3; Node v24.16.0 del equipo. La imagen frontend existente usa Node 20; T006 fija la rama 22 requerida por el plan.
- Cambios previos preservados: metadata/constitución de Spec Kit, feature 009, informe de análisis y bajas de los documentos de seguimiento.

| Comprobación | Resultado observado |
|---|---|
| `cd backend` y `./venv/bin/python -m pytest -q --tb=short` | 320 pasan, 1 falla, 2361 advertencias; 145,97 s. Ejecutada fuera del sandbox con dobles PVE/SMTP y SQLite en memoria de los fixtures existentes. |
| `npm --prefix frontend run lint` | Código 0; 16 advertencias existentes de imports/variables/hooks/exportación de componentes. |
| `npm --prefix frontend run build` | Código 0; Vite 8.1.4, 2463 módulos; chunk JS inicial 792,10 kB (233,72 kB gzip), advertencia de chunk >500 kB. |
| Pruebas PostgreSQL/frontend/runner/imágenes | Todavía no existen las suites/herramientas propuestas por esta feature. No se consideran verificadas. |

Fallo conocido: `backend/tests/test_quickstart_e2e.py::test_escenario_5_abm_templates_y_limite_constitucional` conserva la expectativa obsoleta de rechazar un disco de 10 GiB. La política vigente admite discos grandes; T134 actualiza esa regresión sin reintroducir el tope. El fallo está separado de las regresiones futuras de implementación.

La ejecución dentro del sandbox quedó detenida antes de la primera prueba en el fixture SQLite/aiosqlite; se interrumpió y se repitió fuera, donde terminó. No se tocó ninguna base operativa ni se ejecutaron migraciones, seeds, trabajos programados o llamadas al clúster real.

Los resultados nuevos y sus comandos se registrarán en los documentos de cada fase, conservando este baseline.
