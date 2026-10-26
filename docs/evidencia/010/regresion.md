# Regresión 010

Fecha: 2026-10-25. Base inicial `48224777537aed89e807ac74cee2b8584a520305`, rama `010-integrar-biblioteca-aplicaciones`, cambios sin commit. Ninguna prueba utilizó Proxmox operativo.

| Suite y comando | Resultado observado |
|---|---|
| `cd backend && venv/bin/python -m pytest -q -m 'not postgres'` | **734 passed**, 106 deselected, 3469 warnings, 482.97 s |
| `cd backend && TEST_DATABASE_URL=… venv/bin/python -m pytest --require-postgres -q tests/postgres` | **108 passed**, 663 warnings, 221.73 s |
| `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/builder/tests infra/runner/tests infra/services/tests infra/laboratorio/tests` | **141 passed**, 4 skipped, 4.34 s |
| `npm --prefix frontend test -- --run` (última ejecución) | **49 passed**, 13 archivos, 20.90 s |
| `npm --prefix frontend run test:e2e` | **32 passed**, 1.1 min; build Vite incluido |
| `npm --prefix frontend run lint` | sin errores; 8 advertencias anteriores de hooks/exports |
| `backend/venv/bin/python backend/scripts/validar_contratos.py` | 3 schemas válidos (incluye 1.1) y 13 ejemplos JSON |
| `git diff --check`, `bash -n` de instalación/receta/runner | sin errores |

La regresión backend se inició antes de agregar los casos finales de expiración; éstos se ejecutaron separadamente (**9 passed**, API y vencimiento). Tras ajustar orden de locks/identidades y logs se reejecutaron pipeline/worker/redacción (**5 passed**). Tras ampliar snapshots/aviso/congelación se reejecutaron pedidos biblioteca (**2 passed**). La suite PG completa precede al nuevo caso de dos workers; el archivo final capacidad/workers se ejecutó completo: **4 passed**. No se suman estos números a las suites completas porque contienen pruebas repetidas.

Alembic tiene un único head: **010_03_seleccion_oferta**. Las pruebas migran un esquema legacy aislado por 009 hasta head y comparan nuevas tablas con modelos; preservan snapshots/historia y no reconstruyen selecciones históricas. Restaurar cerca generaciones de ensayo, conserva ciphertext y origen y no reanuda una ejecución de copia. Se amplió también el fingerprint de habilitación y la inspección de claves a las tablas nuevas.

Durante integración se corrigieron un supuesto de test que fijaba head 009, mocks incompletos del catálogo y renovación indebida de clave ante un 409 sin cambio de contenido. Una primera ejecución sobrecargada tuvo timeout de conexión PG/worker Vitest; otra detectó una carrera intermitente en el test existente de regularización de fechas. Se conservaron las pruebas y las ejecuciones completas posteriores pasaron. No se relajaron los límites ni se omitieron suites para obtener el resultado.

CI incorpora builder como cuarto elemento de la matriz infra, además de backend, PostgreSQL, frontend/navegador/lint y contratos. Las cuatro omisiones infra son integraciones explícitas con entorno real; consultar sus marcas antes de acreditar aceptación.

Cierre posterior: worker/redacción/configuración operativa reejecutados tras el último ajuste de validación de rutas: **27 passed**, 4.34 s. Build frontend final: **correcto**, 565 ms. `git diff --check` final sin errores. Se detuvo y eliminó el contenedor/red exclusivos de `docker-compose.test.yml`; no quedó una base de pruebas iniciada por esta sesión.
