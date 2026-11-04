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

(Estado superado por la validación con el motor publicado, más abajo.)

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
- El motor `0510c1a` con plazo fijo de 120 s no se validó de punta a punta en este laboratorio: falló dos veces por el plazo (ver hallazgo 2). Se validó el motor posterior con espera configurable.
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
  enlace simbólico). La validación Proxmox real de este paquete exacto está en la sección siguiente.

## Validación del motor publicado con espera configurable (revisión 4)

Paquete de `main` instalado en `frt` y `pve91` (`code_sha256`
`3fb8fed35536444089f0f8641508373be7cd5987e5f299330e1e76930b972c5d`, `policy_digest`
`99279fd45cd2e0ffa243598f5adfbd6d87dc77940b623ee089f4d72fbd4fd25c`). Perfil `docker-ubuntu24:4`
(sha256 `1f596b638a88d46f4ec719b3fad9db5c8ac350d4195ca2b1e07e6e075b9b6ec8`) habilitado **sólo para `pve91`**;
`frt` lo rechaza. Sin `limits.json` en los nodos: rigen los valores por defecto (300 s / 90 s).
Las revisiones 1 a 3 se conservan como historia y el runner las muestra `bloqueado` (su digest ya no coincide).

| Comprobación | Resultado |
|---|---|
| Gate MariaDB (revisión 4) | Job `confirmado`; persistencia (17 s) y los cinco rechazos como antes; baja limpia |
| Inicialización de MariaDB en ese gate | 119 s: al borde del plazo viejo de 120 s |
| Portal, pedido #47 / servicio #27 | `confirmada`, `RUNNING` / `utilizable`; revelado sin root; TLS 1.3 verificando la CA desde la PC; fila escrita |
| Detener / revelado | `confirmada`, `STOPPED`; revelado bloqueado (`acceso_no_preparado`) |
| Iniciar / reiniciar | `confirmada` ambos; fila recuperada tras cada uno |
| Baja | `confirmada`; sin CT, discos ni tablas `nap011_*`; dirección liberada |

El compose de traspaso monta ahora `infra/` de sólo lectura en api y worker, para que el contrato del
backend coincida siempre con el código del repositorio.

Siguen sin probarse: pull privado, uso funcional de secretos por una aplicación, dos cátedras simultáneas,
`frt`, varios nodos, un host Proxmox reiniciado, y carga de un curso.

## Validación real de la reparación OCI (hallazgo 5) — revisiones 5 y 6

Método: falla controlada con `limits.json` de 60 s (mínimo permitido) en `pve91`, de modo que el job falle
durante la primera inicialización de MariaDB; luego se retira ese archivo (vuelven los 300 s) y se repara con
`reintentar_despliegue` (la misma operación del botón). Pedidos de prueba #48 (revisión 5) y #49 (revisión 6).

| Paso | Resultado |
|---|---|
| Falla controlada | Operación `fallida` (`DEPENDENCY_UNAVAILABLE`), pedido `ERROR`, intento 1 `fallido` |
| Reparación admitida | 202; operación `reparar` con el mismo `operacion_raiz_id`; el LXC se detiene y se envía un job nuevo |
| Resultado final (#49) | Operación `confirmada`, pedido `ACTIVO`, servicio `RUNNING` / `utilizable`; intentos 1 `fallido` + 2 `confirmado` |
| Recurso e identidad | Un solo LXC y una sola identidad; contraseñas sin cambios (revisión 1 de ambos secretos) |
| Acceso y datos | TLS 1.3 verificando la CA desde la PC; fila escrita; recuperada tras detener e iniciar por el portal |
| Baja posterior | `confirmada`; sin CT, discos ni tablas `nap011_*`; dirección liberada |

### Dos defectos que sólo apareció al reparar de verdad

1. **Nombre de contenedor en uso (corregido).** El `start` del guest hacía `docker run --name nap-…` y en una reparación ese
   contenedor ya existe. Ahora se retira antes, sólo si lleva la etiqueta `nap.resource_uuid` de esa instancia (otro dueño
   falla sin tocarlo) y nunca se borran los volúmenes. Con la revisión 5 el contenedor se reemplazó correctamente.
2. **Base a medio inicializar (corregido).** Si el intento muere durante la primera inicialización (nuestro caso: el job
   falla y el paro del LXC mata `mariadbd`), el volumen queda con `mysql/` pero sin la base de la aplicación y la entrada
   oficial lo da por inicializado: nunca crea la base ni el usuario y el acceso no funciona (la reparación del #48 falló
   así a los 300 s). Ahora, y sólo en ese caso, se reinicia el volumen propio de la instancia: sin la base de la aplicación
   todavía no puede haber datos de usuario. Una base completa nunca se toca. La reparación del #49 lo comprobó.

Límite conocido: si la interrupción cae entre la creación de la base y la del usuario, el directorio `catedra/` existe y no
se reinicia; esa reparación fallaría y la salida es la baja y un pedido nuevo.

### Paquete vigente y revisiones

Paquete de `main` en `frt` y `pve91`: `code_sha256` `19c864b15c7d5ffa89e2311d06540a62e44d7d70e2a008dec00c060d7c1ef679`,
`policy_digest` `77d26a9ffef574d3db9ee97b69aa38039c2e095db85278e37013f15b5b74aadd`. Perfil `docker-ubuntu24:6`
(sha256 `e153541ae163b306aa1c237136e5852d05fbd2421586cc0f505c7abae53f9f96`) habilitado sólo para `pve91`; las revisiones 1 a 5 son
historia (bloqueadas por el runner). Un pedido aprobado con una revisión anterior no se puede reparar tras actualizar el
paquete: el portal lo rechaza con `perfil_aplicacion_no_disponible` y la salida es la baja y un pedido nuevo.

Con el pedido #49 se completó también la validación con los pendientes 1, 6 y 7 cargados en el portal (aprobación con
runner comprobado y CA configurada). No se probó con una CA ausente ni con un `known_hosts` inválido en el laboratorio real.

