# Infraestructura de laboratorio: cluster Proxmox + TrueNAS + portal

Runbook de lo construido en el laboratorio local (27/10/2026) para **repetirlo en servidores reales**.
No contiene secretos: tokens, contraseñas, llaves privadas y el dump de la base viven fuera del repo.

> Estado al cierre: nodos, cluster, almacenamiento compartido, artefactos y conexión de la API del portal
> a Proxmox **funcionan**. El **runner** y la **identidad del cluster** están **bloqueados** esperando respuesta
> de Mauro (sección 9).

## 1. Topología

| Elemento | Valor en laboratorio | En servidores reales |
|---|---|---|
| Nodos | 4 VMs VirtualBox con Proxmox VE 9.2.2 (Debian 13 *trixie*) | 4 servidores físicos/VM institucionales |
| Red | `192.168.100.0/24`, gateway `192.168.100.1`, adaptador **puente** | red de gestión institucional |
| `frt` | `192.168.100.90` (FQDN `frt.utn.edu.ar`) | — |
| `pve91`, `pve92`, `pve93` | `192.168.100.91` a `.93` | — |
| TrueNAS | `192.168.100.94` | servidor de almacenamiento dedicado |
| PC del portal/operador | `192.168.100.89` | servidor del portal |
| Cluster | `nap-lab`, creado en `frt`, 4 votos, quórum 3 | nombre institucional |

Los nombres de nodo del `.env`/perfiles tienen que ser **exactamente** los de `pvecm nodes`.

## 2. Orden de implementación

1. Instalar Proxmox en cada nodo y fijar **IP, hostname y `/etc/hosts` antes de crear el cluster**.
2. Dejar los nodos con DNS y repositorios funcionando (`scripts/preparar-nodo.sh`).
3. Crear el cluster en un nodo y unir los demás.
4. Instalar TrueNAS, crear el export NFS y agregarlo como storage compartido.
5. Crear el token de API en Proxmox.
6. Instalar los artefactos (imágenes y bundles) en cada nodo.
7. Levantar el portal y conectarlo a Proxmox.
8. Runner, identidad del cluster y pool de aplicaciones (pendiente, sección 9).

## 3. Nodos Proxmox

### Hostname, IP y `/etc/hosts`
- Cada nodo necesita **hostname único** y su propia IP. Clonar una VM deja nombre e IP repetidos: cambiarlos
  antes de unir al cluster.
- IP: `/etc/network/interfaces`, bloque `vmbr0` (`address 192.168.100.9X/24`, `gateway 192.168.100.1`),
  luego `ifreload -a` o reiniciar. Hacerlo por la consola, no por SSH.
- `/etc/hosts`: la línea del nodo debe tener **su IP nueva** y su hostname
  (`192.168.100.91 pve91.utn.edu.ar pve91`). Si queda con otra IP, fallan `pveproxy` y `pvedaemon`.
- Cambiar hostname: `hostnamectl set-hostname NOMBRE`, editar `/etc/hosts`, reiniciar. Solo es simple
  con el nodo **vacío y sin cluster**.

### DNS y repositorios (`scripts/preparar-nodo.sh`)
Problemas reales que aparecieron:
- `resolv.conf` apuntaba a `172.16.36.1` (red anterior). Con ping a `8.8.8.8` funcionando, `apt` fallaba con
  `Temporary failure resolving`. Síntoma engañoso: `apt-get update` se **cuelga** en vez de fallar rápido.
- Los repos `pve-enterprise` y `ceph` (enterprise) requieren suscripción: se reemplazan por
  `pve-no-subscription` (suite `trixie` para PVE 9, `bookworm` para PVE 8). **Solo laboratorio**; con
  suscripción no se tocan.
- `sudo` no viene instalado en el nodo.

Persistir el DNS también en la interfaz: nodo → System → DNS.

## 4. Cluster

