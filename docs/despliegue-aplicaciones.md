# Despliegue de aplicaciones OCI y operación de infraestructura

Este documento describe la arquitectura, inventario de componentes, procedimientos
de preparación (preflight), operación y rollback del motor común Docker OCI
introducido en la feature 011.

---

## 1. Arquitectura del motor común OCI

El producto opera como un **AWS simple para la universidad**:
- **Catálogo unificado**: Dos entradas en la interfaz («Docker Hub» para imágenes públicas y «Referencia propia» para registries autorizados) que convergen en un **único motor de ejecución**.
- **Contenedores no privilegiados**: Cada servicio corre dentro de un contenedor Proxmox LXC no privilegiado con base Ubuntu 24.04 LTS, configurado con soporte para Docker anidado (`nesting=1`, `keyctl=1`), AppArmor y filtros seccomp estrictos.
- **Flujo simplificado**:
  1. Cátedra solicita la aplicación indicando propósito y fechas académicas (sin campos técnicos, UUIDs ni JSONs).
  2. Administración aprueba la solicitud con **reserva indivisible y atómica de capacidad** (cómputo y almacenamiento). No se crean contenedores ni reservas prematuras durante la solicitud.
  3. Despliegue automatizado: el worker descarga la imagen fijando el digest de arquitectura (`amd64`), genera secretos de aplicación seguros, levanta el contenedor OCI, configura el borde HTTPS (Caddy) y valida la salud HTTP antes de entregar el acceso.
  4. La cátedra accede a través del botón **«Ver acceso»**, mediante un gateway HTTPS seguro con tokens de un solo uso vinculados a la sesión de NAP, sin almacenar credenciales en el navegador ni requerir service workers.

---

## 2. Inventario y componentes instalados

| Componente | Versión / Tipo | Función | Ubicación / Puerto |
|---|---|---|---|
| **Host Virtualización** | Proxmox VE 9.2.2 (Kernel Linux) | Hipervisor y gestor de contenedores | `172.16.36.100:8006` (lab) |
| **Plantilla base** | Ubuntu 24.04 standard (`vztmpl`) | SO huésped para el contenedor LXC | Storage local Proxmox |
| **Motor OCI invitado** | Docker CE 27.x (daemon anidado) | Ejecución del contenedor de la aplicación | Interno al LXC de la cátedra |
| **Borde HTTPS** | Caddy v2 (reverse proxy) | Terminación TLS y proxy hacia puerto de app | Puerto `8443` HTTPS interno |
| **Aislamiento de red** | nftables (Linux bridge) | Filtrado L2/L3 por slot y bloqueo del host | Tabla bridge dedicada en `vmbr0` |
| **Gestión de secretos** | NAP System Keyring | Cifrado en reposo de claves y contraseñas | Base de datos (`credenciales_encrypted`) |
| **Spool / Supervisor** | systemd unit dinámico | Despacho seguro de trabajos y recolección | `/run/credentials/` (permisos 0600) |

---

## 3. Preparación del entorno y Preflight (`preparar_entorno.py`)

La herramienta de infraestructura `infra/laboratorio/011/preparar_entorno.py` automatiza la verificación y preparación repetible del nodo sin realizar cambios a ciegas:

### 3.1 Diagnóstico previo de solo lectura
Inspecciona herramientas instaladas, estado de AppArmor, plantillas relaciones y conectividad TCP/TLS al registry:
```bash
python infra/laboratorio/011/preparar_entorno.py \
  --diagnose \
  --manifest infra/laboratorio/011/candidatos.json \
  --config ~/.local/share/nap011/bootstrap-node.json
```

