# Contratos: Panel simple para cátedra

Esta spec **no agrega ni modifica endpoints**. Ver `research.md` (R1) para el razonamiento. Se
documentan acá, como contrato de referencia para la fase de tasks, los endpoints ya existentes de
los que depende la nueva pantalla principal de cátedra — su forma actual no cambia.

## `GET /api/v1/pedidos/`

- **Auth**: requerida. Cátedra ve solo los suyos (filtrado server-side por `catedra_id`); admin ve
  todos.
- **Query params usados por esta feature**: `estado` (opcional) para acotar a pedidos recientes o
  en estados que requieren atención de la cátedra.
- **Response**: `list[PedidoResponse]` — sin cambios (`backend/app/schemas/pedido.py`).

## `GET /api/v1/servicios/`

- **Auth**: requerida. Cátedra ve solo los suyos (filtrado server-side por `catedra_id`).
- **Response**: `list[ServicioResponse]` — sin cambios (`backend/app/schemas/servicio.py`).

## `GET /api/v1/catedras/{catedra_id}`

- **Auth**: requerida. 403 si `catedra_id` no es la propia y el usuario no es admin.
- **Response**: `CatedraConUso` — incluye `cuota_vcpus`, `cuota_ram_mb`, `cuota_storage_gb`,
  `vcpus_en_uso`, `ram_en_uso_mb`, `storage_en_uso_gb`, `servicios_activos` (sin cambios,
  `backend/app/schemas/catedra.py`).
- **Uso nuevo en esta feature**: la cátedra consulta su propio `catedra_id` (disponible en el
  usuario autenticado, `user.catedra_id`) para mostrar el resumen de cuota en la pantalla
  principal.

## `GET /api/v1/templates/`

- **Auth**: requerida.
- **Response**: catálogo de templates disponibles — sin cambios. Ya es la fuente que usa el
  formulario de "Nuevo Pedido" reutilizado (ver `research.md` R2).

## `POST /api/v1/pedidos/`

- **Auth**: requerida.
- **Request**: `PedidoCreate` — `{ template_id: int, parametros_extra?: dict }`. Sin campos de
  infraestructura (sin cambios).
- **Response**: `PedidoResponse`, `201`.
- **Uso en esta feature**: mismo llamado que ya usa `Pedidos.jsx`, invocado desde el acceso directo
  de la nueva pantalla principal de cátedra.

## Fuera de alcance

No se documentan contratos nuevos porque no se crean. Si una futura iteración decide agregar un
endpoint de resumen agregado (descartado en `research.md` R1 por alcance), le corresponderá su
propia spec y su propio contrato.