```bash
# En el primer nodo (frt)
pvecm create nap-lab
# En cada uno de los otros (contraseña de root del primero)
pvecm add 192.168.100.90
# Verificar
pvecm nodes ; pvecm status      # 4 nodos, Quorate: Yes
```

Errores encontrados:
- `can't add existing node 'frt'`: el nodo a unir tenía el **mismo hostname** que otro. Renombrar y reiniciar.
- Un nodo con VMs/CTs no puede unirse.
- Con 4 nodos, si caen 2 se pierde el quórum (necesita 3). Recuperación de emergencia: `pvecm expected 1`.

## 5. TrueNAS y almacenamiento compartido

**VM (prototipo):** 4 GB RAM, 2 vCPU, disco de arranque 16 GB, un disco de datos de 30 GB, red puente,
IP fija `192.168.100.94/24`, gateway `192.168.100.1`, DNS `192.168.100.1` + `8.8.8.8`, hostname `truenas`,
dominio `utn.edu.ar`. Los discos de datos van **aparte** del de arranque.

**Pasos en TrueNAS:**
1. Pool `tank` (layout *Stripe* en el prototipo, sin redundancia).
2. Dataset `tank/proxmox` (tipo *Generic*): queda en `/mnt/tank/proxmox`.
3. Share NFS de ese path con red autorizada `192.168.100.0/24` y **Maproot User = root, Maproot Group = root**
   (sin esto Proxmox no puede escribir). Activar el servicio NFS con inicio automático.
4. Probar desde un nodo: `showmount -e 192.168.100.94`.

**En Proxmox (una vez, vale para todo el cluster):**
```bash
pvesm add nfs truenas --server 192.168.100.94 --export /mnt/tank/proxmox \
  --content images,rootdir,iso,vztmpl
pvesm status        # truenas = active en los 4 nodos
```

**Verificado:** el storage `truenas` está `active` en los 4 nodos, es realmente compartido (cada nodo ve los
archivos de los otros), se escribe como `root` y ofrece unos 28 GiB.

**Desactivar `local-lvm`** una vez que `truenas` funcione y sin guests ahí: `pvesm set local-lvm --disable 1`
(reversible con `--disable 0`). *Indicado pero no verificado en esta sesión.*

Notas:
- Achicar discos VirtualBox no es práctico (solo se agrandan). Se dejaron como están.
- Los **artefactos** (imágenes/recetas) siguen en el storage `local` de cada nodo, no en `truenas`:
  el diseño registra réplicas por nodo (`replicas_artefacto`) y las rutas están fijas en el script.

**Para servidores reales:** mínimo 8 GB de RAM (ideal más, con ECC), mirror o RAIDZ, restringir el export a
las IPs de los nodos (no a toda la red), red de almacenamiento separada si es posible, y subir los márgenes de
`INFRASTRUCTURE_PROFILE` según el espacio real del dataset.

## 6. Token de API de Proxmox

Datacenter → Permissions → API Tokens → Add. En laboratorio se usó `root@pam!token-nap`.
Verificación: `GET https://NODO:8006/api2/json/nodes` con cabecera
`Authorization: PVEAPIToken=USUARIO!NOMBRE=VALOR` debe listar los 4 nodos `online`.

**Para servidores reales** el contrato (`docs/conexion-infraestructura.md`) pide cuenta/token dedicado con
privilegios mínimos, CA pública verificada y `proxmox_verify_ssl=true`. `root@pam` y `verify_ssl=false` son
solo de laboratorio.

## 7. Artefactos (`scripts/instalar-artefactos-nodos.sh`)

Qué son (deducido de los archivos y del script; el código que los consume no está completo en el repo):
- **Imágenes** `nap009-<producto>-1.0.0.tar.gz` → `/var/lib/vz/template/cache/` (plantillas de contenedor LXC).
- **Bundles** `nap009-<producto>-1.0.0-<sha256>.tar.gz` → `/opt/nap/recipes/` (recetas de preparación).
- Productos: `linux`, `postgresql`, `bookstack`. Tres imágenes (57/142/163 MB) y tres bundles (5 a 10 KB).

