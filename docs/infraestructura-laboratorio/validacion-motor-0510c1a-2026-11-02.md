# Validación del motor `0510c1a` en el laboratorio frt/pve91 + TrueNAS — 02/11/2026

Laboratorio de VirtualBox, dos nodos (`frt`, `pve91`), PVE 9.2.2, kernel `7.0.2-6-pve`, storage
NFS en TrueNAS. **No acredita la infraestructura universitaria ni el laboratorio de Mauro.**
Sin secretos: contraseñas, claves y el valor de la fila de prueba no se publican.

## Configuración

- Rama `011-desplegar-servicios-universitarios` en `0510c1a` (fast-forward desde `2fc95cb`;
  respaldo en la rama local `respaldo/lab-2fc95cb`).
- `policy_digest` del motor: `4ebb0a71e161fd3d20c89a4c29ec60c1e735ac1cfe3cc0d7dcf732e133c18ac0`.
- Paquete instalado en `frt` y `pve91`: `code_sha256` `b6a73e28b20f32de057df1e30a93591f2cebf84d2a42ebe3198975a640ba4cad`.
- Perfiles: `docker-ubuntu24:1` (histórico, digest `73e804b6…`) **se conserva sin cambios**.
  `docker-ubuntu24:2`, sha256 `52acbfba53fa17cfea93e909fdce48d860dfb475c27ca56ab55b0d09c125d73f`,
  habilitado **sólo para `pve91`**. `frt` no figura en `nodes`: sin CA propia, 1 vCPU y sin gate.
  El hash es de este clúster; no se copió ninguno de Mauro.
- Recursos: Medium (2 vCPU, 1024 MB, 8 GB). Small no se probó.

## Validación Proxmox real (pve91)

| Comprobación | Resultado |
|---|---|
| Gate MariaDB `11.4` (manifiesto `sha256:d9fc0297…a9521`, amd64), revisión 2 | Job `confirmado`: `aislamiento`, `runtime`, `salud`, `autenticacion_tcp` (TLS verificado con la CA + `SELECT 1`) |
| Persistencia | Fila escrita, LXC reiniciado (`pct reboot`), misma fila recuperada; consulta aceptada a los 19 s |
| Rechazos MariaDB (gate nuevo, con control positivo) | Contraseña incorrecta: error 1045. CA no confiable: 2026. Sin TLS: 3159. Root remoto: 1045. `docente` sin lectura de `mysql.user`: 1142 |
| Baja del invitado | Sin LXC, discos, pool ni tablas `nap011_*` |
| Reutilización del VMID 900011 | Gate whoami inmediato: `confirmado` (`aislamiento`, `runtime`, `salud`, `acceso_web`); luego baja sin tablas residuales |
| Servicio previo (#23, CT 101 nginx-unprivileged) | No se tocó (detenido durante la prueba) |

La limpieza del gate usa la misma acción `cleanup` del runtime que la baja del portal
(identidad, ausencia del VMID y recibo de reglas).

## Operación incierta resuelta con aprobación

La instalación en `pve91` se detuvo con `ACTIVE_OR_UNKNOWN_JOB` por un job histórico `incierto`
(gate whoami del 28/10, VMID 900011). Tras comprobar ausencia del VMID en el clúster, de discos,
unidad systemd, tablas y pool, y con aprobación explícita, se movió **sólo ese manifiesto** a
`/root/nap011-cuarentena` en `pve91` (copia con sha256
`99770466172360535aba784a3f5b584bda99039f21eb17efe4908b9cd0935dea`). No se repitió el job.

## Automatizado frente a real

- Automatizado (sin Proxmox): pruebas del gate y de los scripts en `infra/laboratorio`
  (169 pasan, 8 omitidas). Falla `test_registry_probe.py::test_diagnostic_cli_never_applies_node_configuration`,
  que también falla en `0510c1a` sin estos cambios (preexistente).
- Real: la tabla anterior.

## No probado

- Recorrido de pedido MariaDB desde el portal y acceso TLS desde el portal en este laboratorio.
- Pull privado, uso funcional de secretos por una aplicación, dos cátedras simultáneas.
- `frt`, migración, HA, varios nodos, carga de un curso, reinicio del host Proxmox.

## Pendientes de backend (identificados en la revisión, sin implementar aquí)

1 (runner inválido deja aprobar), 5 (reintento/reparación OCI), 6 (diagnóstico de CA del portal) y
7 (traza de excepciones del worker). Se coordinan con Mauro para no duplicar cambios.

## Scripts

`actualizar-nodos-011.sh` (revisión pendiente sin tocar históricas), `gate-docker-pve91.sh`
(`APLICACION=mariadb`, `evidencia`, `persistencia`), `habilitar-perfil-pve91.sh` (exige job confirmado
y persistencia; fusiona perfiles), `limpiar-tablas-huerfanas-pve91.sh` (ya sólo lectura). Los
sockets SSH se comparten con `NAP_SSH_CTL`.
