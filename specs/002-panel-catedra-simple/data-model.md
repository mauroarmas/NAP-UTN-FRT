# Data Model: Panel simple para cátedra

No se agregan entidades persistidas, columnas ni migraciones. Esta spec solo cambia cómo se
presentan entidades ya existentes al rol cátedra. Se documentan acá los mapeos de presentación
(view models de frontend) derivados de `research.md`.

## Pedido (esquema sin cambios)

Fuente: `backend/app/schemas/pedido.py` (`PedidoResponse`).

Campos reutilizados sin modificación: `id`, `template_id`, `estado`, `created_at`, `resolved_at`,
`motivo_rechazo`.

**Mapeo de presentación**: se reutiliza el `ESTADO_CONFIG` (ícono + label + color) ya definido en
`frontend/src/pages/Pedidos.jsx` para los 8 estados de `EstadoPedido`. No se introduce vocabulario
nuevo para pedidos — la cátedra ya podía leer estos labels; solo cambia dónde y con cuánto
protagonismo se muestran (pantalla principal en vez de una tabla secundaria).

## Servicio (esquema sin cambios)

Fuente: `backend/app/schemas/servicio.py` (`ServicioResponse`).

Campos reutilizados sin modificación: `id`, `estado`, `hostname`, `vcpus_asignados`,
`ram_asignada_mb`, `disk_asignado_gb`.

**Mapeo de presentación nuevo** (solo frontend, solo para la vista de cátedra; no reemplaza el
`ESTADO_CONFIG` de 4 estados que sigue usando `Servicios.jsx`):

| `estado` (`EstadoServicio`) | Categoría mostrada a la cátedra |
|---|---|
| `running` | Activo |
| `stopped` | Apagado |
| `paused` | Apagado |
| `error` | Con problemas |

## Catedra / CatedraConUso (esquema sin cambios)

Fuente: `backend/app/schemas/catedra.py` (`CatedraConUso`), poblado por
`GET /catedras/{id}` en `backend/app/routers/catedras.py`.

Campos reutilizados sin modificación: `cuota_vcpus`, `cuota_ram_mb`, `cuota_storage_gb`,
`vcpus_en_uso`, `ram_en_uso_mb`, `storage_en_uso_gb`, `servicios_activos`.

**Mapeo de presentación**: se muestran como proporción uso/cuota por recurso (por ejemplo, "2 de 4
vCPUs en uso"), sin exponer el nodo físico ni datos de otras cátedras — ese cálculo ya lo hace el
backend excluyendo lo dado de baja (Principio V de la constitución), el frontend solo lo presenta.

## State transitions

No aplica. Esta spec no introduce ni modifica transiciones de la máquina de estados de `Pedido` ni
de `Servicio` — la única fuente de verdad sigue siendo `cambiar_estado` en `pedido_service.py`
(Principio II de la constitución, sin cambios).
