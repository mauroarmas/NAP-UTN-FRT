# Data Model: Usuario no root en la consola

No hay tablas ni columnas nuevas ni migración. Se reutilizan estructuras existentes y se agregan claves a campos JSON.

## Estructuras existentes que se usan

| Estructura | Campo | Uso |
|---|---|---|
| `servicios` | `credenciales_encrypted` | `{ "guest_password": … }` cifrado (`servicio:{id}:secretos`): pasa a ser la contraseña de `nap`. En una actualización se reemplaza al confirmarse. |
| `servicios` | `acceso_metadata.username` | `nap` cuando el cambio se aplicó; `root` mientras no. |
| `servicios` | `acceso_metadata.consola` (nueva clave) | `{ "usuario": "nap", "aplicado_at": <instante> }`; sólo presencia/fecha, nunca el valor. |
| `operaciones_infraestructura` | `contexto_seguro.acceso_consola` (nueva clave) | `{ "password_cifrada": <cifrado con contexto operacion:{id}:consola> }` en una actualización; se elimina al promoverse. |
| `claves_acceso_servicio` | `revision`, `aplicada_revision` | sin cambios; `configure` sigue idempotente por revisión. |
| `eventos_seguridad` | `accion = revelar_acceso_servicio` | sin cambios; sin el valor revelado. |
| `servicios_historial` | comentario de la operación | «Acceso de consola actualizado: se entra como `nap`». |

## Reglas

- La contraseña pendiente se cifra **antes** de enviarla al nodo y sólo se promueve a credencial del servicio con la confirmación.
- `acceso_metadata.username` y `acceso_metadata.consola` cambian en la misma transacción que la credencial.
- Un servicio sin fila de clave SSH no admite la actualización (409).

## Transiciones

Sin estados nuevos. La operación sigue `pendiente` → `en_curso` → `confirmada`/`fallida`/`incierta`, con reintento por la misma contraseña.
