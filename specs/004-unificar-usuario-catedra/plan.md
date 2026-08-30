# Implementation Plan: Unificación usuario–cátedra y control de recursos por aprobación

**Branch**: `004-unificar-usuario-catedra` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-unificar-usuario-catedra/spec.md`

## Summary

Se unifica la cuenta de acceso (una persona, varias cátedras), se elimina el techo de recursos
declarado por cátedra, y el control de capacidad se traslada al momento de la aprobación — donde
**aprobar reserva**, para que dos decisiones individualmente correctas no puedan sobrecomprometer el
clúster. La capacidad se recupera por dos vías: un vencimiento por servicio (determinista) y el
pausado automático de lo que nadie usa (oportunista).

Enfoque técnico, derivado de [research.md](./research.md): la relación `Usuario→Cátedra` se
invierte (`catedras.titular_id`); el cálculo de capacidad se centraliza en un servicio nuevo que
reemplaza a `verificar_cuota`; la reserva se modela **derivada** del pedido aprobado, sin tabla
nueva, para no crear doble contabilidad; la atomicidad se resuelve con advisory lock de PostgreSQL
(no-op en SQLite) **más** un token de capacidad que rechaza confirmaciones sobre datos viejos; y
los tres procesos automáticos se implementan como funciones de servicio puras invocables tanto por
un planificador nuevo como por endpoints admin.

## Technical Context

**Language/Version**: Python 3.12 (backend), JavaScript ES2022 (frontend)

**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 (async), Alembic 1.16, proxmoxer 2.2,
React 18 + Vite. **Nueva**: APScheduler (planificador de trabajos periódicos, R1)

**Storage**: PostgreSQL (producción, vía asyncpg) / SQLite en memoria (pruebas, vía aiosqlite)

**Testing**: pytest 9.1 + pytest-asyncio, con `FakeProxmoxClient` como doble de prueba
(`backend/tests/fakes.py`). Infraestructura ya existente: 10 archivos de prueba, `conftest.py` con
base en memoria y cliente HTTP.

**Target Platform**: Linux server (clúster Proxmox VE de la UTN FRT)

**Project Type**: Aplicación web — backend FastAPI + frontend React SPA

**Performance Goals**: El cálculo de capacidad se ejecuta en cada apertura de la pantalla de
aprobación y en cada confirmación; debe resolverse en una consulta agregada, no iterando servicios
en Python. Los trabajos periódicos no deben bloquear el bucle de eventos de la app.

**Constraints**:

- La atomicidad de la reserva debe funcionar en PostgreSQL **y** ser verificable en SQLite, donde
  los mecanismos de bloqueo no existen (R2).
- El planificador convive con despliegue multi-worker: los trabajos no deben ejecutarse por
  duplicado (R1).
- La migración elimina columnas y reasigna titularidades: cada paso debe ser reversible (R8).

**Scale/Scope**: Decenas de cátedras, cientos de servicios, un puñado de administradores. Es la
escala que justifica filtrar cátedras en el cliente (R12) y descartar Celery (R1).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluado contra la constitución **v2.0.0** (enmendada el 2026-08-16 específicamente para esta
feature).

### Evaluación inicial (pre-investigación)

| Principio | Estado | Justificación |
|---|---|---|
| I. Proxmox es el back-end | ✅ PASS | Ninguna capacidad nueva expone Proxmox. La consola y las credenciales no se tocan. El mapeo "pausado del portal" ↔ "detenido en Proxmox" queda del lado del portal, que es donde el principio lo ubica. |
| II. Máquina de estados única | ⚠ ATENCIÓN | La feature agrega transiciones ejecutadas por el sistema. El principio (v2.0.0) ya las admite, pero exige autor propio y ejecutor real. **Riesgo detectado**: `APROBADO → RECHAZADO` (expiración de reserva) no existe en `TRANSICIONES_VALIDAS`. Debe agregarse con su ejecutor. |
| III. Operaciones recuperables | ✅ PASS | Reforzado: la expiración de reservas extiende "sin recursos huérfanos" a la capacidad comprometida. La reactivación fallida deja el servicio en `PAUSED`, estado definido. |
| IV. Aislamiento; capacidad al aprobar | ✅ PASS | Es el principio que esta feature implementa. Aislamiento conservado y ampliado a N cátedras. |
| V. Historial no se destruye | ✅ PASS | La cátedra sigue siendo dueña de sus recursos, por lo que reasignar titular no rompe la trazabilidad. Se **agrega** historial de servicios, que hoy no existía. |
| VI. La cátedra pide y observa | ✅ PASS | La cátedra gana reactivar y renovar (acciones sobre lo propio, permitidas). Aprobar sigue siendo exclusivo del administrador. Los avisos previos cumplen el deber nuevo de no ejecutar por sorpresa. |
| Compuerta de pruebas | ⚠ ATENCIÓN | Toda esta feature toca orquestación, máquina de estados y control de capacidad → pruebas obligatorias **con** camino de fallo de infraestructura **y** escenario de concurrencia. |

**Veredicto**: PASS con dos puntos de atención, ninguno un incumplimiento. Ambos son obligaciones de
implementación registradas, no excepciones solicitadas.

### Re-evaluación (post-diseño Fase 1)

| Principio | Estado | Cómo lo resuelve el diseño |
|---|---|---|
| I | ✅ PASS | Sin cambios respecto de la evaluación inicial. |
| II | ✅ PASS | `data-model.md` declara explícitamente la transición faltante y la marca como tarea obligatoria para `/speckit-tasks`. Los dos ejecutores de `EN_DESPLIEGUE → ACTIVO` (alta y renovación) son ambos concretos. El autor sistema se resuelve con `usuario_id` nullable en ambos historiales. |
| III | ✅ PASS | La reserva derivada (R3) elimina por construcción la posibilidad de que el registro y la realidad diverjan: no hay contador que mantener sincronizado. |
| IV | ✅ PASS | `capacidad_service` es fuente única; el token más el advisory lock cubren respectivamente la decisión mal informada y la carrera real. El cálculo incluye reservas vigentes, como exige el principio. |
| V | ✅ PASS | `servicios_historial` de solo agregado. Las migraciones son reversibles. La bitácora de accesos perdidos conserva copias de `username` y `catedra_nombre` para sobrevivir a borrados. |
| VI | ✅ PASS | `GET /capacidad` es admin-only. La cátedra ve vencimiento y estado en términos propios, nunca capacidad del clúster. |
| Compuerta | ✅ PASS | `quickstart.md` fija como bloqueantes los escenarios E4 (la reserva descuenta), E8 (silencio ≠ inactividad) y E10 (sin fugas), más la prueba de concurrencia. |

**Veredicto post-diseño**: PASS. Sin violaciones que justificar — la tabla de Complexity Tracking
queda vacía.

## Project Structure

### Documentation (this feature)

```text
specs/004-unificar-usuario-catedra/
├── plan.md              # Este archivo
├── research.md          # Fase 0 — 12 incógnitas resueltas
├── data-model.md        # Fase 1 — esquema, estados, migraciones
├── quickstart.md        # Fase 1 — validación E1–E10
├── contracts/
│   └── api.md           # Fase 1 — endpoints nuevos y modificados
├── checklists/
│   └── requirements.md  # Calidad de la spec
└── tasks.md             # Fase 2 (/speckit-tasks — NO lo crea /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── usuario.py           # quita catedra_id
│   │   ├── catedra.py           # quita cuotas, suma titular_id
│   │   ├── pedido.py            # suma tipo, servicio_id, reserva_*; historial nullable
│   │   ├── servicio.py          # suma vence_at y marcas de pausa
│   │   ├── servicio_historial.py    # NUEVO
│   │   └── job_lock.py              # NUEVO
│   ├── services/
│   │   ├── capacidad_service.py     # NUEVO — fuente única de capacidad, reserva, token, lock
│   │   ├── acceso_service.py        # NUEVO — catedras_visibles / requiere_acceso_catedra
│   │   ├── vencimiento_service.py   # NUEVO — vencimientos y renovaciones
│   │   ├── inactividad_service.py   # NUEVO — detección y pausado
│   │   ├── scheduler.py             # NUEVO — APScheduler + lock, sin lógica propia
│   │   ├── pedido_service.py        # quita verificar_cuota; suma aprobar/rechazar con reserva
│   │   └── orquestacion_service.py  # ejecutor de renovación; respeta pausado_auto_at
│   ├── routers/
│   │   ├── capacidad.py             # NUEVO — GET /capacidad
│   │   ├── admin_jobs.py            # NUEVO — POST /admin/jobs/{nombre}
│   │   ├── usuarios.py              # alta con catedra_ids, atómica
│   │   ├── catedras.py              # quita validación de cuotas; suma titular
│   │   ├── pedidos.py               # aprobar/rechazar; filtro multi-cátedra
│   │   ├── servicios.py             # reactivar/renovar/pausados/exentos
│   │   └── metricas.py              # filtro multi-cátedra
│   └── main.py                      # arranca el planificador en lifespan
├── alembic/versions/                # 4 revisiones nuevas (ver data-model.md)
└── tests/
    ├── test_capacidad_reserva.py        # NUEVO — incluye concurrencia (constitución)
    ├── test_aislamiento_multicatedra.py # NUEVO — regresión sobre todos los listados
    ├── test_vencimiento_renovacion.py   # NUEVO
    ├── test_inactividad_pausado.py      # NUEVO — incluye "sin métricas no pausa"
    ├── test_alta_usuario_catedras.py    # NUEVO
    ├── test_migracion_titular.py        # NUEVO
    └── test_soft_delete_cuota.py        # REESCRITO contra capacidad, no contra cuota

