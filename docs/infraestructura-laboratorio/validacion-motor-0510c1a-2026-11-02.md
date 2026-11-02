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

## Recorrido de MariaDB por el portal (pedidos #44 y #45)

Hecho con los servicios del backend (`catalog.change`, `solicitud_service`, `evaluacion_service`,
`admision_service`, `admitir_orden`), no con clics ni con el login de una persona. La oferta se
agregó con `MARIADB_APPLICATION_VALIDATION` apuntando a `docker-ubuntu24:2` y al manifiesto probado.
La cuenta semilla `admin@utn.frt.edu.ar` estaba inactiva: con autorización explícita se la activó
sólo para esto (`UPDATE` puntual) y se la dejó otra vez inactiva. No se usó la cuenta de otra persona.
El pedido salió con la cátedra visible para Ivan (`Catedra Ajena T091`); es dato de prueba.

| Paso | Resultado |
|---|---|
| Oferta MariaDB, evaluación (Medium, `pve91`/`truenas`) y aprobación | Correctos; configuración congelada con el perfil `:2` |
| Creación del LXC y arranque de MariaDB (Docker) | Correctos en ambos pedidos |
| Comprobación SQL/TLS del job | **Falló dos veces** con `DEPENDENCY_UNAVAILABLE` (#44 y #45) |
| Baja del servicio #24 (con imagen vieja del portal) | Quedó `incierta` (`resultado_no_confirmado`); el CT y los discos sí se destruyeron |
| Baja del servicio #24 tras reconstruir la imagen | `confirmada`; sin tablas `nap011_*`, dirección liberada |
| Baja del servicio #25 | `confirmada` a la primera; sin CT, discos ni tablas |
| Reutilización del VMID 102 (pedido #45 tras la baja de #44) | El CT recibió red y llegó a instalar MariaDB: no heredó reglas |

### Hallazgos

1. **Imagen del portal desactualizada (entorno, resuelto).** La imagen `nap-handoff-api` era del 28/10 y
   sólo copia `protocol.py` y `configuration.py` de `infra/`; el backend se monta fresco desde el repo.
   El portal armaba la petición `cleanup` y su propio `parse_request` viejo la rechazaba
   (`INVALID_REQUEST`), de modo que nunca abría SSH y la baja quedaba `incierta`. Se resolvió con
   `docker compose build api worker` y recreando ambos. **Hay que reconstruir las imágenes tras cada pull.**
   Conviene coordinar con Mauro que el compose de traspaso lo advierta o monte `infra/`.
2. **Plazo de la comprobación frente a la primera inicialización (límite; confirmado con un paquete experimental, ver abajo).** En este
   laboratorio (NFS en TrueNAS, 2 vCPU, ~4 GB) MariaDB terminó de inicializar ~145 s después de `docker run`
   (#44: 17:29:10→17:31:35; #45: 17:49:51→17:52:16) y el job falló 4 s después, porque `probe_database`
   espera 120 s. Los dos gates directos del mismo día sí pasaron; no se midió su tiempo de inicialización.
   No se tocó el motor. Propuesta para el backend (sin implementar): hacer configurable o ampliar ese plazo,
   y mostrar un diagnóstico específico en vez de `DEPENDENCY_UNAVAILABLE`. Pendiente de backend relacionado: 7.
3. Reservas de red abiertas de servicios históricos (`app-100`…`app-103`) se dejaron como estaban.

Los pedidos #44/#45 y los servicios #24/#25 permanecen como historia en la base del laboratorio.

## Prueba con el plazo ampliado (paquete experimental local)

Para comprobar la causa del hallazgo 2 se hizo una copia **local y no publicada** del motor
(rama local `exp/plazo-probe`, sin push): `docker/guest.py` con el plazo de `probe_database`
en 300 s en lugar de 120 s. Como `guest.py` entra en el `policy_digest`, el paquete es otro:
digest `8447e73978c4d196c597c85ad5742691e025bb97ed3ff7ce62798d059797499a`, `code_sha256` instalado en `pve91`
`47b759b926f1050831c32a7720db03ca02718b00feabb703f982f45df6a02828`, y perfil nuevo `docker-ubuntu24:3`
(sha256 `207edd86875b7f977c2470cf89343cb9691bcc0bbeb93f7fbdaa5ba094668dec`, sólo `pve91`) validado con su propio gate:
job `confirmado`, persistencia (18 s) y los mismos cinco rechazos. `frt` conserva el paquete de `0510c1a`.

En ese gate la inicialización de MariaDB tardó **131 s** (18:02:55→18:05:06): habría superado igualmente
los 120 s originales y con 300 s el job se confirmó. Respalda que la causa era el plazo.

Recorrido completo por el portal con el perfil `:3` (pedido #46, servicio #26; oferta actualizada con la misma
operación del botón "Actualizar aplicación"):

| Paso | Resultado |
|---|---|
| Despliegue y verificación del portal | `confirmada`; servicio `RUNNING` / `utilizable` (el portal repitió `SELECT 1` con TLS desde su red) |
| Revelado de acceso (cuenta de la cátedra) | Dirección, puerto 3306, base, usuario, contraseña y CA pública; sin root |
| Conexión desde la PC del portal | TLS 1.3 verificando la CA entregada y la identidad del servidor; escritura de una fila |
| Detener | `confirmada`; servicio `STOPPED`; el revelado quedó bloqueado (`acceso_no_preparado`) |
| Iniciar | `confirmada`; la fila se recuperó con las mismas credenciales |
| Reiniciar | `confirmada`; la fila se recuperó |
| Baja | `confirmada`; sin CT, discos ni tablas `nap011_*`; dirección liberada |

**Estado resultante de `pve91`:** corre el paquete **experimental** (plazo 300 s) con `docker-ubuntu24:3`
habilitado; `:1` y `:2` quedan bloqueados por el runner (su digest ya no coincide con el paquete). Para volver
al motor publicado: reinstalar `HEAD` con `actualizar-nodos-011.sh` y volver a habilitar la revisión
correspondiente (hoy `:2`) con su gate; no se hizo. El cambio real en el motor lo decide el backend.

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
- Real: las tablas anteriores y el recorrido por el portal.

## No probado

- Pull privado, uso funcional de secretos por una aplicación, dos cátedras simultáneas.
- La validación del portal con el **motor publicado** (`0510c1a`, plazo 120 s) en este laboratorio: sólo con el plazo ampliado, en copia local.
- `frt`, migración, HA, varios nodos, carga de un curso, reinicio del host Proxmox.

## Pendientes de backend (identificados en la revisión, sin implementar aquí)

1 (runner inválido deja aprobar), 5 (reintento/reparación OCI), 6 (diagnóstico de CA del portal) y
7 (traza de excepciones del worker). Se coordinan con Mauro para no duplicar cambios.

## Scripts

`actualizar-nodos-011.sh` (revisión pendiente sin tocar históricas), `gate-docker-pve91.sh`
(`APLICACION=mariadb`, `evidencia`, `persistencia`), `habilitar-perfil-pve91.sh` (exige job confirmado
y persistencia; fusiona perfiles), `limpiar-tablas-huerfanas-pve91.sh` (ya sólo lectura). Los
sockets SSH se comparten con `NAP_SSH_CTL`.

## Espera de arranque configurable (cambio del motor, 02/11/2026)

A partir de la prueba anterior se incorporó al motor, en `main`, una espera de arranque más larga y
configurable por nodo (`infra/applications/docker/probes.py`, `guest.py`):

- Por defecto la comprobación de **bases de datos espera 300 s** (antes 120 s) y la **web 90 s** (sin cambio).
- Ajuste opcional por nodo en `/etc/nap/applications-011/limits.json` (root, modo sin escritura de grupo/otros,
  sin enlaces ni duplicados, ≤ 4 KiB):

  ```json
  {"schema_version": "nap-application-limits/1", "espera_base_datos_segundos": 450, "espera_web_segundos": 90}
  ```

  `espera_base_datos_segundos` admite 60–600 y `espera_web_segundos` 30–600 (el proceso hijo del nodo corta a los 900 s).
  Un archivo inválido **falla cerrado** (`PROFILE_UNAVAILABLE`); no se usan los valores por defecto en silencio.
- No cambia el esquema de la configuración ni `runner.json`. Sí cambia el `policy_digest`
  (`99279fd45cd2e0ffa243598f5adfbd6d87dc77940b623ee089f4d72fbd4fd25c`): requiere una revisión nueva de perfil y su gate.
- Automatizado: `test_ready_wait.py` y las pruebas del guest (defectos, ajuste por nodo, límites, archivo inválido,
  enlace simbólico). **Sin validación Proxmox real todavía** con este paquete exacto.
