# Research: Acceso SSH a servicios IaaS Linux

Hallazgos del 03/11/2026 sobre el código de la rama `dev` (`325fc3c`). Cada decisión cita el archivo que la sostiene.

## R1. Qué es hoy un Linux IaaS "crudo"

- Se crea con `client.create_lxc(node, **config)` (`orquestacion_service.py:_dispatch`), con una contraseña de `root` generada y cifrada
  (`credenciales_iaas` → `servicio.credenciales_encrypted`). Su `acceso_metadata` es una constante armada en el orquestador:
  `metodo: 'consola'`, `username: 'root'`, `endpoint: /servicios/N/consola`, `addresses: [IP reservada]`
  (`orquestacion_service.py` fase `bootstrap`).
- No pasa por el runner del nodo: no hay "preparación" real, solo se declara `local_health: True`.
- Está en el puente con IP DHCP y una dirección reservada (`reserva_red_service`). **No tiene** reglas nftables ni `client_cidrs`:
  eso solo existe en el motor de aplicaciones (`infra/applications/job/isolation.py`).

**Decisión**: la spec no promete restricción de red para Linux IaaS (FR-008/SC-003 corregidos). El único control de ingreso es la clave.
**Alternativa descartada**: agregar aislamiento nftables a IaaS. Es otra feature (otra política, otro gate) y no la pidió nadie.

## R2. Cómo llevar la clave y el usuario al contenedor

La API de Proxmox acepta `ssh-public-keys` solo al **crear** el LXC y solo para `root`. No sirve para: usuario sin privilegios (Q2 = B),
reemplazar la clave (US3) ni servicios ya entregados (Q1 = A). Las tres exigen ejecutar dentro del contenedor.

**Decisión**: un único mecanismo para servicios nuevos, existentes y reemplazos: una acción del runner del nodo que ejecuta
`pct exec`/`pct push` sobre el invitado ya verificado como propio. Un solo camino evita tener un código para "al crear" y otro para "después".

**Alternativas descartadas**
- `ssh-public-keys` al crear: cubre solo root y solo el alta.
- `hookscript` de Proxmox: `_configuration` lo rechaza por diseño.
- Entrar al contenedor por SSH con la contraseña de root para configurarlo: expone la contraseña y depende de la red del portal.

## R3. Dónde vive la acción: protocolo propio, no reutilizar `nap-guest-runner/1`

`nap-guest-runner/1` exige receta registrada, `definition_sha256`, `bundle_sha256` y producto (`schemas/guest_runner.py`); Linux IaaS crudo no
tiene nada de eso. `nap_guest_runner.py` ya despacha por protocolo (`is_application_request` → `nap-application-job/1`).

**Decisión**: protocolo cerrado nuevo `nap-iaas-access/1`, con despacho propio en `nap_guest_runner.py` y lógica en un módulo nuevo
`infra/runner/iaas_access.py`. Acciones: `configure` y `probe`. Contrato en `contracts/runner-iaas-access.md`.

## R4. No alterar el `policy_digest` de los perfiles Docker

`policy_digest()` (`infra/applications/docker/runtime.py`) hashea `job/*.py`, `docker/{runtime,contract,guest,deploy,access,probes}.py`,
`profiles/docker/ubuntu24.json`, `schemas/nap-deployment-1.json`, `runner/node_executor.py` y el contrato de perfiles.
`runner/nap_guest_runner.py` y cualquier archivo nuevo en `infra/runner/` quedan fuera.

**Decisión**: restricción dura del plan: **no tocar** `node_executor.py` ni nada en `job/`/`docker/`. Si se respeta, los perfiles `docker-ubuntu24:9`
siguen válidos y no hace falta gate Docker. Se verifica con una prueba que compara `policy_digest()` antes y después.
Sí cambia el `code_sha256` del paquete de nodo: hay que reinstalar con `install.sh`/`actualizar-nodos-011.sh` en frt y pve91 (`install.py` lista los
archivos permitidos en `SOURCES`/`ALLOWED`; el módulo nuevo se agrega ahí).

## R5. Verificación de "el acceso responde" (FR-006)

El worker del portal puede no tener ruta a los invitados en otras instalaciones. **Decisión**: la acción `probe` corre **dentro del invitado**
(vía `pct exec`): `sshd` escuchando en 22, banner `SSH-2.0-`, la huella de `authorized_keys` coincide con la registrada, `PasswordAuthentication no`
y `PermitRootLogin no` en la configuración efectiva (`sshd -T`). Es salud local; no prueba la ruta de red de la persona, y la spec lo declara.
**Alternativa descartada**: conectar desde el portal al puerto 22. Frágil según la red.

## R6. Cómo se gestiona la clave en la base

Una fila por servicio (`claves_acceso_servicio`), con una `revision` que sube con cada reemplazo y una `aplicada_revision` que fija el runner al
confirmar. "Pendiente" = `revision != aplicada_revision`. Evita una máquina de estados nueva. Antes de que exista el servicio, la clave viaja en la
asignación del pedido (`asignacion_snapshot`) y se vuelca en la tabla al materializar (`_materialize`).
La clave pública no es secreta, pero la privada **nunca** entra: se rechaza por validación (cabecera `PRIVATE KEY`, formato no `tipo base64 [comentario]`).

## R7. Operación durable para reemplazos y servicios existentes

Un reemplazo o un alta tardía es una operación contra infraestructura y debe ser recuperable (Principio III). **Decisión**: nuevo tipo
`acceso_ssh` en `operaciones_infraestructura`, ejecutado por el mismo worker con el mismo arrendamiento y CAS. Es idempotente por
`(servicio_id, revision)`: reenviar la acción con la misma revisión deja el mismo estado final, por lo que un reintento tras incertidumbre es seguro.
Es la pieza de mayor riesgo del plan: antes de escribir tareas hay que leer completo `orquestacion_service.py` (623 líneas) y `operaciones.py`.

## R8. Usuario de conexión y elevación

Usuario fijo `nap` (no configurable: Principio VII). Pertenece a `sudo` con `NOPASSWD`, porque no tiene contraseña. Es equivalente a administrador
**dentro del contenedor propio** (sin privilegios en el nodo: los LXC son `unprivileged: 1`). `PermitRootLogin no`, `PasswordAuthentication no`,
`AllowUsers nap` en un archivo propio de `sshd_config.d/` (no se edita el principal). La contraseña de `root` se conserva solo para la consola
(FR-015) y deja de servir por SSH.

## R9. Servicios existentes y la consola

`Servicios` ya entregados sin clave siguen mostrando `consola`. El detalle de acceso agrega un bloque `acceso_ssh` **sin cambiar `metodo`** ni
la compuerta (`consola_gate_service`), así que FR-015 se cumple por construcción.

## R10. Qué no se sabe y se resuelve en la validación real

- Si la plantilla `ubuntu-24.04-standard` trae `openssh-server` instalado y habilitado. Si no, la acción `configure` no puede instalarlo (sin red de
  paquetes garantizada); en ese caso el servicio queda en fallo con motivo y la decisión pasa a ser elegir otra plantilla. Se comprueba el primer día en pve91 con `pct exec <vmid> -- systemctl status ssh`.
- Si el LXC `unprivileged` permite a `pct exec` crear usuarios y escribir `/home` sin fricción con el almacenamiento NFS. Se comprueba en el mismo ensayo.
