# Phase 1 — Data Model

**Feature**: `001-pedido-soft-delete-retry`

Cambios sobre el esquema existente. Solo se agregan columnas nullable: no hay cambios destructivos ni backfill obligatorio.

---

## Pedido (`pedidos`)

### Columnas nuevas

| Columna | Tipo | Nullable | Default | Propósito |
|---------|------|----------|---------|-----------|
| `deleted_at` | `DateTime` | sí | `NULL` | Marca de baja lógica. `NULL` = vigente. (FR-007, FR-008) |
| `vmid_reservado` | `String(10)` | sí | `NULL` | VMID obtenido del clúster antes de intentar crear el contenedor. Sobrevive al fallo y habilita la reutilización en el reintento. (FR-004, ver [research.md](./research.md) R1) |

### Reglas de validación

- `deleted_at` se escribe **solo** vía la operación de baja; nunca se limpia (no hay "restaurar" en este hito).
- Un `Pedido` con `deleted_at != NULL` no aparece en listados ni en el detalle por ID (responde 404). (FR-009)
- La baja se **rechaza** si existe un `Servicio` asociado vigente (`servicio.deleted_at IS NULL`). (FR-014)
- `vmid_reservado` es informativo/operativo: no es una clave foránea ni tiene restricción de unicidad, porque el VMID puede ser liberado y reasignado por Proxmox fuera de nuestro control.

### Transiciones de estado

`TRANSICIONES_VALIDAS` **no cambia**. La transición `ERROR → EN_DESPLIEGUE` ya existe y ahora efectivamente dispara el despliegue real desde el nuevo punto de entrada de reintento. (Ver [research.md](./research.md) R5)

```text
SOLICITADO ──> EN_REVISION ──> APROBADO ──> EN_DESPLIEGUE ──> ACTIVO ──> SUSPENDIDO
     │              │                             │                          │
     └──> RECHAZADO <┘                            └──> ERROR ────────────────┐│
                     ^                                   │                   ││
                     └───────────────────────────────────┘                   ││
                                                          reintento ─────────┘│
                                                          (ERROR → EN_DESPLIEGUE
                                                           ahora sí ejecuta Proxmox)
                                            ACTIVO <───────────────────────────┘
```

La baja lógica es **ortogonal** al estado: un pedido puede darse de baja en cualquier estado (FR-013) y su `estado` conserva el último valor alcanzado.

---

## Servicio (`servicios`)

### Columnas nuevas

| Columna | Tipo | Nullable | Default | Propósito |
|---------|------|----------|---------|-----------|
| `deleted_at` | `DateTime` | sí | `NULL` | Marca de baja lógica. `NULL` = vigente. (FR-007, FR-008) |

### Reglas de validación

- Al dar de baja: **primero** se libera el contenedor en Proxmox, y solo si tiene éxito se escribe `deleted_at`. Si Proxmox falla, se propaga el error y la columna queda en `NULL`. (FR-010, ver [research.md](./research.md) R7)
- Un `Servicio` sin `proxmox_vmid` (nunca desplegado realmente) puede darse de baja sin llamar a Proxmox.
- Un `Servicio` con `deleted_at != NULL` **no cuenta** para `verificar_cuota` ni para el uso de recursos por cátedra. (FR-012)
- Un `Servicio` con `deleted_at != NULL` queda excluido de la captura periódica de métricas.
- Dar de baja algo ya dado de baja es idempotente: no falla, informa que ya estaba dado de baja.

---

## PedidoHistorial (`pedidos_historial`)

**Sin cambios de esquema.** Se usa tal cual está para satisfacer FR-005: cada intento de despliegue (inicial y reintentos) agrega una fila con su `estado_anterior`, `estado_nuevo`, `comentario` (que incluye el detalle del error de Proxmox truncado) y `usuario_id`.

Se **preserva** el historial de los pedidos dados de baja: nunca se borra ni se filtra por `deleted_at` del pedido padre cuando se consulta el historial de auditoría. (FR-011)

---

## Migración Alembic

Una sola revisión, con `down_revision = 'ce2e9b4b4077'`:

**Upgrade**:
- `ALTER TABLE pedidos ADD COLUMN deleted_at TIMESTAMP NULL`
- `ALTER TABLE pedidos ADD COLUMN vmid_reservado VARCHAR(10) NULL`
- `ALTER TABLE servicios ADD COLUMN deleted_at TIMESTAMP NULL`
- Índices parciales recomendados sobre `deleted_at` en ambas tablas para no degradar los listados: `CREATE INDEX ... ON pedidos (deleted_at) WHERE deleted_at IS NULL` (equivalente para `servicios`).

**Downgrade**: eliminar las tres columnas y los índices.

**Backfill**: no requerido. Todas las filas existentes quedan con `deleted_at = NULL`, que es exactamente el estado "vigente" — el comportamiento observable no cambia para los datos actuales.

---

## Consultas afectadas

El inventario completo de sitios que deben incorporar el filtro está en [research.md](./research.md) R4. Resumen: 3 listados (`pedidos`, `servicios`, métricas), 4 accesos por ID que deben responder 404, y 3 cálculos de consumo/cuota (`catedras`, `pedido_service.verificar_cuota`, `metricas_service`).
