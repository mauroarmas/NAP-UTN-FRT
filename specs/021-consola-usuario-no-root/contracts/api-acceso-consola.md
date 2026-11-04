# Contrato: actualizar el acceso de consola de un servicio

`POST /servicios/{servicio_id}/acceso-consola` — sólo administración; cabeceras CSRF/Origin como el resto y `Idempotency-Key` obligatoria. Sin cuerpo.

## Comprobaciones

1. Servicio vigente y Linux IaaS (409 `servicio_no_linux`).
2. Servicio encendido (409 `servicio_detenido`), sin operación abierta (409 `operacion_en_curso`).
3. Servicio con identidad y asignación regularizadas (409 `asignacion_sin_regularizar`).
4. Servicio con clave SSH registrada (409 `sin_clave`): sin ella `configure` no puede ejecutarse.
5. Si ya está actualizado (usuario `nap` aplicado): 200 `sin_cambios`, sin operación nueva.

## Respuesta

- `202` con la operación `reparar` (`operation_id`, `Location`), `estado: pendiente`, como la operación de clave SSH. Nunca incluye contraseñas.
- Errores como arriba; `403` para quien no es administración.

## Efecto

Operación `reparar` con marca `acceso_consola`: contraseña nueva cifrada en el contexto de la operación → `configure` con `password_consola` → con confirmación, promoción a credencial del servicio, `acceso_metadata.username = "nap"`, historial y auditoría. Falla o incierta: el servicio conserva el estado anterior coherente.

## Acceso (sin cambios de ruta)

`GET /servicios/{id}/acceso` agrega `consola_usuario` (`nap` | `root`) para que la UI indique con qué usuario entrar. «Revelar acceso inicial» devuelve ese usuario y su contraseña como hoy.