Sin probar: pull privado, uso funcional de secretos, dos cátedras a la vez, `frt`, varios nodos, host reiniciado, carga de un curso.

## Segundo nodo (`frt`) y dos cátedras a la vez (03/11/2026)

**Preparación de `frt`** (apagado ordenado de su VM; pve91 perdió quórum mientras tanto y no había nada corriendo; no se tocó el quórum):
2 vCPU (antes 1), CA propia creada en el nodo con `crear-ca-nodo.sh` (la clave `ca.key` no sale de `frt`; el script se niega a sobrescribir una PKI existente),
y el portal pasó a confiar en las dos CA **públicas** (conjunto de 2 certificados en `application_gateway_ca_file`; sin claves).
El perfil `docker-ubuntu24:7` (sha256 `7934d314b0aaaf3c52403db0597375724fc7f9e67f2dea4efe14659dce086921`, `nodes=[frt, pve91]`) se habilitó
**sólo después de un gate completo en cada nodo** (job confirmado, persistencia y cinco rechazos de MariaDB en `frt` y en `pve91`, con la misma definición).
Los scripts ahora validan un perfil con varios nodos y exigen la evidencia de cada uno.

**Capacidad.** Con CT 100 y 101 (servicios anteriores, preservados) y una instancia nueva, el almacenamiento compartido no alcanzaba para una segunda
(libre 6 GB, hacían falta 8). Se amplió el disco de datos del TrueNAS de 30 a 60 GB (VDI dinámico; apagado ordenado de la VM, ampliación del pool en su interfaz tras
`sgdisk -e /dev/sdb`, porque la copia de respaldo de la tabla GPT quedaba en el final del disco viejo). El almacenamiento `truenas` pasó a ~57 GB y el portal lo vio sin cambios de configuración.

