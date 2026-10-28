# Runner del nodo

## Paquete común de aplicaciones 011

El recorrido histórico sigue separado de `nap-application-job/1`. El paquete nuevo
requiere Python 3 y `python3-jsonschema` en el nodo. Desde un checkout revisado,
`bash infra/runner/install.sh --config /ruta/privada/runner.json` instala ambos
protocolos. Para una actualización anterior al primer recibo, aportar además
`--previous /ruta/privada/hashes-revisados.json`; los hashes deben provenir de la
revisión previamente instalada, nunca de aceptar automáticamente el destino actual.
El instalador rechaza versiones desconocidas, enlaces y trabajos activos o inciertos;
guarda respaldo y revierte si falla la importación del paquete instalado.

El laboratorio usa `infra/laboratorio/011/preparar_entorno.py --install-package
--source-root /checkout/revisado --config /ruta/privada/runner.json --previous
/ruta/privada/hashes-revisados.json`, primero sin `--apply` para consultar el plan y
luego con `--apply`. Esta acción no configura registry, red, cuentas ni perfiles.
El archivo inicial es `nap-application-node/1`, con cluster_uuid, node y profiles
vacío; la configuración existente se conserva. Los perfiles se validan por separado.

Para una instalación desde cero, ejecutar **primero** el asistente de acceso
corregido que se describe abajo y **después** `install.sh`, desde la misma revisión.
El bootstrap incluye `registry_entries.py`; no requiere instalar antes el paquete 011.
Si sólo se copiaron imágenes/recetas a `/var/lib/vz/template/cache` y `/opt/nap/recipes`,
el instalador no las modifica. Sí verifica código previo y rechaza versiones
desconocidas o trabajos activos/inciertos; no eludir esas guardas borrando estado.

El JSON de entrada de `--config` lleva exactamente `schema_version`, `cluster_uuid`,
`node` y `profiles: {}`. Prepararlo fuera del destino, con root propietario y modo
0600; el instalador escribe `/etc/nap/applications-011/runner.json`. El campo opcional
`networks` se admite posteriormente en runtime, no en el documento de bootstrap.
La instalación conserva perfiles/redes existentes coherentes y no habilita perfiles.

Estados/tombstones/spool quedan en `/var/lib/nap-application-jobs` (0700). Las
credenciales se entregan por un archivo 0600 en `/run/nap-application-jobs`, que
systemd copia a su espacio privado mediante LoadCredential. El worker confirma
durablemente la carga y retira el origen antes de ejecutar la estrategia; systemd
retira su copia al finalizar. Una regla tmpfiles recrea el directorio tras reiniciar.
Ni stdin/stdout/stderr de la unidad ni propiedades/argv/journal contienen valores.
El instalador y `selfcheck.py` son herramientas explícitas de root, sin acciones
equivalentes en el protocolo del portal. La autocomprobación prueba mecanismos
comunes; no certifica perfiles ni despliegues completos de aplicaciones.

El wrapper y los ejemplos requieren instalación institucional explícita en T101. El backend integra T095 y bloquea la preparación si faltan sus artefactos, destinos o red. Las pruebas locales no acreditan una instalación en Proxmox.

`install.sh` copia código revisado como root a `/opt/nap/runner` y el wrapper a `/usr/local/sbin/nap-guest-runner`. No ejecutar sobre el equipo de desarrollo. Copia el protocolo estándar de `backend/app/schemas/guest_runner.py` como `protocol.py`, sin dependencia de FastAPI/SQLAlchemy en el nodo. Instalar desde un checkout que incluya todos los cambios; no copiar módulos aislados de revisiones distintas.

