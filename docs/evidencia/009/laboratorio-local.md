# Preparación guiada de la VM local

20 de octubre de 2026, America/Argentina/Tucuman. El usuario encendió la VM y pidió ayuda para preparar la infraestructura. Confirmó que Proxmox corre en esta PC y que las primeras pruebas se harán desde ella. La aceptación desde otra computadora continúa pendiente de T102.

## Observado por lecturas reales

| Dato | Resultado |
|---|---|
| API | `172.16.36.100:8006`, Proxmox VE 9.2.2, nodo `proxmox` online |
| Recursos | 4 CPU, 8.275.742.720 bytes de RAM, aprox. 1,6 GB usados en esa lectura |
| Almacén de imágenes | `local`, contenido `vztmpl`, aprox. 68 GB disponibles |
| Disco de invitados | `local-lvm`, `rootdir,images`, aprox. 164 GB disponibles |
| Red PVE | `vmbr0`, bridge sobre `nic0`, `172.16.36.100/24`, gateway `172.16.36.2` |
| Ruta desde esta PC | Interfaz `vmnet8`, origen `172.16.36.1` |
| DHCP VMware existente | `172.16.36.128`–`172.16.36.254`, DNS/gateway `172.16.36.2` |
| Invitados existentes | LXC 101 y 103 detenidos; no se iniciaron, modificaron ni eliminaron |
| SSH | Puerto 22 responde; banner OpenSSH 10.0p2 Debian |

La API actual usa el token ya configurado y verificación TLS desactivada. Esa lectura no acredita el perfil mínimo de permisos ni la confianza TLS institucional. No se cambiaron la configuración VMware, la red PVE ni el archivo `.env`.

El usuario mostró desde la consola root de la VM la huella pública Ed25519:

```text
SHA256:GpEk3MdcApRUkRs36MejD/v1wzeQ+ZsGUQ4/EjQzrQk
```

Se comparó exactamente con la clave obtenida del servidor y se fijó en `/home/mauro/.local/share/nap009/ssh/known_hosts`. No se aceptó una clave desconocida automáticamente. Antes no había archivo known_hosts ni claves SSH en el home de desarrollo.

## Preparado fuera del repositorio

Actualización 2026-10-21: se volvió a observar PVE online y los invitados 101/103 detenidos, sin cambios. `local` sigue siendo un almacenamiento `dir` bajo `/var/lib/vz`, con contenido `iso,import,backup,vztmpl`. Está preparado un [paso acotado de carga](../../../infra/laboratorio/README.md) de las tres imágenes terminadas y sus bundles, sin publicar ni habilitar recetas. Paquete de 379.566.080 bytes, SHA `fbd5f4ca56ee3de729f17b93cff6c4977d77cb80cc34d6a31d124cd794c92db4`; [recibo](carga-artefactos-preparada.json). El usuario ejecutó el lanzador y compartió **Carga terminada**. El [recibo root](carga-artefactos-recibo.json) confirma los seis archivos nuevos y sus SHA; la [API](carga-artefactos-pve.json) confirma las tres imágenes con tamaño exacto. Los LXC 101/103 siguen detenidos. Registro, perfiles, permisos y red/TLS de instancias continúan pendientes. No volver a ejecutar el instalador inicial de acceso SSH de abajo.

- `/home/mauro/.local/share/nap009/ssh/runner_ed25519`: clave privada nueva del worker, modo 0600; nunca impresa ni incluida en el paquete.
- `runner_ed25519.pub`: clave pública; huella `SHA256:AkTsobmZMhFxoKApzruw/gBLO99QTdN1V7tCNUUCNNk`.
- `/home/mauro/.local/share/nap009/configuracion-laboratorio.borrador.json`: propuesta de namespace UUID estable, margen de 1 CPU/2048 MiB y 10 GiB de disco, destino `local-lvm`, bridge `vmbr0`, red `lab-vmnet8` y cliente permitido `172.16.36.1/32`. Instancias y artefactos vacíos. **No aplicada al backend**; los márgenes son una propuesta, no medidas de aceptación.
- `/home/mauro/.local/share/nap009/nap009-runner-setup.tar.gz`: cinco archivos de código, clave pública y recibo de hashes. No contiene `.env`, token API, clave privada ni datos de la aplicación.
- `/home/mauro/.local/share/nap009/instalar-en-proxmox.sh`: paso preparado para ejecutar como mauro en una terminal interactiva de esta PC.

