# Validación real: acceso SSH a Linux IaaS (feature 017)

Ensayo del 03/11/2026 en el laboratorio frt + pve91, con el paquete de la rama `017-acceso-ssh-iaas-linux` (commit `eda65a0`,
incluye la `016`). Resultado parcial: **escenarios 2, 3, 5, 6, 8 y 11 comprobados**; faltan 1, 4, 9, 10 y 12 (ver al final).

## Instalación

- Plan en ambos nodos: **4 archivos** (`iaas_access.py`, `iaas_protocol.py`, `ssh_keys.py`, `nap_guest_runner.py`); `profiles_enabled_by_install: []`,
  `guests_created: false`. `code_sha256` `4734dc9b…`. Respaldos `/root/nap011-package-backup-*`.
- El `policy_digest` sigue siendo `f269ca1e…`: los perfiles Docker (`docker-ubuntu24:9`) siguen válidos sin gate nuevo.
  La MariaDB (CT 100 en frt) y su tabla `nap011_*` quedaron intactas.
- `actualizar-nodos-011.sh` **no sirve** para esto: intenta regenerar el `runner.json` con la revisión 2 de perfil, ya habilitada, y se detiene. Se instaló con
  `git archive HEAD` + `infra/runner/install.sh` (el plan se obtiene antes con `install.py --source-root` sin `--apply`).
- Portal: migración `017_01_clave_acceso_servicio` aplicada (respaldo previo de la base) y `api`/`worker` recreados.

## Riesgo R10 resuelto

La plantilla `ubuntu-24.04-standard` trae `sshd` (habilitado y activo), `sudo`, `useradd` y `bash`: no hace falta cambiar de plantilla.

## Resultados (servicio #41, Ubuntu en pve91, CT 101, sin clave previa)

| # | Escenario | Resultado |
|---|---|---|
| 8 | Alta tardía de una clave en un servicio ya entregado | Operación `reparar` confirmada; fila revisión 1 aplicada |
| 2 | Entrar con la clave como `nap`; `sudo -n true` | Entra, `uid=1000(nap)`, sudo sin contraseña OK |
| 3 | `root` con la clave; `nap` por contraseña; otra clave | Los tres rechazados (`Permission denied (publickey)`) |
| 6 | Reemplazo por una clave nueva | Revisión 2 aplicada; la nueva entra, la **anterior es rechazada** |
| 5 | Detener e iniciar desde el portal | Detenido: el detalle no ofrece el comando y explica el motivo. Iniciado: `puede_conectar` y la misma clave entra |
| 11 | Claves en logs, historial, contexto de operaciones y journal del nodo | 0 coincidencias; el historial guarda solo huellas |

El detalle de acceso mantiene `metodo: consola` (la consola no cambió).

## Hallazgo del laboratorio: la IP mostrada no es la real

El portal muestra `ssh nap@192.168.100.120` (la dirección reservada para la MAC del CT), pero el DHCP de este laboratorio **no respeta las reservas** y
entregó `192.168.100.17`. Ya había pasado con otros contenedores (reservada `.121`, entregada `.15`). El acceso por la IP real funciona. En un
entorno donde la reserva DHCP coincida con la asignada, el comando mostrado es correcto. Queda como decisión: o se configura la reserva en el DHCP
del laboratorio, o el portal informa la dirección observada en el invitado en lugar de la reservada.

## Pendiente

- 1 y 4: despliegue nuevo de un Ubuntu con clave **desde la interfaz del portal** y validación de claves inválidas en el formulario.
- 9: reinicio de pve91 y reinicio del servicio.
- 10: baja y nuevo pedido con el mismo `vmid`.
- 12: regresión de MariaDB y nginx en el portal.