### 3.2 Preparación controlada del nodo (Bootstrap)
Prepara el namespace de configuración `/etc/nap/applications-011/`, registrando certificados CA, manifiestos de red y slots de IP autorizados con bloqueo atómico (`.lock`):
```bash
# Plan sin cambios (dry-run)
python infra/laboratorio/011/preparar_entorno.py \
  --manifest infra/laboratorio/011/candidatos.json \
  --config ~/.local/share/nap011/bootstrap-node.json

# Aplicación real (requiere root en el nodo)
sudo python infra/laboratorio/011/preparar_entorno.py \
  --manifest infra/laboratorio/011/candidatos.json \
  --config ~/.local/share/nap011/bootstrap-node.json \
  --apply
```

### 3.3 Instalación del paquete común del worker
Distribuye los módulos operativos (`job/`, `network.py`, `tls.py`, etc.) de forma aislada e independiente:
```bash
python infra/laboratorio/011/preparar_entorno.py \
  --install-package \
  --source-root . \
  --config ~/.local/share/nap011/bootstrap-node.json \
  --apply
```

---

## 4. Separación estricta: Laboratorio vs. Entorno Universitario

| Aspecto | Laboratorio Local (PC Mauro) | Entorno Universitario (Producción) |
|---|---|---|
| **Segmento de red** | `172.16.36.0/24` (VMware host-only / bridged) | Subredes académicas dedicadas definidas por DTI |
| **Puente Proxmox** | `vmbr0` local | `vmbr0` / VLANs troncales con tagging 802.1Q |
| **Slots IP fijos** | `172.16.36.81`–`.88` (`lab-linux-010`) | Rango CIDR asignado por perfil institucional |
| **Gateway y DNS** | GW `172.16.36.2`, DNS `172.16.36.2` | Gateways institucionales redundantes |
| **Registry de ensayo** | `https://172.16.36.1:5443` (CA privada local) | Registry seguro institucional o Docker Hub |
| **Nombres de dominio** | `*.nap-apps.test`, `app-<id>.nap-apps.test:8443` | Subdominios oficiales `*.universidad.edu.ar` |
| **Certificados TLS** | CA autofirmada de laboratorio en `~/.local/share/nap011/` | Certificados emitidos por AC institucional / Let's Encrypt |

> [!IMPORTANT]
> **Nunca copiar secretos, certificados ni tokens del laboratorio a la infraestructura universitaria.**
> La configuración de red universitaria debe completarse con sus propios valores, certificados y tokens emitidos por la dirección técnica institucional.

---

## 5. Procedimiento de Rollback y Recuperación

### 5.1 Reversión de configuración del nodo
Para retirar limpiamente los archivos de configuración y certificados en `/etc/nap/applications-011`:
```bash
# Simular rollback
python infra/laboratorio/011/preparar_entorno.py --rollback

# Ejecutar rollback definitivo
sudo python infra/laboratorio/011/preparar_entorno.py --rollback --apply
```

### 5.2 Baja segura de un servicio individual
Cuando un servicio finaliza su ciclo lectivo o se solicita su retiro:
1. Docente o admin selecciona **«Dar de baja»** en el portal.
2. La orden ejecuta la destrucción del contenedor en Proxmox (`vzdestroy`).
3. El worker verifica la ausencia física y lógica del contenedor y sus discos en el almacenamiento.
4. **Solo tras confirmar la ausencia total**, se libera la dirección IP estática en la contabilidad de red y se liberan las cuotas de vCPU, RAM y disco en el libro mayor (`CompromisoCapacidad`).
5. Si ocurre cualquier fallo durante la destrucción, el servicio pasa a estado `limpieza_pendiente` y **no se liberan** los recursos para evitar colisiones con futuros servicios.

### 5.3 Reintento de despliegue fallido
Si un despliegue experimenta un fallo transitorio de red o infraestructura:
1. El portal muestra el estado `fallida` con el motivo comprensible en lenguaje claro.
2. La consola administrativa ofrece el botón **«Reintentar despliegue»** (`POST /operaciones/{id}/reintentar`).
3. El reintento preserva los secretos originales del pedido aprobado, revalida la capacidad y despacha una nueva operación de tipo `reparar` sin generar estados inconsistentes ni duplicar contenedores.

