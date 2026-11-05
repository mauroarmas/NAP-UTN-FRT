# Evidencia de pruebas automatizadas consolidadas — Feature 011 (T102)

Fecha: 28/10/2026  
Rama: `011-desplegar-servicios-universitarios`  
Entorno: Linux x86_64, Python 3.12, Node.js v20, PostgreSQL aislado (Docker test container en `:55432`)

---

## 1. Resumen ejecutivo de resultados

Todas las suites automatizadas seleccionadas han sido ejecutadas satisfactoriamente con **0 fallos pendientes**:

| Suite | Componente / Tipo | Comandos ejecutados | Pruebas | Tiempo | Resultado |
|---|---|---|---|---|---|
| **Backend 011** | Dominio y servicios | `pytest -c backend/pytest.ini -q backend/tests/test_*011.py` | 97 | 46.17 s | **97/97 Aprobadas** |
| **Infraestructura** | Runtime Docker, red, spool, retención | `pytest -c infra/pytest.ini -q infra/applications/tests/` | 50 | 12.03 s | **48 Aprobadas / 2 Omitidas** |
| **PostgreSQL Concurrencia** | Base de datos real aislada | `TEST_DATABASE_URL=... pytest -c backend/pytest.ini -q backend/tests/postgres/` | 22 | 38.18 s | **22/22 Aprobadas** |
| **Vitest** | Frontend unitario y componentes | `npm --prefix frontend test -- --run tests/*.test.jsx` | 22 | 6.61 s | **22/22 Aprobadas** |
| **Frontend Build** | Compilación de producción | `npm --prefix frontend run build` | 2496 mod | 0.94 s | **0 Errores (100% limpio)** |
| **Playwright E2E** | Pruebas integradas de UI | `npm --prefix frontend run test:e2e -- tests/e2e/*.spec.js` | 6 | 10.9 s | **6/6 Aprobadas** |

---

## 2. Detalle de ejecuciones y comandos

### 2.1 Backend Pytest (97 pruebas)
Comando:
```bash
backend/venv/bin/python -m pytest -c backend/pytest.ini -q \
  backend/tests/test_biblioteca_despliegue_011.py \
  backend/tests/test_pedidos_aplicaciones_011.py \
  backend/tests/test_consola_operacion_011.py \
  backend/tests/test_ingesta_consola_011.py \
  backend/tests/test_recuperacion_aplicaciones_011.py \
  backend/tests/test_ciclo_vida_aplicaciones_011.py \
  backend/tests/test_endpoint_reintentar_operacion_011.py \
  backend/tests/test_regresion_servicios_011.py \
  backend/tests/test_aislamiento_aplicaciones_011.py
```
Resultado: `97 passed in 46.17s`.

### 2.2 Infraestructura y Runtime (50 pruebas)
Comando:
```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q \
  infra/applications/tests/test_docker_runtime.py \
  infra/applications/tests/test_network_policy.py \
  infra/applications/tests/test_isolation_receipt.py \
  infra/applications/tests/test_secret_retention.py \
  infra/applications/tests/test_redaction.py
```
Resultado: `48 passed, 2 skipped in 12.03s`.

### 2.3 PostgreSQL aislado con carreras y concurrencia (22 pruebas)
Comando:
```bash
TEST_DATABASE_URL=postgresql+asyncpg://nap_test:nap_test_local_only@127.0.0.1:55432/nap_test_009 \
backend/venv/bin/python -m pytest -c backend/pytest.ini -q \
  backend/tests/postgres/test_admision_aplicaciones_011.py \
  backend/tests/postgres/test_catalogo_aplicaciones_011.py \
  backend/tests/postgres/test_consola_011.py \
  backend/tests/postgres/test_despliegue_011.py \
  backend/tests/postgres/test_instalaciones_simultaneas_011.py \
  backend/tests/postgres/test_jobs_011.py \
  backend/tests/postgres/test_migracion_011.py \
  backend/tests/postgres/test_reintentos_011.py
```
Resultado: `22 passed in 38.18s`.

### 2.4 Frontend Vitest (22 pruebas)
Comando:
```bash
npm --prefix frontend test -- --run \
  tests/biblioteca-despliegue.test.jsx \
  tests/pedidos-otro-aplicacion.test.jsx \
  tests/progreso-despliegue.test.jsx \
  tests/consola-operacion.test.jsx \
  tests/recuperacion-aplicaciones.test.jsx
```
Resultado: `22 passed in 6.61s`.

### 2.5 Frontend Build
Comando:
```bash
npm --prefix frontend run build
```
Resultado: `✓ built in 941ms`.

### 2.6 Frontend Playwright E2E (6 pruebas)
Comando:
```bash
npm --prefix frontend run test:e2e -- \
  tests/e2e/despliegue-aplicaciones.spec.js \
  tests/e2e/regresion-servicios-011.spec.js
```
Resultado: `6 passed in 10.9s`.

---

## 3. Conclusión

El conjunto de pruebas automatizadas cubre íntegramente los requerimientos funcionales y no funcionales de la especificación 011: catálogo Docker Hub, referencias de imágenes propias, aprobación indivisible, despliegue programado, consola de lectura en tiempo real con truncamiento seguro y cuota de 10 MB, ciclo de vida sin pull repetido, reintentos idempotentes y compatibilidad de regresión con IaaS y Draw.io.
No se reportan fallos pendientes.