SHA-256 del paquete preparado:

```text
20d97a9e466cf55903337b7f445f980f452d1c1aa5e1042da5957df2c0bbb767
```

El código del paquete corresponde al árbol de trabajo sin commit; no se presenta como receta/versionado de imagen publicado.

## Paso inicial ejecutado por el usuario (no repetir)

```bash
bash /home/mauro/.local/share/nap009/instalar-en-proxmox.sh
```

La contraseña root se escribió únicamente en el prompt SSH de esa terminal. El script usó la hostkey verificada, transfirió el paquete por stdin y comprobó el SHA antes de extraerlo en un directorio nuevo bajo `/root`. Instaló sudo y aplicó [configure_access.py](../../../infra/runner/configure_access.py), validando antes de recargar SSH. El método de acceso root existente se conservó. La clave dedicada ya autentica después de la corrección descrita abajo.

Si falta un prerrequisito, existe una cuenta/configuración previa o falla la validación, conservar la consola root y comunicar el error. No repetir con opciones que desactiven la comprobación de identidad, ni borrar directorios con estado sin investigarlos.

**Instalación confirmada por el resultado compartido por el usuario**: el paquete con SHA `20d97a9e466cf55903337b7f445f980f452d1c1aa5e1042da5957df2c0bbb767` se verificó en `/root/nap009-runner-20d97a9e466c.tar.gz`, se instaló únicamente sudo (sin actualizaciones), el asistente de configuración terminó con `acceso_instalado` y ocho hashes. La primera conexión SSH dedicada fue rechazada; ver la corrección de permisos siguiente. El asistente todavía no ejecutó un comando root remoto ni habilitó recetas.

### Corrección del primer acceso

El helper establece `umask 077`, mientras que `configure_access.py` inicialmente solicitaba modos a `mkdir` sin restaurarlos después de aplicar esa umask. Los directorios nuevos de claves públicas/home podían quedar 0700; sshd, al leer authorized_keys como naprunner, no podía recorrerlos. El ensayo previo había utilizado la umask habitual del contenedor y no cubría esa combinación.

Se reprodujo el rechazo `Permission denied (publickey)` en el contenedor con **la misma umask 077**. Se corrigió el código para fijar explícitamente el modo de los directorios nuevos y se agregó esa condición al ensayo. La instalación, el SSH real por loopback, el rechazo de origen y de forwarding volvieron a aprobar. Las 16 pruebas unitarias aprobaron en 0,06 s.

Se pidió al usuario ejecutar una corrección acotada desde su consola root existente:

```bash
chmod 0755 /etc/nap /etc/nap/runner /var/lib/nap-runner-login
```

Solo cambia el recorrido de esos directorios root; los archivos privados, el estado 0700 y las claves 0600 conservan sus permisos. No requiere recargar sshd. El primer intento del usuario unió dos rutas y corrigió únicamente `/etc/nap`; se dieron dos líneas separadas, que ejecutó sin errores. **Autenticación dedicada confirmada después de la corrección.** El paquete inicial se conserva como evidencia de lo instalado; su instalador histórico contiene el fallo ya corregido en las fuentes. No volver a ejecutar el bootstrap inicial sobre la cuenta existente.

### Comprobaciones reales de SSH

