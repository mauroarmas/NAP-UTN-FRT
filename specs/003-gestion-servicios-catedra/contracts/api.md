# Contratos: Gestión de servicios para cátedra

## Endpoints modificados

### `POST /api/v1/servicios/{servicio_id}/start`

- **Antes**: `Depends(require_admin)`.
- **Ahora**: `Depends(get_current_user)` + chequeo de propiedad inline, igual al patrón ya usado en
  `GET /servicios/{id}` y `GET /servicios/{id}/status`: admin pasa siempre; cátedra pasa solo si
  `servicio.catedra_id == current_user.catedra_id`, si no → `403`.
- **Sin cambios**: precondición de estado (`stopped` → `409` si no), response body
  (`ServicioResponse`), manejo de error de infraestructura (`502`).

### `POST /api/v1/servicios/{servicio_id}/stop`

- Mismo cambio de permisos que `start`. Sin cambios en el resto del contrato.

## Endpoints nuevos

### `POST /api/v1/servicios/{servicio_id}/restart`

- **Auth**: `Depends(get_current_user)` + mismo chequeo de propiedad que `start`/`stop`.
- **Precondición**: `servicio.estado == RUNNING`; si no, `409` con el estado actual en el mensaje
  (mismo estilo que `iniciar_servicio`/`detener_servicio`).
- **Comportamiento**: llama a `reboot_lxc(node, vmid)` (R1 en `research.md`); no cambia
  `servicio.estado` en la base porque el servicio permanece `RUNNING` antes y después (el reinicio
  lo gestiona Proxmox internamente).
- **Response**: `ServicioResponse`, `200`.
- **Errores**: `404` servicio inexistente/dado de baja · `403` sin permisos · `409` no está en
  ejecución · `502` fallo de infraestructura al reiniciar.

### `POST /api/v1/servicios/{servicio_id}/console-ticket`

- **Auth**: `Depends(get_current_user)` + mismo chequeo de propiedad.
- **Precondición**: `servicio.estado == RUNNING`; si no, `409` (FR-008).
- **Comportamiento**: llama a `abrir_termproxy(node, vmid)` contra Proxmox (R3) y emite un ticket
  propio del portal, de un solo uso y vida corta, atado a `servicio_id` + `usuario_id` (R4). No
  persiste nada en base.
- **Response**: `{ "ticket": str, "expira_en_segundos": int }`, `200`.
- **Errores**: `404` · `403` · `409` (no está en ejecución) · `502` (Proxmox no pudo emitir el
  ticket de consola).

### `WS /api/v1/servicios/{servicio_id}/console`

- **Auth**: query param `ticket` — el emitido por `console-ticket` de este mismo servicio, validado
  contra `servicio_id` + `usuario_id` + no vencido + no usado antes (R4). Sin ticket válido, el
  backend cierra la conexión inmediatamente con el código de error correspondiente.
- **Comportamiento**: al aceptar la conexión, el backend abre su propia conexión saliente al
  `vncwebsocket` de Proxmox usando el ticket obtenido de `termproxy` (R2/R3/R5), y relay bytes en
  ambas direcciones mientras ambas conexiones (navegador↔backend, backend↔Proxmox) sigan vivas.
- **Cierre**: al desconectarse el navegador (cierre de pestaña, navegación, logout — FR-009), el
  backend cierra también su conexión saliente hacia Proxmox. No hay reconexión automática — reabrir
  la consola implica pedir un ticket nuevo.

## Fuera de alcance

No se documentan contratos para `Pedido` — esta spec no los toca. No hay contrato de "listar
sesiones de consola activas" — no se persisten, no hay qué listar (ver `data-model.md`).
