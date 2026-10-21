# Carga revisada de artefactos del laboratorio

`instalar_artefactos.py` copia las tres imágenes y sus tres bundles. No crea invitados, publica definiciones ni cambia cuentas, permisos, red o registro del runner. Es un paso parcial de T101; no es prueba de acceso ni aceptación de aplicaciones.

Entrada: directorio privado con `artifact-index.json` de esquema 1 y seis archivos regulares, sin enlaces ni escritura de grupo/otros. El índice sólo elige `product` (linux/postgresql/bookstack), `kind` (image/bundle), SHA-256 y tamaño; no elige rutas ni comandos. Los destinos son constantes:

- Imágenes: `/var/lib/vz/template/cache/nap009-PRODUCTO-1.0.0.tar.gz`.
- Bundles: `/opt/nap/recipes/nap009-PRODUCTO-1.0.0-SHA256.tar.gz`.

El primer destino corresponde al almacenamiento `local` de la VM actual, comprobado por API como `type=dir`, `path=/var/lib/vz`, con `vztmpl`. No asumirlo en otro clúster: revisar/adaptar el instalador y generar un paquete nuevo antes de usarlo allí.

Sin `--apply` inspecciona sin crear directorios. Con `--apply` exige root en PVE, lock privado, verificación de los seis archivos antes de escribir y comprobación de los mismos bytes copiados. Publica cada archivo de forma exclusiva y modo 0444. Un destino con otro contenido, enlace o permisos inseguros aborta; no se reemplaza. Repetir con el mismo contenido es idempotente. Si falla, retira sólo sus archivos nuevos cuyo inode conserva y deja intactos los anteriores. Pueden quedar directorios nuevos vacíos.

```bash
python3 -I instalar_artefactos.py --source DIRECTORIO_PRIVADO \
  --index-sha256 SHA256_REVISADO
# Aplicar únicamente en el nodo, después de revisar el plan:
python3 -I instalar_artefactos.py --source DIRECTORIO_PRIVADO \
  --index-sha256 SHA256_REVISADO --apply
```

Para esta VM se preparó fuera del repositorio `cargar-artefactos-en-proxmox.sh`: comprueba el SHA del tar local, usa la hostkey SSH ya verificada y pide la contraseña root sólo en la terminal del usuario. Recibe el tar por stdin en un temporal root privado, verifica SHA de paquete/instalador, extrae el paquete conocido, ejecuta la copia y limpia su temporal. No contiene contraseñas, claves privadas ni `.env`; no instala paquetes ni recarga SSH.

El paquete y sus hashes están identificados en [carga-artefactos-preparada.json](../../docs/evidencia/009/carga-artefactos-preparada.json). Se verificaron sus ocho miembros regulares, la extracción y un plan readonly con los seis artefactos reales. El usuario ejecutó el lanzador el 21 de octubre y compartió «Carga terminada»: los seis archivos se copiaron con hashes correctos. Se conservan el [recibo root](../../docs/evidencia/009/carga-artefactos-recibo.json) y la [lectura independiente de la API](../../docs/evidencia/009/carga-artefactos-pve.json), que reconoce las tres imágenes y sus tamaños. La API no comprueba los bundles ni los hashes. El instalador no modifica la condición `estado=preparado_no_ejecutado_en_pve` del recibo del repositorio: registrar por separado lo efectivamente observado al ejecutarlo.

