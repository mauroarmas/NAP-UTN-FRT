# Data Model: Gestión de servicios para cátedra

No se agregan tablas ni columnas. Esta spec extiende comportamiento sobre `Servicio`, que ya
existe, y define una estructura efímera (no persistida) para las sesiones de consola.

## Servicio (esquema sin cambios)

Fuente: `backend/app/models/servicio.py` (`EstadoServicio`, `Servicio`).

Campos reutilizados sin modificación: `id`, `catedra_id`, `proxmox_vmid`, `proxmox_node`,
`hostname`, `estado`.

**Transiciones que esta spec habilita para el rol cátedra** (mismas transiciones que ya ejecuta el
administrador; ninguna transición nueva a nivel de modelo):

| Acción | Precondición (`estado` actual) | `estado` resultante | Quién podía hacerlo antes | Quién puede hacerlo ahora |
|---|---|---|---|---|
| Encender | `stopped` | `running` | Solo admin | Cátedra (propio) + admin (cualquiera) |
| Apagar | `running` | `stopped` | Solo admin | Cátedra (propio) + admin (cualquiera) |
| Reiniciar | `running` | `running` (vía Proxmox `reboot`, sin estado intermedio persistido) | Nadie — no existía | Cátedra (propio) + admin (cualquiera) |

`paused` y `error` quedan fuera de esta spec: ni hoy ni con este cambio hay una acción definida
para esos dos estados (limitación heredada, no introducida acá).

## Sesión de consola (efímera, no persistida)

No es una entidad de negocio ni una tabla. Existe solo mientras dura la conexión WebSocket activa
entre el navegador y el backend. Forma conceptual, usada únicamente en memoria/en tránsito:

| Campo | Origen | Vida |
|---|---|---|
| `servicio_id` | Parámetro de ruta | Duración de la conexión |
| `ticket` (del portal) | Emitido por `POST /servicios/{id}/console-ticket` | Un solo uso, corta duración (ver `contracts/`) |
| `ticket`, `port` (de Proxmox) | Respuesta de `termproxy` (R3 en `research.md`) | Duración de la conexión saliente del backend hacia Proxmox |

No se persiste ningún registro de que una consola fue abierta (ni éxito ni error) — la constitución
no exige trazabilidad de acciones (ver Assumptions en `spec.md`) y esta feature no la introduce.

## State transitions

No aplica a `Pedido` — esta spec no lo toca. Las transiciones de `Servicio.estado` descritas arriba
siguen sin pasar por una función central de transición (a diferencia de `Pedido`), consistente con
cómo el código ya trata a `Servicio` hoy (ver Constitution Check, Principio II, en `plan.md`).