Origen: carpeta `~/.local/share/nap009` (entregada por Mauro) con `artifact-index.json` e
`instalar_artefactos.py`. El instalador **no sobrescribe**, verifica hash y tamaño contra el índice
(hash del índice usado: `be1adb42254a8609cd9164cb8512985cb2b829a9d0fb0cf20fc448180f70b992`), exige origen de
root sin permiso de escritura de grupo/otros, y no registra ni habilita nada.

Problemas encontrados:
- El script rechazaba la carpeta por estar en `775`: dejarla en `755` (`chmod g-w`).
- Instalado en los 4 nodos con `"estado": "artefactos_copiados"`.
- Un `!comando` dentro de Claude Code **no tiene terminal**: SSH no puede pedir contraseña.

## 8. Portal (rama `011-desplegar-servicios-universitarios`)

El dump (`nap-traspaso-db-2026-10-27.tar.gz`) **no** va a `master`: su esquema (`011_01_despliegue_aplicaciones`)
solo existe en la rama 011. Seguir `docs/traspaso-011.md`:

```bash
git switch -c 011-desplegar-servicios-universitarios --track origin/011-desplegar-servicios-universitarios
D=~/.local/share/nap-traspaso ; umask 077 ; mkdir -m 700 $D
tar -xzf nap-traspaso-db-2026-10-27.tar.gz -C $D --no-same-owner ; chmod 600 $D/*
python3 scripts/traspaso.py verify --directory $D
python3 scripts/traspaso.py init --keyring $D/keyring.json
docker compose -p nap-handoff -f docker-compose.handoff.yml build
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d --wait db
python3 scripts/traspaso.py restore --directory $D
docker compose -p nap-handoff -f docker-compose.handoff.yml run --rm --no-deps api alembic upgrade head
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d
```
Portal `http://localhost:5174`, API `http://localhost:8001/api/docs`, Mailpit `http://localhost:8025`.
No ejecutar `alembic upgrade head` antes del restore. Si el restore falla, no borrar volúmenes.

### Conexión a Proxmox con `NAP_SETTINGS_FILE`
`settings_from_file` exige archivo regular, `0600`, **del mismo usuario que el proceso**. La API corre como
UID 10001, por eso el override fija `user: "1000:1000"` (el UID del host). Archivos (fuera del repo, `0600`):

`~/.local/share/nap009/settings.json` (solo conexión; sin perfiles de identidad):
```json
{"proxmox_host": "192.168.100.90", "proxmox_port": 8006, "proxmox_user": "root@pam",
 "proxmox_token_name": "token-nap", "proxmox_token_value": "<SECRETO>", "proxmox_verify_ssl": false}
```
`~/.local/share/nap009/compose-api-lab.yml`:
```yaml
services:
  api:
    user: "1000:1000"
    environment:
      NAP_SETTINGS_FILE: /run/nap/settings.json
    volumes:
      - /home/ivan/.local/share/nap009/settings.json:/run/nap/settings.json:ro
```
Levantar con ambos compose: `docker compose -p nap-handoff -f docker-compose.handoff.yml -f ~/.local/share/nap009/compose-api-lab.yml up -d`.
Verificado: desde el contenedor, `proxmoxer` lista los 4 nodos `online`.

El `backend/.env` (esquema de `master`) también se adaptó (rutas a `/home/ivan`, 4 nodos, storage `truenas`
compartido con márgenes de 2 GiB, `PROXMOX_*`), pero **la pila de traspaso no lo usa**.

## 9. Respuestas de Mauro (27/10/2026) y pendientes

### Runner: causa confirmada
Mauro confirmó el diagnóstico. `configure_access.py` quedó con el paquete inicial de la 009 y el runner ahora importa
`registry_entries.py` (`backend/app/utils/artifact_registry.py`, instalado como `/opt/nap/runner/registry_entries.py`).
En su VM se instaló primero el asistente antiguo y luego se actualizaron los paquetes; por eso la suya funciona y la
secuencia desde cero falla. **No hay una versión más nueva del asistente.**
- Solución indicada: **corregir el bootstrap** para que instale todas sus dependencias y **después** instalar el paquete
  común 011 (`install.sh`). No crear la cuenta a mano ni saltear verificaciones.