Resultado medido guardado en [runner-ssh-laboratorio.json](runner-ssh-laboratorio.json): cliente Python/OpenSSH con hostkey fijada, protocolo cerrado válido y rechazo de una receta no registrada; orden de shell sustituida por el wrapper; PTY y forwarding remoto denegados; archivo temporal con hostkey diferente rechazado antes de autenticar. No se ejecutaron comandos dentro de invitados. El origen distinto del permitido no se ensayó en la VM y continúa pendiente de otra fuente real. Esto tampoco acredita ACL/revocación de consolas docentes ni productos instalados. El backend conserva su configuración anterior y no publica ofertas.

## Verificación local del instalador

- Las 16 pruebas nuevas fallaron inicialmente por módulo todavía inexistente; aprobaron tras implementarlo. Cubren origen concreto, rechazo de material privado/opciones/claves múltiples, destinos/enlaces existentes, configuración efectiva incompleta y retirada de archivos/recarga anterior ante fallos.
- Suite infra: **69 aprobadas, 4 opt-in omitidas**, 2,97 s. No se debilitaron los bloqueos de red/procesos de la suite predeterminada.
- Ensayo explícito en contenedor Debian 13 descartable: sshd/visudo/sudo reales, cuenta y wrapper instalados, root conserva configuración, JSON inválido rechazado sin tocar invitados, sudo shell/pct/argumentos denegados y segunda instalación rechazada. `pct`, `pvesh` y systemctl son dobles; no hubo red/PVE en su ejecución. El primer intento tenía incompleto el doble de `/etc/pve/local`; se corrigió ese fixture y se repitió satisfactoriamente.
- En ese mismo contenedor se comprobó SSH real por loopback con claves efímeras: origen distinto del permitido denegado, contraseña bloqueada compatible con autenticación pública mediante PAM, orden de shell sustituida por el wrapper y forwarding remoto denegado. Solo en el fixture se adapta el origen permitido a loopback para el caso positivo. `--network none` evita rutas externas; no se contacta la VM. Se corrigió además el prerrequisito a `/usr/sbin/pct`, la misma ruta fija del ejecutor, y se regeneraron paquete/helper antes de la entrega final.
- Base del ensayo: `debian:13-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad`. La construcción descargó herramientas del sistema; no equivale a instalar productos en la VM.

## Base independiente y pausa

Se creó exclusivamente para el laboratorio el contenedor `nap009-laboratorio-db`, PostgreSQL16, puerto `127.0.0.1:55433`, base `nap_lab_009`, volumen persistente `nap009_laboratorio_pgdata`. Las credenciales aleatorias están fuera del repositorio, bajo `/home/mauro/.local/share/nap009/laboratorio/` con directorio privado. No imprimir la configuración ni usar su URL para pruebas de la base operativa. Alembic terminó correctamente y se verificó la revisión `009_10_identidad_preparacion`. No se crearon usuarios/borradores ni se arrancaron API/worker del laboratorio.

Durante la preparación se corrigió el CLI de administrador inicial, que enviaba password al esquema de alta ordinaria que exige None. El bootstrap conserva la validación y hash de su contraseña explícita. Las cuatro pruebas de `test_cli_identidad.py` aprobaron en 2,20 s.

Al pausar por pedido del usuario se detuvo ordenadamente `nap009-laboratorio-db`; el volumen conserva la base. Reanudar con `docker start nap009-laboratorio-db` cuando se retome. No quedaron builds, migraciones, pytest ni operaciones propias en PVE pendientes. La VM puede apagarse durante la pausa. Los contenedores operativos preexistentes no se modificaron.

## Después de la pausa

El SSH dedicado ya está comprobado; no repetir la instalación inicial. Preparar el host de build y registrar definiciones borrador mediante el flujo autenticado del laboratorio. Los tres inventarios exactos ya están resueltos, según [build-preparacion.md](build-preparacion.md). Después faltan imágenes saneadas/versionadas, reserva DHCP por instancia, nombres locales/certificados individuales y registro del runner. El perfil aún no asigna IPs ni emite certificados. No activar ofertas ni declarar T101/T102 aprobadas antes de las pruebas correspondientes. La consola Linux conserva su gate de ACL y revocación nativa pendiente.