Pruebas sin PVE/SSH/red/procesos externos:

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini infra/laboratorio/tests -q
```

Diez pruebas aprobadas, incluyendo umask 022/077, idempotencia, rollback, rechazo de enlaces/permisos/rutas y aplicación no root. Regresión conjunta runner/services/laboratorio: 83 aprobadas, cuatro integraciones opcionales omitidas, 2,68 s. Estas pruebas locales no acreditan los ensayos T101/T102; la transferencia real se documenta por separado en los recibos anteriores.

## Acceso API temporal para staging

`configurar_api_ensayo.py` prepara un acceso separado del token root de desarrollo. El plan se contrastó con la API real sin escribir: no había colisiones de cuenta, roles o pool; [plan observado](../../docs/evidencia/009/api-ensayo-plan.json). La aplicación en el nodo está **pendiente de la ejecución manual del usuario**; [identificación del instalador](../../docs/evidencia/009/api-ensayo-preparado.json).

| Objeto nuevo | Alcance |
|---|---|
| `nap009lab@pve`, token `ensayos` | Sin contraseña; cuenta y token vencen a los 30 días; separación de privilegios activa |
| `NAP009LabAudit` en `/` | `VM.Audit`, `Sys.Audit`, `Datastore.Audit`: lectura global necesaria para inventario y capacidad |
| `NAP009LabGuest` en `/pool/nap009-staging` | Auditoría del pool; asignar, configurar y encender/apagar sus invitados |
| `NAP009LabDisk` en `/storage/local-lvm` | Asignar espacio en ese almacenamiento; PVE concede este permiso al almacenamiento completo |
| `NAP009LabBridge` en `/sdn/zones/localnetwork/vmbr0` | Usar el bridge existente, sin modificar su configuración |

Cada concesión se aplica tanto al usuario como al token. No se concede `Sys.Modify`, `Permissions.Modify`, `Pool.Allocate` ni `VM.Console`. No se concede escritura global sobre `/vms`. El pool se crea vacío y no se incorporan los invitados 101/103. Este acceso sirve para staging: los pools de cátedra y las consolas docentes requieren preparación y ensayos separados.

El CLI exige root/PVE. Antes de crear objetos verifica por TLS la IP `172.16.36.100`, usando el certificado público de CA del propio nodo, y rechaza colisiones. El plan predeterminado sólo lee; `--apply` crea la cuenta inicialmente deshabilitada, guarda el secreto en `/root/nap009-api-ensayos.json` nuevo con modo 0600, configura ACL y habilita al final. Ante un fallo posterior intenta deshabilitar sólo la cuenta cuya creación confirmó. Conserva estado para diagnóstico y no borra objetos ni reintenta tareas inciertas. Si falla esa deshabilitación, necesita intervención del operador. Un timeout inicial de creación deja la cuenta solicitada deshabilitada. No hay rollback destructivo automático.

El lanzador privado `preparar-api-ensayos-en-proxmox.sh` envía una copia del instalador con SHA fijado mediante la hostkey SSH ya verificada. El usuario escribe la contraseña root en su terminal. La respuesta con token y CA se captura bajo `/home/mauro/.local/share/nap009/api-ensayos/`, directorio 0700 y archivos de respuesta 0600; no se imprime. Se exporta únicamente el certificado público de CA, nunca su clave privada. La exportación del CLI está reservada a stdout capturado, sin terminal. No compartir esos JSON ni incorporarlos al repositorio. La configuración backend existente no se modifica; el resultado requiere después verificar permisos efectivos y lecturas HTTPS con el nuevo token.

Las concesiones y comandos se revisaron contra fuentes primarias de Proxmox: [tokens y sesiones](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc), [creación LXC](https://github.com/proxmox/pve-container/blob/master/src/PVE/API2/LXC.pm), [permisos de configuración](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm), [uso de bridge](https://github.com/proxmox/pve-guest-common/blob/master/src/PVE/GuestHelpers.pm) y [acceso a plantillas](https://github.com/proxmox/pve-storage/blob/master/src/PVE/Storage.pm). La documentación advierte que deshabilitar una cuenta no termina sesiones de consola ya abiertas; este paso no acredita su revocación.

Nueve pruebas nuevas aprobaron: plan sin efectos, alcance declarado, colisiones, salida sin secreto, permisos del archivo, preservación de invitados, rechazo de enlaces y fallos con cuenta deshabilitada/secreto recuperable. Regresión infra completa: **92 aprobadas, cuatro integraciones opcionales omitidas, 2,60 s**, log `/tmp/nap009-infra-api-ensayo.log`. Son pruebas con un doble de PVE; no acreditan ACL reales ni T101/T102. No se ejecutó el lanzador remoto desde las herramientas.


### Primer intento y corrección TLS

El usuario ejecutó el lanzador inicial y recibió «Preparación no confirmada». Su respuesta privada quedó vacía (0600); no se imprimió ni se obtuvo un token. La [consulta posterior de la API](../../docs/evidencia/009/api-ensayo-diagnostico.json) no encontró la cuenta, ninguno de los cuatro roles ni el pool. El certificado público presentado por `172.16.36.100` aún incluía `192.168.1.2` y omitía la IP actual. La lectura del certificado sin autenticar sirve sólo para ese diagnóstico; no establece confianza. El código exacto del primer fallo no se capturó porque el mensaje era genérico; se corrigió esa limitación.

El instalador incorpora `--repair-default-tls`, exclusivamente junto con `--apply`. Si TLS ya verifica, no renueva. Si falla por IP (OpenSSL código 64), admite renovación sólo en el nodo `proxmox` standalone, sin `corosync.conf`, sin certificado personalizado y con resolución IPv4 local exactamente `172.16.36.100`. Para cualquier otra condición se detiene antes de renovar y muestra un código de diagnóstico cerrado. No modifica `/etc/hosts`, red, CA ni claves SSH.

Antes de renovar guarda certificado, clave del nodo, CA pública y hostkey SSH pública en un directorio nuevo `/root/nap009-tls-respaldo-*` (0700, archivos 0600). Ese respaldo incluye una clave privada y nunca se exporta. Ejecuta `pvecm updatecerts --force` y `systemctl reload pveproxy`, comprueba que CA/hostkey continúan iguales y vuelve a verificar TLS con CA y nombre/IP. La herramienta oficial también actualiza metadatos locales de PVE/SSH; no se invoca la opción de desunir known_hosts ni se cambian las restricciones de naprunner. Si falla, conserva el respaldo y no comienza la creación de la cuenta. No restaura archivos automáticamente sobre una operación incierta. El estado parcial de certificado debe revisarse en root antes de otro intento.

Fuentes primarias revisadas: [implementación de la renovación](https://github.com/proxmox/pve-cluster/blob/master/src/PVE/Cluster/Setup.pm), [comando pvecm](https://github.com/proxmox/pve-cluster/blob/master/src/PVE/CLI/pvecm.pm) y [proxy: reload frente a restart](https://github.com/proxmox/pve-docs/blob/master/pveproxy.adoc). Se eligió recargar el proxy; no se reinicia la VM ni los invitados.

La copia original del lanzador/instalador y el recibo del primer intento se conservan. Se preparó una copia nueva con SHA fijado y se pidió al usuario ejecutar el lanzador actualizado; **renovación y acceso API todavía pendientes de confirmación**. El código informa etapa y código/mensaje TLS sin volcar errores de PVE ni respuestas con secretos. Las pruebas del instalador son ahora **20 aprobadas**; cubren también certificados expirados/no confiables, entorno no admitido, respaldo privado, conservación de identidad, fallo de renovación y diagnóstico anterior a cualquier escritura API. Regresión infra: **103 aprobadas, cuatro opcionales omitidas, 2,77 s** (`/tmp/nap009-infra-api-tls.log`). La renovación real y las ACL siguen sin acreditarse por estos dobles.


### Segundo intento y recuperación del estado parcial

El usuario ejecutó la corrección TLS y llegó a `etapa=preparar_api`, donde se detuvo con `RuntimeError`. La [lectura real posterior](../../docs/evidencia/009/api-ensayo-diagnostico-intento2.json) encontró los cuatro roles, el pool y el token `ensayos` con separación de privilegios/vencimiento correctos; la cuenta está **deshabilitada y sin ACL**. Una lectura adicional de `certificates/info` confirmó que el certificado de nodo ya incluye `172.16.36.100`. No se recibió el valor del token: ambas respuestas locales anteriores están vacías, privadas y conservadas.

Se reprodujo un fallo del instalador al comparar metadatos numéricos de PVE que pueden llegar como strings (`"1"`, timestamp decimal) contra enteros. Se normalizan ahora únicamente enteros o strings decimales canónicos; se rechazan floats, valores ambiguos y booleanos como vencimiento. El primer error remoto no incluyó la operación exacta, por lo que esta reproducción no demuestra por sí sola su causa única. El wrapper informa ahora método/ruta/código de salida de un fallo `pvesh`, sin stdout/stderr ni parámetros con secretos.

El valor que devuelve la creación del token se guarda inmediatamente en el archivo root, **antes de validar sus metadatos**. La versión anterior lo guardaba después; un rechazo de la validación podía perderlo. Un token inválido nunca recibe permisos y la cuenta queda deshabilitada; el valor retenido permanece sólo en el archivo root para diagnóstico/revocación.

Se preparó `--resume-reviewed SHA256` para recuperar exclusivamente este intento conocido. [Snapshot y SHA revisados](../../docs/evidencia/009/api-ensayo-recuperacion-plan.json). El helper abre el archivo root con `O_NOFOLLOW`, comprueba propietario/modo 0600, archivo regular/un solo enlace y toma un lock exclusivo. Contrasta nuevamente usuario, roles, pool, token y ACL con ese SHA; además exige cuenta deshabilitada/sin grupos, roles exactos, pool vacío, ningún ACL del usuario/token y vencimiento todavía vigente. Un SHA no permite saltar esas condiciones. Se requiere el marcador privado exacto del intento anterior o sus credenciales guardadas coherentes, no un objeto existente parecido.

Antes de escribir guarda una copia root privada del estado. Si el valor del token quedó guardado, lo conserva. Si sólo quedó el marcador inicial sin valor, registra la recuperación pendiente antes de revocar/reemitir **únicamente** `nap009lab@pve!ensayos`; conserva su vencimiento y privilegios separados. No recrea cuenta, roles o pool. Después aplica las ocho concesiones ya revisadas y habilita al final. Un fallo conserva el estado y vuelve a intentar deshabilitar la cuenta; una recuperación parcial no se reintenta automáticamente. No toca invitados, red, certificados ni configuración del backend.

El lanzador actual usa esta recuperación con el SHA fijado; **ejecución manual solicitada, resultado pendiente**. Se conservan instaladores y lanzadores de ambos intentos anteriores. Pruebas del instalador: **36 aprobadas**; regresión infra: **119 aprobadas, cuatro opcionales omitidas, 2,65 s** (`/tmp/nap009-infra-api-recuperacion.log`). Incluyen bloqueo por cambios de permisos/usuario/pool, token guardado conservado, sustitución de huérfano, respaldo privado, fallo incierto sin repetición y rechazo de metadatos ambiguos. Son pruebas con dobles; las ACL y el nuevo acceso real se deben verificar después de la ejecución manual. T101/T102 siguen pendientes.


### Acceso API real confirmado y registro Linux

El usuario completó la recuperación. El archivo de respuesta privado se recibió con modo 0600 y su CA pública se guardó bajo el mismo directorio privado. Se usó únicamente el token nuevo, con `verify_ssl=True`, para consultar versión, inventario, nodo, almacenamiento, imágenes y pool. La [verificación real](../../docs/evidencia/009/api-ensayo-verificacion.json) contrastó exactamente los permisos efectivos de once rutas: escritura/configuración sólo en el pool de staging, espacio sólo en `local-lvm`, uso de `vmbr0` y lectura en 101/103/otros pools. No tiene `VM.Console`, `Sys.Modify` ni `Permissions.Modify`. No se intentaron escrituras en invitados ajenos para probar una denegación. No repetir el lanzador API: el secreto ya está guardado y el acceso verificado. La configuración backend anterior sigue intacta.

`registrar_linux_ensayo.py` es un paso aparte de root: admite exclusivamente Linux de staging, en `proxmox`, con red `lab-vmnet8`/subred conocida y rutas constantes. Valida el plan por SHA, los hashes reales de imagen/bundle y el registro anterior vacío por SHA. Rechaza enlaces, archivos ajenos/modificables y cambios del registro. Plan sin efectos por defecto; al aplicar toma lock privado, respalda el registro root, vuelve a compararlo y publica el nuevo JSON por reemplazo atómico/fsync, modo 0600. Si ya coincide exactamente, es idempotente. Una sustitución no confirmada conserva el respaldo para revisión, sin rollback ciego.

El usuario ejecutó el registro y compartió [recibo exitoso](../../docs/evidencia/009/registro-linux-recibo.json). Se registró `linux-lab-009:1.0.0` con hash del manifiesto **borrador**, no un manifiesto final/evidencia/publicación. Ese paso no creó invitados. Sus once pruebas locales y toda infra aprobaron: **130 aprobadas, cuatro opcionales omitidas, 2,78 s**, log `/tmp/nap009-infra-registro-linux.log`.

Después se inició un ensayo real separado con el token limitado: se crearon los LXC 100/102 con UUID/nonce y marcas distintas en `nap009-staging`, 1 CPU/512 MiB/4 GiB cada uno. Antes se comprobaron los márgenes de 1 CPU, 2 GiB RAM y 10 GiB de disco. El 100 arrancó pero no obtuvo IPv4 durante 60 s ni en la consulta posterior; 102 sigue detenido. **El flujo se detuvo antes de enviar credenciales o ejecutar bootstrap**. No se recreó, adoptó ni eliminó un recurso al fallar. Los invitados 101/103 permanecen detenidos e intactos.

Diario privado con secretos en `/home/mauro/.local/share/nap009/ensayos-linux/estado.json` (0600), persistido antes de cada POST; no compartirlo. El [estado público](../../docs/evidencia/009/linux-staging.json) excluye nonce/contraseñas. El script privado de ensayo no debe repetirse: requiere revisar/continuar la identidad ya creada. Se pidieron tres consultas de root mediante `pct exec 100` para conocer el estado real de networkd y su configuración. Resultado pendiente. No inferir que la imagen o VMware son la causa sin esas lecturas; no se modificaron imágenes, red ni servicios para forzar un resultado. Ninguno de los dos ensayos está aceptado y T101/T102 siguen pendientes.