**Dos cátedras a la vez** (servicio #30, cátedra 3, en `pve91`; servicio #31, cátedra sintética de laboratorio, en `frt`; ambos `RUNNING` / `utilizable` simultáneamente):

| Comprobación | Resultado |
|---|---|
| Autorización | Cada docente revela sólo su servicio; el cruce da 403 en ambos sentidos |
| Credenciales | Cada clave abre sólo su base; la clave cruzada da error 1045 en ambos sentidos |
| TLS | Cada servidor presenta un certificado de la CA de **su** nodo (pve91 / frt); ambos verificados con el conjunto del portal, TLS 1.3 |
| Datos | Cada base guarda su propia marca y no ve la de la otra; cada docente ve sólo `catedra` e `information_schema` |
| Red, salida | Desde cada instancia: **bloqueado** el otro servicio, ambos nodos (SSH y 8006), el TrueNAS (NFS) y el portal; **alcanza** sólo el DNS permitido |
| Baja | Ambas `confirmada` a la vez, una por nodo; sin tablas `nap011_*`, direcciones liberadas, CT 100 y 101 intactos |

**Límite encontrado (configuración del laboratorio, no del motor).** Los nodos **sí** pueden conectarse al puerto 3306 de las instancias (sigue exigiendo TLS y contraseña):
la cadena de entrada de cada instancia acepta `192.168.100.0/24`, que en este laboratorio es la red de clientes y **incluye** a los nodos (subred plana). Mauro documentó un rechazo
desde el nodo con otra configuración de red. En la universidad, `client_cidrs` debe excluir las direcciones de gestión de los nodos. Tampoco se probó la separación a nivel de
cátedras con el mismo docente en ambas ni con más de dos instancias.

**Datos de prueba.** Se creó una cátedra (#25) y un usuario (#11) **sintéticos** (`lab-aislamiento-b@lab.invalid`, sin contraseña utilizable) y se desactivaron al terminar. Los pedidos #50 y #51
y los servicios #30 y #31 quedan como historia.

## Entrada acotada a los clientes (03/11/2026)

Resuelve el límite anterior: los nodos alcanzaban el 3306 de las instancias porque `client_cidrs` era toda la `/24`.

- **Perfil de red `lab-applications-011`, revisión 3.** `client_cidrs` pasa a 11 bloques que cubren la `/24` **sin** el gateway (.1) ni los nodos y el
  almacenamiento (.90 a .94). El portal (.89) queda **dentro**: su worker se conecta al 3306 para verificar cada base. La revisión 2 lo excluía por error y la
  verificación de un despliegue real expiró (`TimeoutError`); esa instancia no se pudo cerrar sola hasta quitar las reglas manuales que se le habían agregado.
- **Perfil Docker `docker-ubuntu24:8`** (sha256 `b8d4d941…21e2`, `nodes=[frt, pve91]`): misma definición que la 7; gate real completo en cada nodo (job confirmado,
  persistencia y rechazos de MariaDB). Ese gate corrió con la lista de la revisión 2 (sin .89); la revisión 3 sólo agrega .89 y se comprobó con un despliegue real.
- **Validador del backend** (`validar_red_aplicacion`): rechaza un `client_cidrs` que contenga la dirección de un nodo (`RUNNER_NODES`, `PROXMOX_HOST`) o el gateway.
  Acepta que contenga al portal.
- **Comprobación con despliegues reales, red revisión 3, sin reglas manuales** (pedido #53, servicio #33, en `pve91`; pedido #54, servicio #34, en `frt`):
  en cada uno, desde `frt` y `pve91` el 3306 queda **bloqueado** (incluido el nodo que aloja la instancia); desde el portal (.89) y desde un cliente (.88,
  alias de la PC, no otra máquina) **conecta** (MariaDB 11.4). Bajas `confirmadas`; sin tablas `nap011_*` ni invitados de prueba en ningún nodo.
- **Nota operativa.** La regla de una instancia se fija al desplegarla: una instancia anterior a un cambio de `client_cidrs` conserva sus reglas viejas. Quitar a un
  cliente exige dar de baja y volver a pedir. No agregar reglas nftables a mano a una instancia viva: el motor no reconoce la tabla modificada y la baja queda `incierta`.

## Reinicio de un nodo (03/11/2026)

**Defecto encontrado.** Tras `systemctl reboot` en `pve91`, con una instancia de MariaDB desplegada (servicio #38):

| Qué | Resultado |
|---|---|
| Nodo | vuelve en ~75 s; quórum, NFS (TrueNAS), `runner.json` y disco del LXC intactos |
| LXC | **no arranca solo** (`onboot: 0`) |
| Portal | muestra `RUNNING` falso mientras el nodo cae; se corrige solo ~2 min después de volver (`running → stopped`, "Estado observado en Proxmox; no se envió ninguna orden") |
| Tabla nftables `nap011_*` | **desaparece** (vive en el kernel) |
| `iniciar` por el portal | arranca el LXC **sin ninguna regla de red**: los nodos conectaban al 3306 y el portal seguía diciendo `RUNNING / utilizable` |

**Corrección.** Unidad systemd `nap-isolation-restore.service` (`Before=pve-guests.service`, instalada y habilitada por el paquete). Recrea la tabla de cada recurso con
recibo `applied` antes de que arranque ningún invitado. No guarda la política: la **recalcula** con la identidad y la configuración del job durable, el perfil de red
institucional y la configuración real del LXC, y `IsolationManager.ensure` la compara con el hash del recibo (cualquier diferencia falla cerrado). Sólo instala sobre
invitados **detenidos** y nunca inicia ni crea ninguno. Un recibo cuyo invitado ya no existe, o cuyo vmid reutiliza otro recurso, se omite como obsoleto; un invitado en marcha
sólo se verifica. Se reintenta únicamente lo transitorio (el clúster aún no publica los invitados). No usa `hookscript`: `_configuration` lo rechaza por diseño.

**Verificación real** (perfil `docker-ubuntu24:9`, `policy_digest` `f269ca1e…`, gate completo en `frt` y `pve91`; instancia #39 en `pve91`):

1. Reinicio de `pve91`: la unidad corrió a las 19:04:33 y `pve-guests` a las 19:04:35 (terminó antes). Informe: `restaurados` = la instancia, `obsoletos` = 6 recibos de pruebas viejas, `fallidos` = ninguno, 1 intento.
2. Con el LXC aún detenido la tabla `nap011` ya existía.
3. `iniciar` por el portal (confirmada en ~10 s): nodos `.90` y `.91` **bloqueados** al 3306; la PC (`.89`) conecta con TLS; el dato escrito antes del reinicio se recupera.
4. Baja confirmada; sin tablas ni invitados de prueba.

**Límites.**
- Las instancias **siguen sin arrancar solas** tras un reinicio: hay que iniciarlas por el portal. No se activó `onboot` a propósito: reiniciaría también los servicios que un usuario detuvo.
  Que el portal las reinicie al detectar que el nodo volvió es una mejora aparte.
- Si la restauración falla para un recurso, la unidad queda en fallo (se ve en `journalctl -u nap-isolation-restore`), pero no impide que el nodo arranque ni que el portal inicie el invitado.
- Los recibos `applied` de invitados borrados por caminos antiguos quedan en `/var/lib/nap-application-isolation`; son inofensivos y la unidad los ignora.
- El firewall de Proxmox del clúster está **desactivado** (sin `cluster.fw` ni `host.fw`; iptables en `ACCEPT`); sólo filtran las tablas `nap011_*` de cada instancia. Decidir si se activa para la universidad.

