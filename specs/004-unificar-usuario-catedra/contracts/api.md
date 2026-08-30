# Contratos de API: 004-unificar-usuario-catedra

**Fecha**: 2026-08-16 | Prefijo: `/api/v1`

Solo se documentan los endpoints **nuevos** y los que **cambian de forma**. Los no listados
mantienen su contrato actual. Códigos de error según Principio III: 502 infraestructura,
409 conflicto de estado, 403 permisos.

---

## Identidad y cátedras

### `POST /usuarios/` — cambia

Alta de usuario con sus cátedras en una sola operación (FR-035, FR-036).

```jsonc
// Request
{
  "username": "mgomez",
  "nombre": "M. Gómez",
  "email": "mgomez@utn.edu.ar",       // opcional
  "password": "...",
  "rol": "catedra_admin",
  "catedra_ids": [3, 7, 12]            // reemplaza a catedra_id
}
```

```jsonc
// 201 Created
{
  "id": 42, "username": "mgomez", "nombre": "M. Gómez", "rol": "catedra_admin",
  "catedras": [ {"id": 3, "nombre": "Programación I"}, ... ]   // FR-036c
}
```

| Código | Caso |
|---|---|
| 400 | `catedra_ids` vacío (FR-036b) |
| 409 | Alguna cátedra ya tiene titular (FR-036). **No se crea el usuario**: la operación es atómica |
| 403 | Quien llama no es administrador |

El 409 incluye qué cátedras dejaron de estar disponibles, para que la pantalla pueda rehacer la
búsqueda sin adivinar:

```jsonc
{ "detail": "Cátedras ya asignadas", "catedras_no_disponibles": [{"id": 7, "titular": "J. Pérez"}] }
```

### `GET /catedras/` — cambia

Cada cátedra suma su titular. Parámetro nuevo `?sin_titular=true` para el selector de alta.

```jsonc
[ { "id": 3, "nombre": "Programación I", "activa": true,
    "titular": {"id": 8, "nombre": "J. Pérez"} } ]   // null si no tiene
```

Se eliminan de la respuesta `cuota_vcpus`, `cuota_ram_mb`, `cuota_storage_gb` (FR-010).

### `PATCH /catedras/{id}` — cambia

Acepta `titular_id` (reasignación, FR-007). Deja de aceptar los tres campos de cuota.

| Código | Caso |
|---|---|
| 409 | La cátedra tiene servicios vigentes y se intenta desactivar sin confirmar (`?confirmar=true`) |

### `PATCH /usuarios/{id}` — cambia

Desactivar un usuario con cátedras a cargo devuelve **409** con la lista de cátedras que quedarían
sin responsable (FR-008). El cliente debe reasignarlas o darlas de baja primero.

### `GET /admin/migracion/accesos-perdidos` — nuevo

Bitácora de FR-034. Admin-only. Devuelve quién perdió acceso al pasar a titular único.

---

## Capacidad y aprobación

### `GET /capacidad` — nuevo

Panorama del clúster. Admin-only (Principio VI: no es información del rol cátedra).

```jsonc
{
  "fisica":       {"vcpus": 64, "ram_mb": 262144, "storage_gb": 4096},
  "desplegado":   {"vcpus": 40, "ram_mb": 163840, "storage_gb": 900},
  "reservado":    {"vcpus": 4,  "ram_mb": 8192,   "storage_gb": 40},
  "comprometido": {"vcpus": 44, "ram_mb": 172032, "storage_gb": 940},
  "libre":        {"vcpus": 20, "ram_mb": 90112,  "storage_gb": 3156},
  "ram_en_riesgo_mb": 12288,        // reactivación de los pausados (FR-014c)
  "capacidad_token": "a3f9c1"
}
```

Si Proxmox no responde, **502**. El sistema no inventa una capacidad por defecto: aprobar sin saber
la capacidad real sería exactamente lo que el Principio IV prohíbe.

### `GET /pedidos/{id}/evaluacion` — nuevo

Lo que el administrador necesita para decidir (FR-014). Admin-only.

```jsonc
{
  "pedido": {"id": 91, "tipo": "alta", "catedra": {"id": 3, "nombre": "Programación I"}},
  "costo":            {"vcpus": 2, "ram_mb": 2048, "storage_gb": 8},
  "consumo_catedra":  {"vcpus": 6, "ram_mb": 6144, "storage_gb": 24},
  "capacidad": { /* igual que GET /capacidad */ },
  "libre_si_aprueba": {"vcpus": 18, "ram_mb": 88064, "storage_gb": 3148},
  "excede_capacidad": false,
  "capacidad_token": "a3f9c1"
}
```

