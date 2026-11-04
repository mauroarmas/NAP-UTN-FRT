# Contrato del runner: `nap-iaas-access/1`

Protocolo cerrado y separado de `nap-guest-runner/1` y `nap-application-job/1`. Mismo transporte: SSH a la cuenta `naprunner`, `ForceCommand`
al wrapper `nap-guest-runner`, JSON por stdin. El despacho se hace por el campo `protocol` (igual que `is_application_request`).

## Solicitud

```json
{
  "protocol": "nap-iaas-access/1",
  "operation_id": "<uuid>",
  "action": "configure | probe",
  "cluster_uuid": "<uuid>",
  "resource_uuid": "<uuid>",
  "node": "pve91",
  "vmid": 101,
  "pool": "catedra-3",
  "nonce": "<22..128 [A-Za-z0-9_-]>",
  "revision": 2,
  "usuario": "nap",
  "clave_publica": "ssh-ed25519 AAAA…"
}
```

- Campos exactos; cualquier otro, o duplicado, se rechaza `INVALID_REQUEST`. Tope de 16 KiB.
- `clave_publica` solo en `configure`. Se valida de nuevo en el nodo con las mismas reglas que el portal (no se confía en el origen).
- `usuario` solo puede ser `nap`.

## Identidad (antes de cualquier efecto)

El nodo comprueba, leyendo la configuración del LXC, que `vmid`, nodo, pool, `resource_uuid` y la marca con el `nonce` coinciden, que es
`unprivileged` y de tipo `lxc`. Un `vmid` reutilizado por otro recurso falla con `IDENTITY_MISMATCH` y **no** escribe nada.
(La marca es la misma que escribe `identidad_infra_service.descripcion`.)

## Acciones

**`configure`** — idempotente por `(resource_uuid, revision)`:
1. Si el invitado está detenido: error `GUEST_NOT_RUNNING` (reintentable; el portal reintenta al iniciarlo).
2. Crea el usuario `nap` si no existe (sin contraseña, shell bash, grupo `sudo`) y deja `/etc/sudoers.d/nap-acceso` con `nap ALL=(ALL) NOPASSWD:ALL` (0440).
3. Escribe `~nap/.ssh/authorized_keys` (0600, dueño `nap`) con **solo** la clave recibida, reemplazando todo lo anterior.
4. Escribe `/etc/ssh/sshd_config.d/50-nap-acceso.conf`: `PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers nap`, `KbdInteractiveAuthentication no`.
5. Valida con `sshd -t`, habilita y recarga `ssh`.
6. Ejecuta el mismo chequeo que `probe`.

La clave, el nombre de usuario y el contenido de los archivos **nunca** se interpolan en una línea de comandos: viajan por stdin a `pct exec … tee`
con rutas fijas. Los argumentos son una lista, sin shell.

**`probe`** — solo lectura: `sshd` escuchando en 22, banner `SSH-2.0-`, huella de `authorized_keys` igual a la solicitada, y
`sshd -T` reporta `passwordauthentication no`, `permitrootlogin no`, `allowusers nap`.

## Respuesta

```json
{ "protocol": "nap-iaas-access/1", "operation_id": "…", "action": "configure",
  "status": "succeeded | failed | unconfirmed", "identity_verified": true,
  "result": { "ready": true, "revision": 2, "huella": "SHA256:…", "usuario": "nap", "puerto": 22 },
  "error": { "code": "…", "retryable": true } }
```

Códigos: `INVALID_REQUEST`, `IDENTITY_MISMATCH`, `GUEST_NOT_RUNNING`, `SSHD_UNAVAILABLE` (la plantilla no trae `openssh-server`),
`CONFIG_INVALID`, `PROBE_FAILED`, `UNCONFIRMED`. `unconfirmed` = el efecto pudo haber ocurrido; el portal repite **la misma** `revision`.

## Restricciones de implementación

- Archivo nuevo `infra/runner/iaas_access.py`; despacho en `nap_guest_runner.py`. **No** modificar `infra/runner/node_executor.py`,
  `infra/applications/job/*` ni `infra/applications/docker/*` (entran en `policy_digest`, ver `research.md` R4).
- Agregar el archivo a `SOURCES` y `ALLOWED` en `infra/applications/install.py`; la ruta instalada es `/opt/nap/runner/iaas_access.py`.
- Sin dependencias fuera de la biblioteca estándar (el nodo solo tiene `python3` y `python3-jsonschema`).
- Sin registros que contengan la clave; solo huella.