- El rollback del asistente retira los archivos nuevos pero **no elimina la cuenta/grupo** `naprunner` creados durante la
  comprobación: revisar y limpiar (lo hace `scripts/reinstalar-runner.sh`).

### Identidad del cluster
- Generar **un UUID propio**, compartido por los 4 nodos. No usar el de Mauro. Se llama `cluster_id` en configuración
  y `cluster_uuid` en el protocolo del runner.
- UUID del laboratorio (no es secreto): `0d69119f-054a-40b3-b3c1-4b1b2c707917`. En servidores reales, generar otro.
- Los registros importados ligados al laboratorio de Mauro se conservan como **históricos**: no reemplazar sus UUID con
  actualizaciones masivas ni adoptarlos como recursos de los nodos propios.
- Los archivos de imágenes/recetas se pueden reutilizar verificando hashes, pero **las validaciones de infraestructura
  no se transfieren**: hay que registrar y validar perfiles, destinos y ofertas propios. Usuarios, cátedras y calendario
  pueden conservarse.

### Acceso al portal
Coordinar por privado el acceso a un administrador existente y desde esa cuenta crear el administrador personal.
`bootstrap_admin` solo sirve en una instalación **sin** administradores: con el dump actual lo rechaza (aunque el admin
esté inactivo). No borrar cuentas para forzarlo.

### `runner.json` mínimo por nodo (sin perfiles habilitados)
```json
{"schema_version": "nap-application-node/1", "cluster_uuid": "<UUID-PROPIO-DEL-CLUSTER>",
 "node": "frt", "profiles": {}}
```
El documento de **entrada** de `--config` lleva exactamente esos cuatro campos, **sin `networks`** (Mauro lo corrigió el
28/10); propietario root, modo 0600. El instalador escribe el destino `/etc/nap/applications-011/runner.json`.
En los otros nodos cambia `node` (`pve91`, `pve92`, `pve93`); el UUID es el mismo. Redes y perfiles se agregan después
en el `runner.json` instalado (ver "Avance del 28/10"), con configuración propia comprobada.

### Dependencias del nodo
`python3-jsonschema`, `python3-cryptography`, `sudo`, `openssl`, `nftables`, SSH y systemd, más `pct` y `pvesh`
(parte ya viene con Proxmox). **Docker se instala dentro del LXC de aplicación, no en los nodos.**

### Pool de PostgreSQL/BookStack
En la 009 Mauro lo preparó con configuración privada de laboratorio (identidades y MAC distintas, direcciones reservadas
fuera del DHCP, certificados por instancia); no son valores para copiar. Para la 011 se usará el **asignador de slots**
con identidades nuevas y TLS por instancia; esa integración **todavía está pendiente** de completar y validar.

### Cambio de alcance de la spec 011
Se simplificó: **Community Scripts queda fuera**; Docker Hub será la biblioteca y las imágenes propias usarán el mismo
motor OCI. Ya no hacen falta los pilotos Community (MariaDB/Caddy) ni reproducir PostgreSQL/BookStack históricos.
Actualizar la rama hasta el commit **`26e52a3`** cuando esté publicado (a las 22:5x del 27/10 aún no lo estaba:
`origin/011-...` seguía en `0167202`).

### Avance del 28/10/2026
Mauro corrigió el bootstrap en `4bc7a51` (`registry_entries.py` en `configure_access.py`). Con la rama 011 al día:
1. **Limpieza** de los 4 nodos (con respaldo en `/root/nap-limpieza-<nodo>`): se retiró la cuenta/grupo `naprunner`
   y los directorios vacíos que dejó el asistente en `frt`; en `pve91..93` se retiró además el `sudoers` con
   `NOPASSWD:ALL` y el home con su `authorized_keys`. Imágenes, recetas y `/home/tom` no se tocaron.
