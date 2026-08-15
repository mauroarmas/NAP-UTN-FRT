# Implementation Plan: Recuperación de Errores y Eliminación Lógica de Pedidos/Servicios

**Branch**: `001-pedido-soft-delete-retry` | **Date**: 2026-08-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-pedido-soft-delete-retry/spec.md`

## Summary

Dos capacidades de backend sobre la máquina de estados existente:

1. **Reintento de despliegue** para pedidos caídos en ERROR, pseudo-idempotente: persiste el VMID reservado antes de llamar a Proxmox, y al reintentar reutiliza ese VMID si sigue libre, adopta el contenedor si detecta un huérfano propio de un fallo parcial, o pide un VMID nuevo si fue tomado por un tercero.
2. **Baja lógica** (`deleted_at`) en `Pedido` y `Servicio`, con exclusión por defecto en todos los listados y consultas de cuota, preservando el historial de consumo por cátedra.

El enfoque técnico central es **extraer la lógica de aprovisionamiento a una función compartida** (`_ejecutar_despliegue`) con dos puntos de entrada que difieren solo en la validación del estado de entrada. Eso elimina de raíz el desajuste actual entre `TRANSICIONES_VALIDAS` (que permite ERROR → EN_DESPLIEGUE) y `desplegar_pedido()` (que exige APROBADO), causa del pedido "colgado". Ver [research.md](./research.md) R1–R5.

## Technical Context

**Language/Version**: Python 3.12.3

**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 (async/asyncpg), Alembic 1.16, Pydantic Settings 2.9, proxmoxer 2.2

**Storage**: PostgreSQL vía `postgresql+asyncpg`; migraciones con Alembic (una revisión existente: `ce2e9b4b4077_initial_schema`)

**Testing**: pytest + pytest-asyncio + httpx + aiosqlite — **a incorporar en este hito** (hoy no existe ninguna prueba en el repositorio; ver [research.md](./research.md) R6)

**Target Platform**: Servidor Linux; API consumida por un frontend React (fuera del alcance de este hito)

**Project Type**: Aplicación web — backend FastAPI + frontend React (solo se toca backend)

**Performance Goals**: N/A — el volumen es de decenas de pedidos por cuatrimestre, no hay objetivos de throughput. El costo dominante son las llamadas sincrónicas a la API de Proxmox.

**Constraints**: Las operaciones contra Proxmox son sincrónicas y bloqueantes dentro de handlers async (comportamiento preexistente, no se modifica en este hito). El reintento no debe crear contenedores duplicados bajo ninguna secuencia de fallos.

**Scale/Scope**: ~8 sitios de consulta a corregir para el filtro de baja lógica, 2 modelos, 1 migración, 2 endpoints nuevos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitución evaluada**: v1.0.0, ratificada 2026-08-07.

| Principio | Resultado | Fundamento |
|-----------|-----------|------------|
| I. Proxmox es el back-end, nunca la interfaz | **PASS** | Toda llamada nueva a la infraestructura queda dentro de `orquestacion_service.py`; el router solo delega. El `vmid_reservado` es estado interno, no algo que la cátedra deba conocer. |
| II. La máquina de estados es la única fuente de verdad | **PASS — remedia** | El feature corrige exactamente la violación vigente: `ERROR → EN_DESPLIEGUE` está declarada como válida pero ningún código la ejecuta. T015/T019 le dan ejecutor real. Ninguna tarea asigna `estado` fuera de `cambiar_estado`. |
| III. Toda operación contra la infraestructura debe ser recuperable | **PASS — remedia** | Es el objeto central de US1: persistencia de la reserva (R1), adopción de huérfanos para no duplicar contenedores (R2), y reintento pseudo-idempotente. FR-010 impide marcar como dado de baja si Proxmox no liberó el recurso. |
| IV. Aislamiento y cuota por cátedra | **PASS** | FR-012 y T029 aseguran que lo dado de baja deje de ocupar cuota. El feature no toca los filtros por cátedra existentes ni el tope de disco. |
| V. El historial académico no se destruye | **PASS — remedia** | US2 implementa literalmente este principio. El `PedidoHistorial` se mantiene de solo agregado también en los reintentos (FR-005). |
| Compuerta de calidad (pruebas) | **PASS** | El feature toca orquestación, máquina de estados y cuotas, así que la compuerta aplica: T011–T014 y T023–T025 incluyen simulación de fallo de infraestructura mediante el doble de prueba de T004. |

**Resultado global**: **PASS**, sin violaciones. No se registran entradas en Complexity Tracking.

**Nota**: tres principios se marcan como *remedia* porque el código actual los incumple y este feature es precisamente la corrección. Esa deuda es preexistente, no introducida acá.

**Re-evaluación post-Phase 1**: sin cambios; el diseño no introduce proyectos, capas ni patrones adicionales — extiende dos modelos y dos servicios existentes.

## Project Structure

### Documentation (this feature)

```text
specs/001-pedido-soft-delete-retry/
├── plan.md              # Este archivo
├── spec.md              # Especificación funcional
├── research.md          # Phase 0 — decisiones técnicas (R1–R7)
├── data-model.md        # Phase 1 — cambios de modelo y migración
├── quickstart.md        # Phase 1 — guía de validación end-to-end
├── contracts/
│   └── api.md           # Phase 1 — contrato de los endpoints nuevos/modificados
├── checklists/
│   └── requirements.md  # Checklist de calidad del spec
└── tasks.md             # Phase 2 — generado por /speckit-tasks (NO por este comando)
```

### Source Code (repository root)

Archivos existentes que se modifican y archivos nuevos, sobre la estructura real del repo:

```text
backend/
├── alembic/
│   └── versions/
│       ├── ce2e9b4b4077_initial_schema.py      # existente
│       └── <nueva>_soft_delete_y_vmid.py       # NUEVO: deleted_at + vmid_reservado
├── app/
│   ├── models/
│   │   ├── pedido.py                           # MOD: deleted_at, vmid_reservado
│   │   └── servicio.py                         # MOD: deleted_at
│   ├── schemas/
│   │   ├── pedido.py                           # MOD: exponer deleted_at / vmid_reservado
│   │   └── servicio.py                         # MOD: exponer deleted_at
│   ├── routers/
│   │   ├── pedidos.py                          # MOD: filtro + DELETE + POST reintentar
│   │   ├── servicios.py                        # MOD: filtro en listados/detalle
│   │   ├── catedras.py                         # MOD: filtro en uso de recursos
│   │   └── metricas.py                         # MOD: filtro en consultas de servicios
│   ├── services/
│   │   ├── orquestacion_service.py             # MOD: _ejecutar_despliegue + reintentar
│   │   ├── pedido_service.py                   # MOD: filtro en verificar_cuota, baja de pedido
│   │   └── metricas_service.py                 # MOD: filtro en captura de snapshots
│   └── utils/
│       └── soft_delete.py                      # NUEVO: helpers de filtrado
├── tests/                                      # NUEVO (todo el directorio)
│   ├── conftest.py                             # fixtures: DB en memoria, fake Proxmox, cliente
│   ├── test_reintento_despliegue.py
│   └── test_soft_delete.py
└── requirements.txt                            # MOD: dependencias de testing
```

**Structure Decision**: Se mantiene la estructura de aplicación web ya establecida (`backend/app` con separación models / schemas / routers / services / utils). El feature no introduce capas nuevas: agrega un módulo de utilidades (`utils/soft_delete.py`, junto al ya existente `utils/security.py`) y el directorio `backend/tests/` que hoy no existe. Todo el trabajo de frontend queda explícitamente fuera.

## Complexity Tracking

> No aplica — la Constitution Check no arrojó violaciones (ver sección correspondiente).
