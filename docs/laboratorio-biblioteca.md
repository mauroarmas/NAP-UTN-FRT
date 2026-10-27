# Biblioteca de aplicaciones en la VM local

Configuración inicial de laboratorio, 25/10/2026. No corresponde todavía al clúster universitario.
La operación diaria sigue la [guía sencilla](administracion-servicios.md).

## Distribución

- El portal sigue en `http://localhost:5174`.
- Proxmox está en `172.16.36.100`, con 4 CPU y 8 GB de RAM. Se comprobó por API que no quedaron los CT 100–107 ni los seis pools de prueba anteriores.
- Un preparador Docker separado en esta PC construye las imágenes. No se instala el constructor en el sistema de Proxmox. Sus fuentes son un snapshot Git privado; no se hizo un commit en el repositorio de trabajo.
- El nodo recibe imágenes, recetas y registro dinámico por tres carpetas NFS autorizadas únicamente para la dirección de esta PC, `172.16.36.1`. El preparador es un componente de confianza y escribe como root en esas carpetas; no se comparten claves TLS ni archivos generales del nodo. Esta autorización es de laboratorio y debe revisarse para la red institucional.
- El portal recibe una réplica local de sólo lectura de los artefactos. Las claves de conexión están fuera del repositorio y las leen API/worker con su usuario efectivo `nap` (UID 10001).

## Preparación inicial

Los archivos privados de este laboratorio están en `/home/mauro/.local/share/nap010/`.
No copiar sus secretos al repositorio ni reutilizarlos como valores institucionales.

1. `diagnosticar-proxmox.sh`: consulta de sólo lectura de runner, archivos y red. Resultado recibido y revisado.
2. `preparar-nodo-proxmox.sh`: actualiza runner, agrega ocho certificados de aplicaciones y habilita las tres carpetas compartidas, con respaldo en root. Necesita contraseña root sólo en la terminal del operador.
3. `configurar-acceso-local.sh`: agrega ocho nombres a `/etc/hosts` y la CA pública del laboratorio a esta PC, conservando respaldo. Necesita sudo local; no modifica VMware, DHCP ni interfaces.
4. Verificar montajes y SSH del preparador, instalar settings privados para API/worker y habilitar el ejecutor de infraestructura. No habilitar con sólo el diagnóstico inicial.
5. Agregar Draw.io desde NAP. El alta completa sus comprobaciones automáticamente; el navegador se verificó en este laboratorio. No confundir esa prueba con la aceptación de la red universitaria.

El primer intento del paso 2 se detuvo antes de modificar archivos porque el control previo no contemplaba protocolo/wrapper originales. Se corrigió con hashes del paquete anterior y se verificó que acepte esos archivos y rechace cambios desconocidos.

## Red del laboratorio

Se prepararon ocho identidades distintas para `drawio1.nap010.test` a `drawio8.nap010.test`, direcciones `172.16.36.61–68`, certificados y MAC independientes. No se reutilizan UUID históricos. Están fuera del rango dinámico de VMware observado (`172.16.36.128–254`).

El perfil de esta VM usa direcciones estáticas asignadas por Proxmox, con gateway `172.16.36.2`, para no depender del DHCP que falló en los ensayos anteriores. La cátedra y administración no completan direcciones en los formularios. Los perfiles sin `ip_mode` conservan DHCP. La asignación estática queda congelada con su identidad y se valida contra el rango autorizado antes de crear.

Los certificados nuevos de este laboratorio duran como máximo 60 días y nunca más que su CA. Esto no es el vencimiento del servicio ni una prueba de 24 horas; la renovación de certificados corresponde a infraestructura. El acceso está limitado a esta PC; la red universitaria necesitará sus propios destinos, certificados y rangos de clientes.

## Verificaciones técnicas

