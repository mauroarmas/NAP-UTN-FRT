# Validación real: acceso SSH a Linux IaaS (feature 017)

Ensayo del 03/11/2026 en el laboratorio frt + pve91, con el paquete de la rama `017-acceso-ssh-iaas-linux` (commit `eda65a0`,
incluye la `016`). **Escenarios 1, 2, 3, 5, 6, 8, 9, 10 y 11 comprobados; 4 y 12 parcialmente** (ver al final).

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

## Hallazgo del laboratorio: la IP mostrada no era la real (corregido)

El portal mostraba `ssh nap@192.168.100.122` (la dirección *reservada* para la MAC del CT), pero el DHCP de este laboratorio **no respeta las reservas** y
entregó `192.168.100.18` (en el #41, `.17`; ya había pasado con otros CT). El comando mostrado daba `No route to host`.

**Corrección** (commit posterior al ensayo): el runner informa la IPv4 real de `eth0` en `configure`/`probe` (`direccion`), el portal la guarda en
`acceso_metadata.ssh.direccion` y el comando la prefiere a la reservada. Se refresca al **iniciar o reiniciar** el servicio, sin hacer fallar la orden si el nodo
no responde (se conserva la última conocida). Comprobado en el #42: antes `ssh nap@192.168.100.122`, tras detener e iniciar desde el portal
`ssh nap@192.168.100.18`, y ese comando entra. Instalado en ambos nodos (2 archivos; el `policy_digest` no cambia).

Límite: la IP se aprende en el despliegue, en un reemplazo de clave y al iniciar/reiniciar. Si el DHCP la cambiara con el servicio en marcha, el portal
seguiría mostrando la anterior hasta el próximo inicio.

## Reinicio de pve91 (escenario 9)

Con el Ubuntu #42 en marcha (clave de la notebook, revisión 2 aplicada), `systemctl reboot` en pve91:

| Qué | Resultado |
|---|---|
| Nodo | Volvió en ~60 s, con quórum |
| `nap-isolation-restore` | 23:38:51 → 23:39:05, **antes** de `pve-guests` (23:39:05); `estado: ok`, `fallidos: []`, `restaurados: []` (pve91 no aloja instancias OCI; los 6 `obsoletos` son recibos viejos) |
| Contenedor | No arrancó solo (sin `onboot`, decisión vigente); el portal mostró `RUNNING` unos instantes y se corrigió solo a `STOPPED` |
| Iniciar desde el portal | Confirmado; el comando muestra la IP real |
| Después de iniciar | `sshd` responde; `authorized_keys` con una sola línea (la huella de la notebook); `passwordauthentication no`, `permitrootlogin no`, `allowusers nap` |
| Conexión | Desde la notebook, `ssh nap@192.168.100.18` entra |

## Escenarios 4 y 12

- **4 (clave inválida en el formulario):** durante el ensayo se pegó por error la salida de `ssh-keygen`, y el formulario la rechazó con el mensaje
  «Tipo de clave no admitido. Usá ed25519 (recomendado), ecdsa o RSA de 3072 bits o más.» Los demás casos (clave privada, RSA corta, varias líneas) están cubiertos
  por pruebas automáticas, no se repitieron en la interfaz.
- **12 (regresión):** la MariaDB #40 (frt) conserva su acceso `mariadb` sin bloque SSH, su tabla `nap011_*` y el 3306 abierto para un cliente permitido.
  **nginx no se desplegó en vivo** en este ensayo (pve91 aloja un solo servicio a la vez); lo cubren las pruebas automáticas.

## Límites que quedan

- No se probó un corte brusco del nodo ni la caída de ambos nodos.
- La consola del portal sigue bloqueada para IaaS (decisión de esta feature: no se modifica); el acceso es solo por SSH.
- Los Linux IaaS **no tienen aislamiento de red por instancia**: la clave es el único control de ingreso.