El operador debe crear una cuenta dedicada `naprunner`, sin contraseña ni grupos administrativos, con home y authorized_keys controlados por root. `authorized_keys.example` y `sshd_config.example` restringen origen, comando, PTY y forwarding; sustituir sus marcadores y comprobar `sshd -t`. La shell de la cuenta permite únicamente a sshd ejecutar ForceCommand; no habilitar otro método de entrada. `sudoers.example` permite exclusivamente el wrapper sin argumentos. Validar con `visudo -cf` y usar permisos root:root 0440. No activar grabación de stdin/stdout para esa orden: transporta secretos de instancia. Estos ejemplos no se aplican automáticamente.

### Asistente de instalación inicial

`configure_access.py` prepara esos archivos a partir de **una clave pública Ed25519** y la dirección concreta del worker. Sin `--apply` solo imprime el plan, incluso en el equipo de desarrollo:

```bash
python3 infra/runner/configure_access.py --worker-ip IP_DEL_WORKER \
  --node-ip IP_DEL_NODO --public-key /ruta/worker.pub
```

Para aplicar, copiar el código revisado y el protocolo a un directorio root seguro del nodo y ejecutar allí el mismo comando con `--apply`. Requiere `sudo`, `sshd`, `visudo` y las herramientas PVE existentes; no instala paquetes automáticamente. Rechaza cuentas/grupos, archivos o estado anteriores y enlaces en las rutas. No lo utilice para actualizar o reparar una instalación existente.

Ante una preparación manual o fallida, revisar primero cuenta/grupo, concesiones
sudo y grupos administrativos, claves/fragmentos SSH, archivos y directorios de
estado creados. Quitar una cuenta no limpia el resto. Retirar únicamente restos
identificados de ese intento, con respaldo y consola root disponible; nunca borrar
en bloque `/opt/nap`, `/etc/nap` o estado de recursos existentes. Las imágenes y
recetas son independientes del acceso SSH y deben conservarse.

Crea `naprunner` con contraseña bloqueada, home root y claves públicas en `/etc/nap/runner/authorized_keys`. Restringe la clave al origen y el comando, desactiva otras fuentes de claves/CA para esa cuenta y solo autoriza sudo sobre el wrapper sin argumentos. El registro comienza vacío: la conexión no habilita recetas ni productos. Antes de recargar SSH contrasta `visudo`, sintaxis y configuración efectiva de sshd, comprueba que root conserva su configuración anterior y ejecuta un JSON inválido como naprunner para verificar el wrapper sin tocar invitados. Si falla, retira únicamente los archivos nuevos. Puede quedar la cuenta bloqueada y directorios privados; conservar la consola root y revisar antes de reintentar, sin borrar estado de otra instalación.

Ensayo adicional explícito de instalación con OpenSSH/sudo reales dentro de un contenedor Debian descartable, **sin PVE ni red durante la ejecución**:

```bash
docker build -f infra/runner/tests/setup-sandbox.Dockerfile -t nap009-runner-setup-test .
docker run --rm --network none -e NAP_SETUP_SANDBOX=1 \
  --mount type=bind,source="$PWD/infra",target=/source/infra,readonly \
  --mount type=bind,source="$PWD/backend/app/schemas",target=/source/backend/app/schemas,readonly \
  --mount type=bind,source="$PWD/backend/app/utils",target=/source/backend/app/utils,readonly \
  nap009-runner-setup-test python3 /source/infra/runner/tests/setup_sandbox.py
```

La descarga de paquetes se realiza solo al construir la imagen de prueba. El ensayo comprueba también SSH por loopback con claves efímeras, origen rechazado, ForceCommand y forwarding denegado; adapta únicamente el origen del fixture para el caso positivo. `pct`, `pvesh` y la recarga de servicio son dobles; no acredita SSH hacia la VM ni revocación de consolas docentes. Para el laboratorio actual ver [la preparación guiada](../../docs/evidencia/009/laboratorio-local.md).

## Registro institucional

