# Data Model: Revertir una aprobación antes del despliegue

**Feature**: 005-revertir-aprobacion | **Fecha**: 2026-08-30

> **Esta feature no requiere migración de esquema, ni campos, ni estados nuevos.** Todo lo que
> necesita ya existe. Lo que cambia es **quién puede ejecutar** una transición que ya es válida, y
> cómo se lee el resultado. Este documento describe esas reglas.

---

## Por qué no hace falta nada nuevo

La reserva de capacidad **no es una tabla**. Es un estado derivado del propio pedido, definido en
`capacidad_service.reservas_vigentes_where`:

```text
reserva vigente  ⇔  estado = APROBADO
                 ∧  tipo = ALTA
                 ∧  no tiene servicio
                 ∧  deleted_at es nulo
                 ∧  (reserva_expira_at es nulo  ∨  reserva_expira_at > ahora)
```

De ahí se sigue lo esencial de esta feature: **liberar una reserva es dejar de cumplir esa
condición**. No hay fila que borrar ni saldo que recalcular; el cómputo de capacidad deja de contarla
por sí solo. Esa es la razón por la que revertir sale tan barato — el trabajo lo hizo la feature 004
al elegir este modelo.

---

## Entidades afectadas

### Pedido

Sin cambios estructurales. Cambia qué operaciones lo alcanzan.

| Campo | Rol en esta feature |
|---|---|
| `estado` | Solo `APROBADO` es reversible. Pasa a `RECHAZADO`. |
| `reserva_vcpus`, `reserva_ram_mb`, `reserva_disk_gb` | Se ponen en cero al revertir |
| `reserva_expira_at` | Se limpia: ya no hay reserva que pueda vencer |
| `motivo_rechazo` | Recibe un texto que nombra la reversión, para que la cátedra no lea "rechazado" a secas |
| `justificacion_capacidad` | **No se toca**: es parte del registro de la aprobación que se está deshaciendo, y borrarlo perdería la mitad de la historia |

**Reglas**:

- **P1** — Solo un pedido en `APROBADO` puede revertirse. Desde cualquier otro estado la operación se
  rechaza con un conflicto que nombra la vía correcta.
- **P2** — La reversión exige motivo no vacío. Sin él, no se toca ni el pedido ni la capacidad.
- **P3** — La liberación de la reserva y el cambio de estado son **indivisibles**: ocurren dentro del
  mismo bloqueo de capacidad y la misma transacción.
- **P4** — La reversión es exclusiva del rol administrador.
- **P5** — Revertir la aprobación de una renovación no altera el servicio renovado. Sale gratis: una
  renovación reserva cero y `vence_at` no se mueve hasta que la renovación se **ejecuta**.
- **P6** — Un pedido revertido **no** bloquea pedidos nuevos por el mismo recurso.

**Transiciones** (ninguna es nueva):

```text
                  aprobar
   SOLICITADO ──────────────▶ APROBADO ──── desplegar ───▶ EN_DESPLIEGUE ──▶ ACTIVO
        │                        │                              │
        │ rechazar               │ ┌────────────────────────┐   └──▶ ERROR ──▶ (reintento)
        ▼                        │ │  revertir  (persona)   │
    RECHAZADO ◀──────────────────┴─┤  vencimiento (sistema) │
                                   └────────────────────────┘
```

La flecha `APROBADO → RECHAZADO` **ya existía**: la usaba el vencimiento automático. Esta feature le
agrega un segundo ejecutor, humano. `EN_DESPLIEGUE`, `ACTIVO` y `ERROR` no son reversibles (R5).

---

### PedidoHistorial

Sin cambios estructurales. Es donde vive la distinción que pide FR-009.

| Situación | `usuario_id` | `estado_anterior` | Cómo se reconoce |
|---|---|---|---|
| Rechazo original | persona | `solicitado` | Estado anterior |
| **Reversión de aprobación** | **persona** | **`aprobado`** | Estado anterior **y** autor |
| Vencimiento de reserva | **nulo** (sistema) | `aprobado` | Autor |

**Reglas**:

- **H1** — La reversión agrega una entrada; **nunca** modifica ni borra la de la aprobación original.
  Leídas en orden, las dos cuentan la historia completa: se aprobó, y después se deshizo.
- **H2** — El autor de la reversión es la persona que la ejecutó. MUST NOT registrarse como sistema,
  aunque la operación se parezca al vencimiento automático.
- **H3** — El motivo que escribió el administrador queda en el comentario de la entrada.

---

### Servicio

**No participa.** Revertir ocurre antes de que exista servicio alguno: si hubiera uno, el pedido no
estaría en `APROBADO`. Por eso la feature no toca Proxmox y no puede dejar recursos huérfanos.

---

## Invariantes que la feature debe preservar

| # | Invariante | Por qué |
|---|---|---|
| I1 | Ninguna secuencia de reversiones libera la misma reserva dos veces | Principio IV; SC-006 |
| I2 | Un pedido revertido nunca queda con reserva distinta de cero | Sería capacidad huérfana (Principio III) |
| I3 | Nunca hay capacidad liberada sobre un pedido que sigue en `APROBADO` | La mitad opuesta de I2 |
| I4 | La entrada de la aprobación original sobrevive a la reversión | Principio V |
| I5 | El estado se cambia siempre por la función central de transición | Principio II |

---

## Qué NO cambia

- No hay migraciones de Alembic.
- No se agregan tablas, columnas ni estados.
- No se agregan transiciones a la máquina de estados.
- No se modifica el cálculo de capacidad: se reutiliza `reservas_vigentes_where` tal cual.
- No cambian los permisos de ningún rol existente.
- `PATCH /pedidos/{id}/estado` sigue rechazando `APROBADO → RECHAZADO`: la reversión es una
  operación con nombre propio, no un cambio de estado a mano (R1).
