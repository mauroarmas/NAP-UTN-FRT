# Research: Usuario no root en la consola de Linux IaaS

Fuentes: `backend/app/services/orquestacion_service.py`, `iaas_acceso_service.py`, `service_access_service.py`, `infra/runner/iaas_access.py`, `backend/app/schemas/iaas_access.py` y la 017 (`specs/017-acceso-ssh-iaas-linux/research.md`, R4).

## R1. Estado actual del acceso inicial (hechos)

- Al **crear** un IaaS, la operación genera `guest_password` (`secrets.token_urlsafe(32)`), lo guarda cifrado en `contexto_seguro.credenciales_iaas` y lo envía a Proxmox como parámetro `password` del contenedor: eso fija la contraseña de **`root`**.
- Creado el servicio, el valor se copia cifrado a `servicios.credenciales_encrypted`. `acceso_metadata.username` es `root`, y «Revelar acceso inicial» devuelve ese usuario y `guest_password`.
- La 017 corre `configure` del runner después de crear: usuario `nap`, `usermod -p '*'` (sin contraseña), clave SSH, `sudo` sin contraseña y `sshd` sin contraseñas ni `root`.
- El bootstrap `infra/services/linux/bootstrap.py` (usuario `napadmin`) pertenece a otro producto (no es el camino de IaaS) y no se modifica.

## R2. Reutilizar el secreto y el canal existentes

- **Decisión**: la contraseña de `nap` es el mismo `guest_password`; `configure` la recibe en un campo opcional `password_consola` y la aplica por stdin. El portal deja de enviar `password` a Proxmox al crear, de modo que `root` nace sin contraseña utilizable.
- **Razón**: no hay secreto nuevo que guardar ni canal nuevo; mantiene un único lugar cifrado (`credenciales_encrypted`) y la revelación y su auditoría actuales sirven sin cambios.
- **Alternativas**: contraseña elegida por la persona (más fricción, fuera de la spec); tabla nueva de credenciales (migración sin necesidad); mantener `password` hacia Proxmox y bloquear `root` después (deja una ventana con `root` utilizable y exige un paso más).

## R3. Idempotencia del runner

- **Decisión**: dentro del contenedor, con el hash de `nap` leído de `getent shadow` (nunca registrado): si está bloqueado (`*`/`!`) → `chpasswd` y resultado `aplicada`; si ya corresponde a la contraseña recibida → `sin_cambios`; si es otro hash (la persona lo cambió) → no se pisa y se informa `conservada`. `root` se deja con `*` siempre que se envíe `password_consola`.
- **Razón**: repetir la operación no invalida una contraseña ya entregada (SC-004) y no pisa un cambio legítimo de la persona. Comparar hashes se hace en el contenedor (`mkpasswd`/`crypt` con la sal existente) sin sacar el secreto.
- **Riesgo conocido**: si la persona cambió su contraseña, el valor que muestra el portal ya no coincide; el portal lo trata como acceso *inicial*, no como un secreto vigente. Se documenta en el runbook.

## R4. Sin romper el motor Docker ni nodos viejos

- **Hecho**: `iaas_access.py` y su esquema no entran en el `policy_digest` (17/R4). Se añade una prueba que fija el valor actual.
- **Decisión de protocolo**: se mantiene `nap-iaas-access/1` y el campo nuevo es **opcional** en `configure`; sin él, el runner no toca ninguna contraseña (comportamiento actual). Un nodo viejo rechaza el campo desconocido con `INVALID_REQUEST` (definitivo y claro), por eso se instalan primero los nodos y después el portal.
- **Alternativa**: subir a `/2` (rompe cualquier despliegue con nodos sin actualizar, sin ventaja real).

## R5. Servicios ya entregados: contraseña nueva con persistencia previa

- **Problema**: la contraseña vigente de esos servicios fue entregada como la de `root` y pudo ser vista; reutilizarla para `nap` la dejaría válida en otra cuenta.
- **Decisión**: una acción de administración crea una operación `reparar` con marca `acceso_consola`, genera una contraseña **nueva**, la guarda cifrada en el `contexto_seguro` de la operación **antes** de enviarla y, sólo con la confirmación del nodo, la promueve a `credenciales_encrypted`, pasa el usuario mostrado a `nap` y registra el cambio en el historial. Si el resultado es incierto, el reintento envía la misma contraseña (el runner la deja igual o la aplica una sola vez).
- **Razón**: nunca hay un instante en que el portal ignore qué contraseña puede estar aplicada en el contenedor (Principio III).
- **Servicios sin clave SSH** (anteriores a la 017): `configure` necesita una clave; la acción responde `409 sin_clave` y esos servicios siguen con `root` hasta que la persona registre una. No se asume que existan.

## R6. Qué usuario muestra el portal

- **Decisión**: `acceso_metadata.username` pasa a `nap` sólo cuando el cambio se aplicó (servicio nuevo o actualizado) y conserva `root` en el resto; la UI deriva la indicación de ese dato. «Revelar acceso inicial» no cambia de lógica: toma el usuario de `acceso_metadata`.

## R7. Higiene de secretos

- La contraseña viaja por stdin (JSON al runner y `chpasswd` dentro del contenedor), nunca por `argv`; las respuestas y errores del runner sólo llevan códigos; el portal no registra solicitudes del runner. Se agregan pruebas que fuerzan fallos y buscan el valor en respuestas, registros y auditoría (SC-005).