frontend/
├── src/
│   ├── components/
│   │   ├── SelectorCatedras.jsx     # NUEVO — buscador con marcado múltiple (R12)
│   │   ├── PanelCapacidad.jsx       # NUEVO — los números del admin al aprobar
│   │   └── PanelCatedra.jsx         # quita consumo vs cuota; suma vencimientos
│   ├── pages/
│   │   ├── Usuarios.jsx             # alta con SelectorCatedras
│   │   ├── Catedras.jsx             # quita campos de cuota; suma titular
│   │   ├── Pedidos.jsx              # pantalla de aprobación con capacidad y token
│   │   └── Servicios.jsx            # reactivar, renovar, exento, vencimiento
│   └── services/api.js              # endpoints nuevos
```

**Structure Decision**: se mantiene la estructura de aplicación web ya existente (backend FastAPI +
frontend React), sin reorganizarla. La feature agrega cinco servicios de backend y dos componentes
de frontend, todos siguiendo las convenciones vigentes del repositorio: la lógica de negocio vive
en `app/services/` y los routers no invocan `proxmoxer` directamente (Principio I).

Cuatro de los servicios nuevos existen para satisfacer un principio concreto: `capacidad_service`
es la fuente única que exige el Principio IV, y `acceso_service` centraliza el filtrado multi-cátedra
que hoy está repetido en seis lugares y que, disperso, es la fuga de datos más probable de toda la
feature (riesgo 10 de la spec).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Sin violaciones. La Constitution Check pasó en ambas evaluaciones y no se solicita ninguna
excepción, por lo que esta tabla queda intencionalmente vacía.
