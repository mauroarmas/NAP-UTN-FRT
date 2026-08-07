# Phase 1 — API Contract

**Feature**: `001-pedido-soft-delete-retry`
**Base**: `/api/v1`

Todos los endpoints requieren JWT (`Authorization: Bearer <token>`). Los marcados **admin** exigen rol `admin` y devuelven `403` en caso contrario, consistente con `require_admin` ya existente.

---

## Endpoints nuevos

### `POST /pedidos/{pedido_id}/reintentar` — admin

Reintenta el despliegue de un pedido que quedó en estado `error`. (FR-001, FR-002, FR-003, FR-006)

**Request body** (opcional, mismo shape que `DesplegarRequest`):

```json
{
  "node": "pve1",
  "storage": "local-lvm"
}
```

Ambos campos opcionales: si se omite `node`, se elige automáticamente el nodo online con menos carga de CPU (comportamiento idéntico al despliegue original).

**Responses**:

| Código | Cuerpo | Cuándo |
|--------|--------|--------|
| `200` | `ServicioResponse` | Reintento exitoso: pedido queda en `activo`, servicio desplegado o adoptado |
| `403` | `{"detail": "Se requieren permisos de administrador"}` | Usuario sin rol admin |
| `404` | `{"detail": "Pedido no encontrado"}` | No existe, o está dado de baja |
| `409` | `{"detail": "Solo se pueden reintentar pedidos en estado ERROR. Estado actual: <estado>"}` | El pedido no está en `error` (FR-002) |
| `502` | `{"detail": "Error al crear recurso en Proxmox: <detalle>"}` | Falló de nuevo: el pedido vuelve a `error` con una nueva entrada de historial |

**Comportamiento del VMID** (FR-004, [research.md](./research.md) R2):

| Situación del `vmid_reservado` | Acción |
|--------------------------------|--------|
| No hay reserva previa | Se pide un VMID nuevo al clúster |
| Reservado y libre en el clúster | Se reutiliza |
| Reservado, ocupado, hostname coincide con `cat{catedra_id}-svc{pedido_id}` | Se **adopta** el contenedor existente (no se crea uno nuevo) |
| Reservado, ocupado, hostname distinto | Se descarta la reserva y se pide un VMID nuevo |

**Efecto sobre el historial**: cada invocación agrega al menos una entrada a `pedidos_historial` (`error → en_despliegue`) y una segunda al resolverse (`en_despliegue → activo` o `en_despliegue → error` con el motivo). (FR-005)

---

### `DELETE /pedidos/{pedido_id}` — admin

Da de baja lógicamente un pedido, en cualquier estado. (FR-013, FR-014, FR-015)

**Responses**:

| Código | Cuerpo | Cuándo |
|--------|--------|--------|
| `200` | `{"message": "Pedido <id> dado de baja", "deleted_at": "<timestamp>"}` | Baja exitosa |
| `200` | `{"message": "El pedido <id> ya estaba dado de baja", "deleted_at": "<timestamp original>"}` | Idempotente: ya estaba dado de baja |
| `403` | `{"detail": "Se requieren permisos de administrador"}` | Usuario sin rol admin |
| `404` | `{"detail": "Pedido no encontrado"}` | No existe |
| `409` | `{"detail": "El pedido tiene un servicio vigente (id=<n>). Dé de baja el servicio primero para liberar el recurso."}` | Tiene `Servicio` asociado no dado de baja (FR-014) |

No ejecuta ninguna operación contra Proxmox.

---

## Endpoints modificados

### `DELETE /servicios/{servicio_id}` — admin

**Cambio de comportamiento**: pasa de borrado físico (`db.delete()`) a baja lógica. La liberación del contenedor en Proxmox se mantiene idéntica y **precede** al marcado. (FR-010)

**Responses**:

| Código | Cuerpo | Cuándo |
|--------|--------|--------|
| `200` | `{"message": "Servicio <id> dado de baja correctamente", "vmid": "<vmid>", "deleted_at": "<timestamp>"}` | Contenedor liberado y registro marcado |
| `200` | `{"message": "El servicio <id> ya estaba dado de baja", "deleted_at": "<timestamp original>"}` | Idempotente |
| `404` | `{"detail": "Servicio no encontrado"}` | No existe |
| `502` | `{"detail": "Error al eliminar en Proxmox: <detalle>"}` | Falló la liberación: el registro **no** se marca |

**Nota de compatibilidad**: el código de estado y la forma general de la respuesta se preservan; cambia el texto del mensaje y se agrega `deleted_at`. Un consumidor que solo verifique `200` no se rompe.

---

### Listados y detalle — filtro por defecto

Los siguientes endpoints excluyen registros dados de baja, sin cambios en su firma ni en su forma de respuesta (FR-009):

| Endpoint | Cambio |
|----------|--------|
| `GET /pedidos/` | Excluye pedidos con `deleted_at` |
| `GET /pedidos/{id}` | `404` si está dado de baja |
| `GET /servicios/` | Excluye servicios con `deleted_at` |
| `GET /servicios/{id}` | `404` si está dado de baja |
| `GET /servicios/{id}/status` | `404` si está dado de baja |
| `GET /catedras/{id}` | El uso de recursos informado excluye servicios dados de baja (FR-012) |
| `GET /metricas/*` | Excluye servicios dados de baja |

`POST /pedidos/` (crear) tampoco computa servicios dados de baja al validar cuota, vía `verificar_cuota`. (FR-012)

---

## Cambios en schemas de respuesta

| Schema | Campo agregado | Tipo |
|--------|----------------|------|
| `PedidoResponse` | `deleted_at` | `datetime \| None` |
| `PedidoResponse` | `vmid_reservado` | `str \| None` |
| `ServicioResponse` | `deleted_at` | `datetime \| None` |

Son campos aditivos y nullable: no rompen a los consumidores actuales del frontend. En los listados por defecto siempre llegarán en `null`, ya que los dados de baja se excluyen; su utilidad es para la vía de consulta histórica.

---

## Fuera de alcance de este contrato

- Endpoint dedicado de consulta histórica con filtros (queda para el hito de Trazabilidad y Logs de Auditoría). Este hito solo garantiza que los datos **permanecen** consultables (FR-011).
- Operación de restauración (deshacer una baja).
- Cualquier cambio en el frontend.
