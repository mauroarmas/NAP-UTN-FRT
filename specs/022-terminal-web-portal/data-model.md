# Data Model: Terminal web de la consola

Una migración Alembic (`022_01_terminal_identidades`, cabeza anterior `017_01_clave_acceso_servicio`) agrega dos tablas. No se modifican tablas existentes salvo los campos de inventario de consola de `usuarios`, que se actualizan al adoptar la identidad gestionada.

## `identidades_consola` (nueva)

Una fila por persona con identidad de consola gestionada por el portal.

| Campo | Tipo | Notas |
|---|---|---|
| `usuario_id` | FK `usuarios.id`, **unique** | una identidad por persona (FR-008) |
| `identidad` | string(100), **unique** | `nap-u<id>@pve`; nunca `root@pam` ni compartida |
| `password_cifrada` | texto | `{ "password": … }` cifrado con el keyring (contexto `identidad_consola:{usuario_id}`); nunca se expone |
| `estado` | enum | `en_preparacion` · `lista` · `con_error` · `retirada` |
| `pools_aplicados` | JSON (lista) | `catedra-N` con ACL aplicada y confirmada por `probe` |
| `revision` | int | sube con cada convergencia; base de la idempotencia |
| `ultimo_error_seguro` | string(200) | motivo sin secretos; visible para administración |
| `reconciliada_at`, `creada_at`, `actualizada_at` | timestamps | |

**Reglas**: el conjunto *deseado* no se guarda; se calcula (persona activa → cátedras activas que posee; administración → todas las activas → pools). `estado = lista` sólo si `pools_aplicados` ⊇ deseado y el último `probe` coincide. Una identidad manual previa se conserva hasta que la gestionada esté `lista` (R11).

## `sesiones_terminal` (nueva)

Una fila por terminal abierta. **No guarda contenido** (FR-017).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | |
| `usuario_id` | FK | cupo por persona (FR-015) |
| `servicio_id` | FK | una sesión, un servicio |
| `nodo` | string | nodo por el que se abrió (puede diferir del que aloja el contenedor) |
| `abierta_at`, `ultimo_latido_at` | timestamps | cupo = filas sin `cerrada_at` con latido reciente |
| `ultima_entrada_at` | timestamp | base de la inactividad (entrada de la persona) |
| `cierre_solicitado_at`, `motivo_solicitud` | timestamp, string | lo marcan retiro/baja/detención/desactivación |
| `cerrada_at`, `motivo_cierre` | timestamp, string | `inactividad`, `persona`, `retiro`, `baja`, `detencion`, `cuenta`, `reinicio_portal`, `error`, `limite` |
| `duracion_s` | int | al cerrar |

**Índices**: `(usuario_id, cerrada_at)` para el cupo; `(servicio_id, cerrada_at)` para cortes por servicio.

## Estructuras existentes que se usan

| Estructura | Uso |
|---|---|
| `usuarios.identidad_consola`, `inventario_consola*` | se actualizan a la identidad gestionada al adoptar (R11) |
| `cambios_acceso_consola`, `evidencias` (`revocacion_consola`) | el retiro automático crea la evidencia con lo observado y completa el trámite (R5) |
| `eventos_seguridad` | `terminal_abierta`, `terminal_cerrada`, `identidad_consola_*` sin contenido |
| `console_access_profile` (privado) | sigue aportando `cluster_uuid`, `pve_version`, `gate` y `nodos`; **deja de aportar `identities`** |
| `identidades_infraestructura`, `servicios` | confirmación de identidad del servicio y nodo del contenedor |

## Transiciones

- **Identidad**: `en_preparacion` → `lista`; `lista` → `en_preparacion` si cambia lo deseado; cualquiera → `con_error` (reintentable); `lista` → `retirada` al quitar todo (se elimina la cuenta y se conserva la fila para auditoría).
- **Sesión**: abierta → cerrada con un motivo; nunca se reabre.
