# Factibilidad Community/Core — T006

Laboratorio local, 2026-10-26. **T006 aprobada para los dos pilotos; los perfiles definitivos no están habilitados.**

## Fuentes y dependencias preparadas

- Scripts ProxmoxVE fijados a `5d477b0b6efb4141da0b90cadcec32f8641a815c`; Core a
  `81a2e2ae7d42dea39fd5dd7903b266b5e607c811`.
- [community-sources.lock.json](../../../infra/laboratorio/011/community-sources.lock.json):
  14 archivos locales por hash, incluyendo ambas licencias MIT. No contiene ct wrappers,
  core/build.func ni pve/backend.func. Un helper ausente, modificado, ajeno o enlazado se rechaza.
- [community-dependencies.lock.json](../../../infra/laboratorio/011/community-dependencies.lock.json):
  Debian Snapshot `20261026T000000Z`, suites trixie, trixie-updates y trixie-security, con hashes
  de los tres InRelease. Sus firmas se comprobaron con gpgv y debian-archive-keyring **2025.1**
  dentro de un contenedor sin red/capabilities, con el UID del operador y fuentes de lectura.
- Caddy **2.11.7**, release oficial del 03/10/2026, artefacto amd64 de 18 142 322 bytes;
  SHA-256 verificado contra el digest publicado por GitHub. La instalación usa ese archivo;
  el helper no vuelve a resolver latest. MariaDB usa el snapshot distro, sin PhpMyAdmin.

Las fuentes y el binario públicos se conservan en la caché privada del operador. No se
incorporaron claves, contraseñas, tokens o código upstream completo al repositorio.

## Comprobaciones locales

El Core real fijado cargó sus helpers desde disco en Docker, **sin red**, como UID 1000,
con rootfs de lectura y sin capabilities. No ejecutó instaladores de aplicaciones.
La política bloquea preguntas, descarga de helpers/artefactos no declarados y logging crudo.
Conserva parsers no interactivos y sustituye los hooks comunes de consola/login/updater;
los dos scripts de aplicación permanecen sin modificaciones.

La guarda APT exige el archivo completo de fuentes y los tres hashes de InRelease antes y
después de las operaciones. No admite repositorios mutables, opciones que cambien fuentes,
paquetes locales ajenos ni autenticación omitida. El alias del helper de releases valida
repositorio, versión fijada, arquitectura, patrón de asset y hash antes de instalar.

El adaptador de laboratorio comparte con T005 identidad previa al efecto, CT detenido,
aislamiento externo, AppArmor/seccomp/UID verificados desde el nodo y limpieza sólo de lo propio.
Community usa Debian 13 sin nesting/keyctl. Recibe sólo configuración de red y archivos
públicos: no necesita ni recibe credenciales del registry o de la API de Proxmox.

## Primer intento real y corrección

El [recibo](community-primer-intento.json) de MariaDB confirmó confinamiento y terminó en
`COMMUNITY_APT_SOURCES_CHANGED`, con CT/disco retirados. Caddy no se ejecutó en ese intento.
El helper `cleanup_orphaned_sources` de Core interpretó como una ruta inexistente las tres
líneas Signed-By del archivo nap-snapshot.sources y lo eliminó. Su excepción para el archivo
base del sistema permite conservar el mismo contenido como **debian.sources**.

Se reprodujo la eliminación con el Core real en un contenedor aislado y una configuración
multistanza temporal; la prueba falló antes y pasó tras cambiar el nombre. La guarda mantiene
los mismos hashes/URLs y sigue rechazando archivos extra o cambios de contenido. Se admiten
únicamente las opciones Dpkg force-confdef/force-confold usadas por el instalador fijado.
Los hooks comunes de actualización no prueban espejos alternativos ni borran fuentes para
recuperar un error de red. El paquete anterior está respaldado fuera de Git.

Selección de laboratorio posterior a la corrección: **98 pruebas aprobadas**, incluyendo Core
real aislado y subprocesos de política. No equivale a 98 pruebas en Proxmox ni acredita todavía
MariaDB/Caddy. El nuevo ensayo real se ejecuta secuencialmente con identidades nuevas y el
mismo tamaño Medium; mantiene perfiles pendientes y conserva Draw.io.

## Segundo intento real — aprobado

El [recibo](community-segundo-intento.json) confirmó `community_gate_passed`, ambos invitados
ausentes y ningún perfil habilitado. Se usaron los scripts de aplicación fijados sin modificarlos,
con el mismo harness/política y snapshots. No se ejecutaron wrappers host, no se elevó el token
ni se instaló software de las aplicaciones en Proxmox.

| Piloto | Producto comprobado | Pico cgroup | Disco usado | OOM |
|--------|---------------------|-------------|-------------|-----|
| MariaDB | 11.8.6; SELECT 1 por socket autenticado local | 1017,28 MiB | 0,962 GiB | 0 |
| Caddy | 2.11.7; versión exacta y HTTP 200 local | 832,73 MiB | 0,683 GiB | 0 |

Los picos incluyen instalación y cachés; el margen de MariaDB es estrecho en Medium y no
certifica una carga académica ni permite habilitar Small. Se verificaron root bloqueado,
ausencia de logs crudos de instalación y updater mutable, las tres fuentes por hash,
AppArmor externo en enforce, UID mapeado y seccomp. Las reglas del nodo registraron dos
paquetes bloqueados hacia administración y dos hacia otro invitado en cada ensayo.

Los dos CT, volúmenes y tablas nftables propias se retiraron. El acceso SSH temporal se cerró.
Estos resultados son factibilidad local del prototipo, no habilitación de ofertas ni prueba
del acceso de red/TLS para las cátedras. T061 repite la aceptación con el paquete definitivo.

## Condiciones para el paquete definitivo

Comprobar SELECT 1 local autenticado de MariaDB, versión/HTTP de Caddy, ausencia de preguntas,
telemetría/updater mutable y logs crudos de instalación; root bloqueado, fuentes cerradas,
memoria/disco dentro de Medium sin OOM, bloqueos de red con contadores del nodo y eliminación
de CT/disco/reglas. No cambiar a privilegiado, unconfined o a otro tamaño para pasar el gate.
La comprobación definitiva del paquete y del acceso de las cátedras corresponde a T061.