- Conexión real a PVE 9.2.2 y certificado TLS comprobados.
- Cliente SSH del builder corregido para separar presupuesto de los cinco campos del transporte; conserva validación de clave y hostkey. Suite seleccionada: 20 pruebas aprobadas.
- Archivo Docker de resolución corregido y construido realmente. Paquetes Draw.io fijados: 160, JRE 21.0.12.1.
- Draw.io 32.6.1 y Tomcat 11.0.27 descargados desde sus fuentes oficiales; se verificó el digest publicado por GitHub y el SHA-512 de Apache, respectivamente. [Draw.io](https://github.com/jgraph/drawio/releases/tag/v32.6.1), [Tomcat](https://tomcat.apache.org/download-11.cgi).
- Pruebas seleccionadas de red/orquestación y pipeline: 15 aprobadas; ampliación de red estática/DHCP con fallo y recuperación: 11 aprobadas; infraestructura: 85 aprobadas, 4 omitidas. Estos resultados usan dobles donde corresponde y no acreditan el editor real.

La aceptación institucional y las mediciones humanas siguen siendo independientes de esta comprobación local.

## Confirmaciones del operador

Los pasos del nodo y del acceso local terminaron correctamente. El nodo conserva el registro estático y el respaldo `/root/nap010-runner-mizgm8xi`; no creó contenedores durante esa instalación. La PC conserva respaldo `/root/nap010-acceso-cbegxyi3`. Se verificaron resolución de nombres, NFS accesible y SSH real del builder con receta lista.

API/worker se activaron con settings privados validados y verificación TLS de Proxmox habilitada. Se conservó un dump privado previo (`portal-antes-activar.dump`). Se creó un único pool operativo `nap-preparacion` para los recursos auxiliares de biblioteca. El portal ofrece preparar Draw.io y la preparación real quedó lista para abrir y comprobar. No se publicó la oferta: la decisión final queda en administración.

## Verificación real — 26/10/2026

Estado histórico antes de simplificar el alta: `lista_para_comprobar` (la UI muestra **Ya podés probarla**), preparación
`ce1fc631-8deb-4ca0-9a10-db3b3b555a15`. Las siete operaciones de resolución, construcción,
distribución, creación y bootstrap terminaron confirmadas. CT 100 y 101 están en
`nap-preparacion`; las instancias anteriores de configuración se eliminaron con ausencia
confirmada y liberación de reservas. No se modificaron Usuarios ni Cátedras.

Desde esta PC, en **ambas** instancias:

| Comprobación | Resultado |
|---|---|
| Certificado, nombre y cadena TLS | Verificados, sin omitir validación |
| HTTPS sin credenciales | 401 |
| HTTPS con credenciales propias | 200 |
| Credenciales de la otra instancia | 401 |
| Editor en Chromium | Cargó el lienzo y los menús; sin ignorar errores de certificado |

Los endpoints observados fueron `https://drawio7.nap010.test` y
`https://drawio1.nap010.test`. Las claves no se incluyen en esta documentación. Se obtienen
mediante **Ver acceso** en el asistente administrativo. La comprobación local del editor
con 512 MB también respondió HTTP 200; no sustituye mediciones de uso prolongado ni humanas.

Se corrigieron fallos detectados al conectar el entorno real: campos adicionales en el
cliente SSH, continuación del Dockerfile, referencias resueltas sobrescritas por el perfil,
proc temporal requerido por Java, ubicación de la unidad systemd antes de enmascararla,
carpetas de ejecución borradas por el saneamiento, espera del arranque y tratamiento de
`WARNINGS` de PVE. La construcción tiene un namespace de montajes propio. Las operaciones
largas renuevan su lease y dejan de renovarlo al cancelarse o perder pertenencia.

Validación final: **89 pruebas de infraestructura aprobadas, 4 omitidas**; **21 pruebas**
seleccionadas de pipeline/red/transporte aprobadas y **13 pruebas** seleccionadas de worker,
pipeline, alta y transporte aprobadas. Son selecciones parcialmente superpuestas, no se suman.
Los ensayos reales pendientes de la institución y las mediciones de T052/T067/T072/T073
no se cierran por estos resultados. No se simuló una publicación ni una aprobación humana.

## Arranque y acceso desde esta PC

`.env` conserva `COMPOSE_FILE` con los archivos normales y el complemento privado
`/home/mauro/.local/share/nap010/compose-portal.yml`. `docker compose up -d` mantiene API,
worker y preparador conectados a la configuración local. El constructor espera sus montajes
si Proxmox todavía no está disponible.

VMware tenía permitido el modo promiscuo en la VM, pero su dispositivo `/dev/vmnet8` no
permitía activarlo al usuario Mauro. Se verificó el rechazo en el log de VMware y se concedió
ACL de lectura/escritura **sólo a Mauro**, conservando a los demás usuarios sin acceso. Se
reconectó Ethernet0 de esa VM sin reiniciarla. La persistencia está en
`/etc/systemd/system/vmware.service.d/90-nap010-permisos.conf`; no modifica otras redes.
La justificación técnica está en la [documentación de Broadcom](https://knowledge.broadcom.com/external/article/315331).

La CA pública del laboratorio se instaló en el sistema y en el almacén NSS del usuario para
que el navegador valide el acceso. Se respaldó el almacén de certificados antes del cambio;
no se importaron claves privadas. Los respaldos y resultados están en el directorio privado.
Los contenedores e imagen de diagnóstico adicionales se retiraron tras comprobar el editor.

Para revertir el ajuste específico de permisos, el operador puede retirar el drop-in indicado,
recargar systemd y eliminar la ACL de Mauro de `/dev/vmnet8`. No hacerlo mientras se necesite
acceder a los LXC anidados. Los archivos privados describen este laboratorio, no son los
valores que debe adoptar el clúster universitario.

## Alcance de la biblioteca y de IaaS

La preparación automática actual admite **Draw.io**. Buscar e incorporar una ficha de
Community Scripts no incorpora su instalador al ejecutor: otra aplicación necesita una
receta compatible de construcción, configuración, acceso y comprobación. Una vez preparada
y publicada, esa aplicación puede reutilizarse en pedidos independientes de varias cátedras.

El catálogo usa las categorías **IaaS, PaaS y SaaS** en administración y en la vista docente.
El administrador también puede consultar las bases Linux descargadas en Proxmox. El 26/10/2026
se comprobaron por API `ubuntu-24.04-standard_24.04-2_amd64.tar.zst` y
`debian-13-standard_13.6-1_amd64.tar.zst`. Ahora se incorporan automáticamente como IaaS,
sin construir una aplicación ni registrar una validación ficticia. Las imágenes de aplicaciones
y de ensayos no se muestran como bases Linux.


## Alta directa y recuperación (26/10/2026)

- Flujo habitual: **elegir → agregar → disponible**. NAP continúa en el worker y la pestaña no necesita quedar abierta.
- Draw.io quedó **ofrecido en el catálogo**. Se conservó el artefacto ya probado y se retiraron sus dos LXC auxiliares.
  La consulta de `stage` rechazaba `validated_manifest` al cambiar a `status`; se corrigió el contrato de consulta.
- IaaS usa las plantillas estándar del nodo directamente. La red privada `lab-linux-010` asigna ocho IP/MAC
  autorizadas (.71–.78); PVE configura la red y una contraseña root aleatoria, persistida cifrada antes del POST.
  El alta IaaS acredita el contenedor propio arrancado y el acceso inicial recuperable, sin inventar pruebas de una aplicación.
- Se aplicó `010_05_alta_materializada` con respaldo previo privado. La base local conservaba la condición antigua
  que obligaba a las altas a mantener `servicio_id` vacío, aunque 009_14 ya figuraba aplicada. La migración permite
  vincular el servicio creado y sigue exigiendo un servicio a las renovaciones. No modifica usuarios ni cátedras.
- Pruebas reales: pedidos técnicos 31 (Ubuntu) y 32 (Debian), servicios 16 y 17, llegaron a **Activo** y permitieron
  recuperar sus credenciales. Se detuvieron/eliminaron sus contenedores por el flujo normal, se confirmó la ausencia
  y se archivaron los pedidos. No se comprobó manualmente el login dentro del guest ni se acreditó acceso de la universidad.
- El acceso administrativo a consola abre Proxmox con la cuenta propia del operador, tras comprobar pertenencia;
  no emite tickets ni comparte credenciales. La consola docente conserva la autorización individual institucional.
- La verificación automática de aplicaciones tiene su propia marca (`automatic_verification`): no afirma que se
  haya probado desde la red estudiantil. Se conservan los controles de integridad, propiedad y secretos distintos.

## Acceso Draw.io con la sesión de NAP (26/10/2026)

- Se conservó el servicio 18 del pedido 33, sin detenerlo, eliminarlo ni reconstruir el contenedor.
- El arranque habitual de Compose incluye `nap010-app-gateway` (HTTPS, puerto local 8443).
  Usa `app-<id>.nap-apps.test`, separado de localhost y de la API. Se agregaron los nombres 1–256
  a `/etc/hosts` con respaldo privado `nap010/hosts.antes-acceso-nap`; no se cambió VMware ni Proxmox.
- Certificado firmado con la CA local ya instalada; configuración y clave privada fuera del repositorio.
  La migración `010_06_acceso_aplicacion` se aplicó tras `nap010/antes-acceso-nap.dump`.
- Chromium abrió el editor real en español por **Ver acceso → Abrir aplicación**, sin Basic Auth,
  con certificados verificados y sin fallos de recursos. Se comprobaron la separación de cookies/orígenes,
  ausencia de opener y rechazo de consultas después de logout (HTTP 401).
- Para esta verificación se creó una sesión de dominio temporal del titular operativo sin 2FA, auditada
  y revocada al cerrar NAP. No se modificaron contraseñas, usuarios ni cátedras; esta prueba no acredita
  ingreso mediante contraseña ni MFA. La apertura confirmó la entrega real y el pedido pasó a Activo.
- Las capturas de comprobación quedan en el directorio privado `nap010/qa-acceso-modal.png` y
  `nap010/qa-drawio-nap.png`. Las pruebas sintéticas de concurrencia se ejecutan en PostgreSQL aislado.
- No se usan service workers ni instalación PWA: el editor debe consultar NAP al recargar después
  del cierre de sesión. No se borra almacenamiento del navegador ni archivos del usuario.

Guía de uso e instalación institucional: [acceso a aplicaciones con NAP](acceso-aplicaciones-nap.md).

## Búsqueda y categorías (26/10/2026)

Se eliminó la lista «Guardadas». Las incorporaciones se conservan internamente para retomar la
misma alta, sin confundir una ficha con una instalación disponible. Las aplicaciones compatibles
continúan directamente al formulario; las demás muestran el motivo y no ofrecen un botón bloqueado.

La búsqueda conserva las rutas LXC fijadas a una revisión de GitHub y enriquece nombres,
descripciones y categorías con las colecciones públicas `script_categories` y `script_scripts`
de `https://db.community-scripts.org/api/collections/`. La consulta es de sólo lectura, con límite
de tiempo, bytes, páginas y caché. El token de GitHub no se envía a ese proveedor de metadatos.
Si esa consulta falla, permanece la búsqueda por nombre y se informa que faltan categorías.
La metadata externa nunca habilita por sí misma la instalación de una aplicación.

Comprobación real: se consultaron 28 categorías y las fichas públicas; MariaDB se encontró dentro
de Databases. Las pruebas visuales de la nueva interfaz usan backend simulado, sin instalar servicios
ni modificar Proxmox. El despliegue genérico de aplicaciones propias sigue pendiente, descrito en
[rumbo del producto](rumbo-mini-cloud.md).
