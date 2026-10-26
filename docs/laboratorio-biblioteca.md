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
5. Preparar Draw.io desde NAP y abrirlo antes de confirmar funcionamiento/publicar. Una ficha incorporada y un build correcto no acreditan que el editor funcione desde el navegador.

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

Estado final: `lista_para_comprobar` (la UI muestra **Ya podés probarla**), preparación
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
