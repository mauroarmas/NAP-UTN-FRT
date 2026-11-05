# Contrato: runner `nap-iaas-access/1` (delta)

Se mantiene el protocolo y su validación cerrada. Cambio **sólo** en `configure`.

## Solicitud

Campo **opcional** nuevo en `configure`:

| Campo | Tipo | Regla |
|---|---|---|
| `password_consola` | string | `^[A-Za-z0-9_-]{32,128}$`. Viaja sólo por stdin; nunca en `argv` ni se registra. |

- Ausente: el runner no modifica contraseñas (comportamiento actual).
- Presente en `probe`: se rechaza (`INVALID_REQUEST`); `probe` no cambia.
- Un nodo sin esta versión rechaza el campo con `INVALID_REQUEST`.

## Efecto (con `password_consola`)

1. Si `nap` está sin contraseña válida (`*`/`!`) → se fija con `chpasswd` (stdin). Resultado `consola: "aplicada"`.
2. Si el hash de `nap` ya corresponde a la contraseña recibida → sin cambios, `consola: "sin_cambios"`.
3. Si es otro hash → no se pisa, `consola: "conservada"`.
4. `root` queda con `*` en todos los casos.
5. Verificación: `nap` con contraseña válida, `root` bloqueado, `sshd -T` con `passwordauthentication no`, `permitrootlogin no`.

## Respuesta

`result` agrega `consola` (`aplicada` | `sin_cambios` | `conservada`) cuando se envió la contraseña. Nunca incluye la contraseña, su hash ni texto del sistema. Errores sólo con códigos existentes (`PROBE_FAILED`, `UNCONFIRMED`, …; un fallo al fijar la contraseña queda `unconfirmed` y se reintenta); un efecto posible sin confirmar queda `unconfirmed` (reintentable).
