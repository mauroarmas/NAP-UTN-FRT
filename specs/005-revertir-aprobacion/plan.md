# Implementation Plan: Revertir una aprobación antes del despliegue

**Branch**: `005-revertir-aprobacion` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-revertir-aprobacion/spec.md`

## Summary

La feature le da al administrador una vía para **deshacer una aprobación antes del despliegue**,
liberando en el acto la capacidad que esa aprobación comprometió, con el motivo registrado y la
cátedra enterada.

El hallazgo que define el enfoque: **el sistema ya sabe hacer exactamente esta operación**.
`capacidad_service.expirar_reservas` libera reservas todos los días —pone los tres campos de reserva
en cero y transiciona el pedido de `APROBADO` a `RECHAZADO`— y la transición ya figura como válida
en la máquina de estados. Lo que falta no es el mecanismo sino **un segundo ejecutor**: hoy esa
transición está en `TRANSICIONES_SISTEMA`, reservada al trabajo periódico, y un administrador que la
intenta recibe un 409.

En consecuencia el plan es acotado: se agrega un endpoint, se habilita a la persona como autor de
una transición que ya existe, y se distingue en el historial la reversión humana del vencimiento
automático. No hay entidades nuevas, no hay migración, y la contabilidad de capacidad no se toca —
se reutiliza tal cual, incluido su bloqueo.

## Technical Context

**Language/Version**: Python 3.12 (backend), JavaScript ES2022 + React 18 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2; React + Vite

**Storage**: PostgreSQL 16 vía SQLAlchemy async. **Sin migración de esquema**: la reserva no es una
tabla sino un estado del pedido (`reservas_vigentes_where`), y los campos que la componen ya existen
desde la feature 004.

**Testing**: pytest con doble de prueba del cliente Proxmox; las pruebas corren sobre SQLite con
`create_all`

**Target Platform**: Linux server en Docker Compose

**Project Type**: Aplicación web (backend FastAPI + SPA React)

**Performance Goals**: No aplica. Una reversión es una corrección de error, no operación rutinaria.

**Constraints**: La liberación de capacidad y el cambio de estado MUST ser indivisibles (FR-004), y
dos reversiones simultáneas MUST NOT liberar la capacidad dos veces (FR-005).

**Scale/Scope**: Un endpoint nuevo, una función de servicio, un ajuste en la máquina de estados y
una acción en la bandeja del administrador.

### Estado del código relevante (verificado el 2026-08-30)

Lo que **ya funciona** y esta feature reutiliza:

| Pieza | Dónde | Estado |
|---|---|---|
| La transición `APROBADO → RECHAZADO` es válida | `pedido_service.TRANSICIONES_VALIDAS` | Existe |
| Liberar una reserva = poner los tres campos en cero | `capacidad_service.expirar_reservas` | Existe |
| El cálculo de capacidad excluye reservas liberadas | `capacidad_service.reservas_vigentes_where` | Existe |
| Bloqueo que serializa decisiones de capacidad | `capacidad_service.BloqueoCapacidad` (advisory lock) | Existe |
| Transición con autor humano y motivo | `pedido_service.cambiar_estado` | Existe |
| Transición con autor sistema | `pedido_service.transicion_del_sistema` | Existe |
| La cátedra ve el estado y el historial de sus pedidos | `routers/pedidos.py` | Existe |

Lo que **falta**:

| Hueco | Dónde | Requisito |
|---|---|---|
| No hay endpoint para revertir | `routers/pedidos.py` | FR-001 |
| `APROBADO → RECHAZADO` está monopolizada por el sistema | `pedido_service.TRANSICIONES_SISTEMA` | FR-001 |
| No se distingue reversión humana de vencimiento automático | historial y `motivo_rechazo` | FR-009 |
| La cátedra no distingue un rechazo original de una reversión | `frontend/src/pages/Pedidos.jsx` | FR-010 |
| No hay acción de revertir en la bandeja del administrador | `frontend/src/pages/Pedidos.jsx` | FR-001 |

## Constitution Check

*GATE: evaluado antes de Phase 0 y reevaluado tras Phase 1.*

Constitución vigente: **v3.0.0**.

| Principio | Evaluación | Veredicto |
|---|---|---|
| **I. Proxmox es el back-end, con una excepción nombrada** | La feature no toca Proxmox: revertir ocurre **antes** de que exista contenedor alguno. No usa la excepción de consola ni la ensancha. | ✅ Sin impacto |
| **II. La máquina de estados es la única fuente de verdad** | Zona sensible. No se agrega ninguna transición: `APROBADO → RECHAZADO` ya es válida. Lo que cambia es **quién puede ejecutarla**, y el principio ya admite tanto persona como sistema como autores. La reversión pasa por la función central; MUST NOT haber asignación directa de `estado`. | ⚠️ Requiere cuidado — ver R1 |
| **III. Toda operación debe ser recuperable** | Es el principio que la feature viene a hacer cumplir: hoy una aprobación compromete recursos reales y no tiene vuelta atrás humana. La cláusula de "capacidad huérfana" se apoya solo en el vencimiento automático, que tarda hasta 24 h. | ✅ Mejora |
| **IV. La capacidad se controla al aprobar** | Se refuerza. El principio exige que sobrecomprometer sea deliberado y nunca accidental; esta feature agrega que además sea **reversible**, que es lo que vuelve honesta la advertencia que el sistema ya muestra. La liberación reutiliza el bloqueo y la definición de reserva vigente existentes. | ✅ Mejora |
| **V. El historial académico no se destruye** | FR-008 y FR-009 lo respetan: la reversión **agrega** una entrada, no reescribe la de la aprobación. | ✅ Cumple |
| **VI. La cátedra pide y observa; el administrador gestiona** | FR-010 y FR-012: la cátedra se entera y entiende, pero no revierte. Aprobar, rechazar y resolver siguen siendo exclusivos del administrador. | ✅ Cumple |
| **Seguridad: operaciones mutantes exigen rol administrador** | La reversión queda tras `require_admin`. | ✅ Cumple |
| **Esquema versionado con Alembic** | No introduce migraciones: la reserva es un estado, no una tabla. | ✅ Sin impacto |

**Compuerta de pruebas**: la constitución exige pruebas automatizadas para todo código que toque
**máquina de estados** o **control de capacidad**, con al menos un camino de fallo, y —para el código
que decide sobre capacidad— **un escenario de concurrencia**.

Esta feature cae de lleno en ambas categorías, y **a diferencia de la 006, acá el escenario de
concurrencia sí corresponde y es obligatorio**: la reversión decide sobre capacidad (libera), no solo
la consume. Dos reversiones simultáneas sobre el mismo pedido podrían liberar dos veces e inflar el
saldo libre — exactamente la clase de defecto que el bloqueo de la feature 004 existe para prevenir,
entrando por una operación nueva. FR-005 y SC-006 lo exigen explícitamente.

**Resultado de la compuerta (pre-Phase 0)**: ✅ **PASA**, con la advertencia registrada sobre el
Principio II, resuelta en R1.

### Reevaluación post-diseño (tras Phase 1)

| Punto | Resultado |
|---|---|
| ¿El diseño agregó transiciones de estado? | No. `APROBADO → RECHAZADO` ya existía; se le suma un ejecutor humano (R1). |
| ¿Hay algún camino que asigne `estado` fuera de la función central? | No. La reversión usa `cambiar_estado`, como aprobar y rechazar. |
| ¿El diseño toca el cálculo de capacidad? | No. Reutiliza `reservas_vigentes_where` y `BloqueoCapacidad` sin modificarlos. |
| ¿Queda algún camino que destruya historial? | No. La reversión agrega una entrada y conserva la de la aprobación (R4). |
| ¿Se puede liberar capacidad dos veces? | No: el bloqueo serializa y la segunda reversión encuentra el pedido fuera de `APROBADO` (R3). |
| ¿Alguna capacidad nueva para el rol cátedra? | No. Solo ve el resultado. |

**Resultado post-diseño**: ✅ **PASA**. La sección Complexity Tracking queda vacía a propósito.

## Project Structure

### Documentation (this feature)

```text
specs/005-revertir-aprobacion/
├── plan.md              # Este archivo
├── research.md          # Phase 0 — decisiones de diseño
├── data-model.md        # Phase 1 — entidades y reglas
├── quickstart.md        # Phase 1 — guía de validación
├── contracts/
│   └── api.md           # Phase 1 — contrato del endpoint
├── checklists/
│   └── requirements.md  # Checklist de calidad de la spec
└── tasks.md             # Phase 2 — lo genera /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   └── pedidos.py                 # POST /pedidos/{id}/revertir-aprobacion
│   ├── schemas/
│   │   └── pedido.py                  # PedidoRevertir (motivo obligatorio)
│   └── services/
│       ├── pedido_service.py          # ejecutor humano de APROBADO → RECHAZADO
│       └── capacidad_service.py       # liberar_reserva() extraída y reutilizada
└── tests/
    ├── test_reversion_aprobacion.py       # nuevo
    └── test_reversion_concurrencia.py     # nuevo — compuerta de capacidad

frontend/
└── src/
    ├── pages/
    │   └── Pedidos.jsx                # acción de revertir; distinguir la reversión
    └── services/
        └── api.js                     # revertirAprobacion
```

**Structure Decision**: se conserva la estructura ya establecida por las features 001–006. La feature
no introduce capas ni carpetas: agrega un endpoint donde ya hay un router, un schema donde ya hay
schemas, y una acción en una página que ya existe.

## Complexity Tracking

No hay violaciones a la constitución que justificar. La sección se deja vacía deliberadamente, según
lo previsto en Governance.