Crear `/etc/nap/runner/registry.json` root:root 0600, con objeto indexado por `definition_key:definition_version`. Cada entrada tiene `product`, `definition_sha256`, `bundle_sha256`, `bundle_path` absoluto, `cluster_uuid`, `nodes`, `network_profile_ids` y `networks`. El bundle debe ser archivo regular root, sin enlaces ni escritura de grupo/otros, conservado con su SHA-256 original. Una retirada ordinaria no elimina este artefacto; `security_blocked: true` bloquea expresamente su ejecución.

`networks` es un objeto por ID institucional. Cada perfil declara `subnets`: CIDR de las direcciones guest que pueden inspeccionarse, nunca ruta por defecto. PostgreSQL/BookStack añaden `client_cidrs` y `instances`, un objeto por resource_uuid previamente autorizado. Cada instancia contiene `host`, `address`, `tls_certificate_path`, `tls_private_key_path`, `tls_ca_path`, con archivos regulares root en directorios seguros. La clave debe ser 0600. Los certificados y claves son por instancia; no compartir una clave wildcard entre invitados. El runner solo lee estos archivos en bootstrap; inspect/verify transmiten únicamente host, dirección y CIDR públicos.

Los endpoints no se obtienen del cliente del portal: el operador proporciona DNS, asignación de dirección, CA/certificado y conectividad reales antes de habilitar el destino. La dirección debe estar presente en `ip -json address show` del guest y dentro de subnets. No hay IPAM, emisión de certificados, NAT ni cambios de red automáticos.

## Identidad, ejecución y fallos

La descripción del LXC debe ser JSON con `nap` y exactamente `cluster_uuid`, `resource_uuid`, `pool`, `nonce_sha256`, `definition_sha256`, `bundle_sha256`. El pool y nodo se contrastan además con inventario PVE, y el recurso debe ser LXC no privilegiado. Los registros históricos con marcas incompletas no habilitan bootstrap. T095 integra estas marcas nuevas en el backend.

Cada push/exec comprueba identidad antes y después mediante comandos PVE fijos. Los bundles se vuelven a verificar sobre los mismos bytes copiados a una carpeta temporal privada. Solo se extraen common.py/bootstrap.py y configure.php en BookStack, sin rutas o comandos elegidos por el solicitante. La configuración de instancia se transmite por stdin; no se escribe en argv, logs o respuestas. El guest limpia los archivos temporales del bundle al terminar y conserva únicamente configuración necesaria de aplicación y estado privado. Una interrupción forzada puede dejar un directorio de receta sin secretos bajo `/run/nap-runner`; se elimina al reiniciar el guest.

`/var/lib/nap-runner` y temporales usan 0700, clave HMAC/estado/locks 0600. Conservar estado y clave juntos en copias institucionales. Los registros contienen huellas HMAC, fases y UUID de operación, sin contraseñas ni nonce original. Un flock por recurso excluye operaciones simultáneas, incluso con otros UUID de operación. El intento se persiste antes de enviarse. Tras timeout/corte se inspecciona la preparación; solo un resultado completo y saludable permite confirmar. Un guest completo sin historia del host no se adopta por inferencia. Un intento parcial incierto permanece bloqueado hasta investigación; no se vuelve a ejecutar a ciegas, no se recrean recursos ni se regeneran claves.

El proceso tiene deadline de 170 s; OpenSSH del cliente limita la llamada a 180 s. La entrada JSON se limita a 64 KiB y su lectura a diez segundos. El drenaje de salida host tiene límite y timeout, descarta stderr y termina el grupo de procesos local al vencer. Eso no acredita que el guest haya terminado: se conserva la incertidumbre y el lock de preparación guest protege su ejecución.

## Comprobación

Desde la raíz:

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests
```

Pruebas locales con dobles, sin SSH/PVE ni procesos reales. El ensayo de instalación debe comprobar hostkey cambiada, forced-command, sudo sin argumentos, intento de escape/comando libre, pool ajeno, nonce/digests alterados, cambio de identidad durante una orden, deadline, reinicio del runner y limpieza. No declarar habilitado el nodo antes de registrar evidencia real de T101.