### `POST /pedidos/{id}/aprobar` — nuevo

Reemplaza a la transición manual a `APROBADO` vía cambio de estado genérico. Admin-only.

```jsonc
// Request
{
  "capacidad_token": "a3f9c1",
  "justificacion_capacidad": null    // requerido solo si excede (FR-015b)
}
```

Efecto: valida capacidad y **crea la reserva** dentro de la misma transacción, bajo advisory lock
(R2). Fija `reserva_*` y `reserva_expira_at`.

| Código | Caso |
|---|---|
| 409 `token_desactualizado` | La capacidad cambió desde que se mostró. Devuelve la evaluación nueva; el cliente reconfirma (FR-018c) |
| 400 | `excede_capacidad` y falta `justificacion_capacidad` (FR-015b) |
| 409 | El pedido no está en `SOLICITADO` |

Aprobar excediendo la capacidad **no se bloquea** si viene justificación (FR-015).

### `POST /pedidos/{id}/rechazar` — nuevo

Requiere `motivo` (FR-016), visible para la cátedra solicitante.

---

## Servicios: vencimiento, renovación, pausa

### `GET /servicios/` — cambia

Cada servicio suma los campos de la spec y queda alcanzado por el filtro multi-cátedra (R10):

```jsonc
{
  "id": 55, "catedra": {"id": 3, "nombre": "Programación I"},   // rotulado (FR-004)
  "estado": "paused",
  "vence_at": "2026-12-15T00:00:00",
  "exento_pausado": false,
  "pausado_auto_at": "2026-08-10T03:00:00",     // null si no lo pausó el sistema
  "pausa_programada_at": null,
  "almacenamiento_retenido": true               // FR-031
}
```

### `POST /servicios/{id}/reactivar` — nuevo

La cátedra reactiva por sí sola un servicio pausado (FR-024). No requiere pedido ni aprobación.

| Código | Caso |
|---|---|
| 409 `sin_capacidad` | No hay capacidad libre. El servicio **queda en `paused`**, no en error (FR-025). El cuerpo explica cómo escalarlo al administrador |
| 403 | El servicio no pertenece a ninguna cátedra de quien llama |

### `POST /servicios/{id}/renovar` — nuevo

Crea un `Pedido` con `tipo=renovacion` (FR-018i, R11). Lo puede llamar la cátedra dueña.

| Código | Caso |
|---|---|
| 409 | Ya existe una renovación pendiente para ese servicio |

### `PATCH /servicios/{id}` — nuevo

Único campo editable por la cátedra: `exento_pausado` (FR-026). El administrador puede además
ajustar `vence_at`.

### `GET /servicios/pausados` — nuevo

Admin-only (FR-030). Servicios en `paused`, con `pausado_auto_at` y el almacenamiento que retienen,
ordenados por antigüedad, para decidir bajas definitivas.

### `GET /servicios/exentos-inactivos` — nuevo

Admin-only (FR-026). Servicios marcados "siempre encendido" que sin embargo están inactivos — el
contrapeso a que la exención se use de más.

---

## Trabajos periódicos

### `POST /admin/jobs/{nombre}` — nuevo

Admin-only. Ejecuta a demanda el mismo servicio que corre el planificador (R1). Sirve para operar y
depurar sin esperar la cadencia.

`nombre` ∈ `recolectar_metricas` \| `evaluar_inactividad` \| `aplicar_vencimientos` \|
`expirar_reservas`.

```jsonc
// 200 OK
{ "job": "expirar_reservas", "ejecutado_at": "...", "afectados": 3, "detalle": [...] }
```

| Código | Caso |
|---|---|
| 409 | El trabajo ya está corriendo (lock tomado, R1) |

---

## Cambios de comportamiento sin cambio de forma

| Endpoint | Cambio |
|---|---|
| `POST /pedidos/` | Deja de devolver **409 cuota excedida** (FR-009). Acepta `catedra_id` explícito, validado contra las cátedras de quien llama |
| `GET /pedidos/` | Filtra por el conjunto de cátedras, no por una sola (R10) |
| `GET /metricas/*` | Ídem |
| `GET /catedras/mi-catedra` | **Se elimina**: no hay "mi cátedra" en singular. Se reemplaza por `GET /catedras/mias` |
| Historial (pedidos y servicios) | `autor` puede ser `"sistema"` cuando `usuario_id` es `NULL` (R4) |