2. **Asistente corregido** con `--apply` en los 4 nodos, desde una copia de `git archive` de root sin escritura de
   grupo/otros (`chmod -R go-w`), con `--worker-ip 192.168.100.89` (la IP que ven los nodos). Prueba SSH con la clave
   del worker: `INVALID_REQUEST` del wrapper en los 4 (también desde el contenedor de la API).
3. **Paquete 011** con `infra/runner/install.sh --config` (JSON inicial de 4 campos): `installed`, sin perfiles
   habilitados ni invitados; mismo `code_sha256` en los 4 nodos.
4. **Plantilla base en TrueNAS** (decisión de laboratorio): `pveam download truenas ubuntu-24.04-standard_24.04-2_amd64.tar.zst`
   (sha256 `75a827c4…`), visible desde los 4 nodos. Cambia `volumen_lxc` a `truenas:vztmpl/…` en
   `infra/applications/profiles/docker/ubuntu24.json` (la 011 de Mauro usa `local:`; **cambio local, no commiteado**)
   y obliga a reinstalar el paquete (cambia `policy_bundle_sha256`).
5. **Perfil y red** registrados en el `runner.json` de cada nodo (respaldo `/root/runner-<nodo>.antes.json`): perfil
   `docker-ubuntu24:1` en `pendiente_validacion` y red `lab-applications-011` (slots `.100–.119`, DNS `192.168.100.1`,
   `peer_cidrs` `192.168.100.0/24`). La red del nodo tiene otro esquema que la del portal (`nodes`, `bridge`,
   `client_cidrs`, `management_addresses`, `peer_cidrs`, `endpoints`, `slots`).
6. **Portal** (`backend/.env` privado, cluster_id `0d69119f-…`): la pila `nap-handoff` fija esos valores en `{}`, por lo
   que se usa un override privado adicional (`compose-api-011.yml`) con `INFRASTRUCTURE_PROFILE`, `RUNNER_NODES`,
   `NETWORK_PROFILES`, `APPLICATION_PROFILES` y `APPLICATION_NETWORK_PROFILES`, el montaje de la clave SSH y un
   `/etc/passwd` con el UID 1000 (sin esa entrada `ssh` falla dentro del contenedor).

### Pendiente
- Terminar T044–T047 (motor Docker de la 011: `deploy.py`, `access.py`/`probes.py`, orquestación) y T050: el perfil
  no se habilita antes. Las compuertas de `infra/laboratorio/011/` están fijas al laboratorio de Mauro (nodo `proxmox`,
  VMID 900011, `local-lvm`, registry privado `172.16.36.1:5443`) y no sirven tal cual aquí.
- Decidir con Mauro dónde vive la plantilla base (`local:` por nodo o `truenas:` compartido).
- Capacidad: `truenas` tiene ~28,6 GiB y el perfil reserva 2 GiB de margen; entran ~3 servicios de 8 GB.
- Acceso admin: ya resuelto con Mauro (cuenta personal creada).

## 10. Lecciones operativas

- Pegar bloques con `heredoc` en la terminal suele **romperse** (indentación, saltos de línea): preferir scripts
  en archivo.
- Un `apt-get` colgado deja el lock tomado: matar el proceso antes de reintentar.
- `ssh` lee de stdin: un `bash -s` con `apt-get` adentro puede consumir el resto del script. Usar `</dev/null`.
- Los warnings de `perl`/locale por `LC_*` enviados por SSH son inofensivos (`LC_ALL=C`).
- Los comodines (`*.tar.gz`) los expande el shell de quien llama: con `sudo` hay que usar `sudo sh -c '...'`.

## 11. Qué NO está en este repo

Token de Proxmox, `settings.json`, llaves SSH (`~/.local/share/nap009/ssh/`), el dump y el keyring
(`~/.local/share/nap-traspaso/`), el `.env` de la raíz y los `.tar.gz` de artefactos.