## Paso de acceso de ensayo preparado el 21 de octubre

Después de confirmar la carga se preparó un [acceso API temporal de staging](../../../infra/laboratorio/README.md#Acceso-API-temporal-para-staging). El plan real sólo de lectura no encontró colisiones. Se pidió al usuario ejecutar `bash /home/mauro/.local/share/nap009/preparar-api-ensayos-en-proxmox.sh`; resultado pendiente. La cuenta, roles, pool y exportación de CA **todavía no están confirmados en la VM**. Las nueve pruebas nuevas y la regresión infra de 92 aprobadas/4 omitidas usan dobles y no sustituyen la verificación posterior con token real. No se modificó la configuración del backend ni se crearon invitados.


El primer intento del paso API falló. No aparecieron cuenta/roles/pool en la consulta posterior. Se detectó un certificado con la IP anterior, se conservó el recibo inicial y se preparó una [corrección condicionada de TLS](../../../infra/laboratorio/README.md#primer-intento-y-corrección-tls), con respaldo root y recarga del proxy. Nueva ejecución manual solicitada; resultado pendiente. La configuración backend permanece intacta y no se crearon contenedores. No confundir esta solicitud corregida con un segundo éxito observado.


El segundo intento llegó a preparación API y se detuvo. La consulta real encuentra cuenta deshabilitada, cuatro roles, pool vacío y token separado, **sin ACL**. El certificado actual sí contiene `172.16.36.100`. Se preparó una recuperación con SHA del estado revisado y comprobación del archivo privado root; preserva credenciales guardadas o sustituye sólo el token huérfano, sin recrear los objetos. Se pidió ejecutar el lanzador actualizado. Estado todavía pendiente de resultado y de verificación HTTPS/permisos efectivos. Ver [procedimiento y límites](../../../infra/laboratorio/README.md#segundo-intento-y-recuperación-del-estado-parcial).


## Acceso confirmado y primer ensayo Linux

La recuperación API terminó correctamente: [recibo](api-ensayo-recuperacion-recibo.json) y [lecturas HTTPS/permisos efectivos con el token nuevo](api-ensayo-verificacion.json). El usuario también confirmó [registro Linux](registro-linux-recibo.json); no repetir esos pasos. El registro habilita únicamente la receta de staging, sin publicar el catálogo.

Se crearon dos LXC de ensayo propios (100/102) y se arrancó sólo 100. No obtuvo dirección IPv4; el flujo se detuvo antes de transmitir credenciales/bootstrap. Se conservan 100 arrancado para diagnóstico y 102 detenido. Los anteriores 101/103 siguen detenidos y no se modificaron. Se solicitaron al usuario consultas de root `systemctl status systemd-networkd`, `networkctl status eth0` y lectura de `eth0.network` dentro del 100. Resultado pendiente; no reconstruir imágenes ni cambiar DHCP por una hipótesis. [Estado público](linux-staging.json). No se ejecuta ningún script propio en segundo plano después del fallo.


Pausa solicitada por el usuario el 21 de octubre: los cuatro LXC 100/101/102/103 quedaron detenidos, con datos conservados; sólo se detuvo el 100 propio. VMware registra un bloqueo explícito de promiscuo y el dispositivo vmnet8 no da acceso a mauro. No se cambiaron esos permisos ni opciones de VMware. La captura individual confirma networkd activo y eth0 sin IPv4. [Diagnóstico](linux-red-diagnostico.json), [pausa verificada](pausa-laboratorio.json). Al retomar se preparará la corrección mínima del permiso y se revalidará DHCP antes de bootstrap. La VM puede apagarse.
