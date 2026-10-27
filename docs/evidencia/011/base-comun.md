# Base común 011 — avance del 26/10/2026

Implementación parcial de Phase 2. No habilita perfiles ni ofertas y no acredita
el despliegue definitivo de aplicaciones. Draw.io conserva su camino existente.

## Contratos y perfiles

- `nap-deployment/1`: dos orígenes discriminados, datos estrictos, límites de
  recursos/variables/persistencia, probes tipados y errores sin entradas privadas.
  Hash canónico y pruebas de equivalencia entre validación de portal y nodo.
- `nap-application-job/1`: requests por acción; respuestas cerradas y correlacionadas
  con la identidad completa. Rechaza comandos, rutas, unidades y cursores inválidos.
  La huella liga configuración y referencias/versiones; excluye valores privados
  y generación del controlador. El nonce privado viaja sólo en la petición;
  manifiesto y respuesta conservan su SHA-256, nunca el valor original.
- Registro institucional compartido: hash de definición, plataforma/base/runtime
  exactos, estados explícitos, evidencia referida al hash final, 2700 s y dos trabajos
  por nodo. Registro vacío por defecto; no activa capacidades por ejecutar pruebas.
  El paquete copia el contrato común y exige `jsonschema` explícitamente.

## Persistencia y secretos

Migración aditiva `011_01_despliegue_aplicaciones` desde `010_06_acceso_aplicacion`:
seis tablas nuevas, vínculos nullable, agenda sin backfill y exclusión de origen.
Las revisiones validadas son inmutables por ORM y trigger PostgreSQL, con retirada
lógica definitiva. Se conserva el contador de reclamaciones histórico separado
del número de intento efectivo. La consola liga raíz/intento/ejecución y diferencia
eventos portal/runner; cuota y secuencia quedan restringidas en el esquema.

La prueba PostgreSQL compara todos los valores anteriores de usuarios, cátedras,
templates, pedidos, servicios, identidades y operaciones terminales antes/después.
Comprueba FK, índices parciales, exclusión, trigger y downgrade sin pérdida silenciosa.
También se ejecutó el upgrade en el portal local, con respaldo privado `pg_dump`
verificado previamente. `/api/v1/health` respondió 200 después de la migración.
No se crearon invitados ni reservas como efecto de migrar.

`SecretoDespliegue` usa el keyring existente con contexto pedido/nombre/revisión.
Creación serializada por pedido; otro alta recibe otros valores. Un reintento conserva
referencias/valores aunque cambie VMID; una renovación reutiliza los del alta original.
Entrada aportada write-only, replay que no reemplaza secretos y HMAC contextual con
soporte de clave anterior tras rotación. Descifrado sólo tras autorización vigente
de acceso, o lease actual y referencias/snapshot coincidentes para dispatch privado.
No se copian valores a snapshots, contexto, oferta o campos legacy de Servicio.

## Depuración previa a consola

`redaction.py` está integrado al worker y al colector del paquete común.
Procesa UTF-8 incremental y controles ANSI/OSC/bidi; cubre representaciones declaradas,
fronteras entre chunks y prefijos truncados. El texto desconocido se descarta incluso
si no contiene un secreto registrado. Sólo eventos cerrados y paquetes admitidos por
el perfil producen mensajes; entradas/colas de memoria tienen límites explícitos.
El spool guarda sólo texto admitido, con secuencia/cursor transaccionales, límite de
bytes/filas/páginas, recorte explícito, replay y eliminación segura por ACK. Una
escritura fallida no publica secuencias; al recuperarse comunica los mensajes que
no pudo confirmar, sin inventar contadores durables tras una caída de disco/proceso.
La ingesta en PostgreSQL y su tick independiente están implementados; faltan la UI
y las comprobaciones durante despliegues completos.

## Supervisor y distribución — T009/T024/T025/T027/T028/T029

El dispatcher nuevo conserva el recorrido histórico separado. El supervisor escribe
manifiesto e índice antes de solicitar una unidad de nombre fijo `Type=exec`, sin
PTY, pipe/wait ni salida cruda en journal. Los archivos se anclan a directorios
privados, sin enlaces; los locks de admisión/recurso son breves. La generación
obsoleta se rechaza, el replay no inicia otra unidad y un cambio de boot/unidad o
una salida sin resultado probado queda incierto. Cuenta también trabajos inciertos
para el máximo de dos activos. La reclamación del worker es de un solo uso y liga
fingerprint, boot e InvocationID. Una respuesta perdida no reinstala ni libera capacidad.

`install.py` construye sólo archivos de código revisados y una regla tmpfiles para
`/run`; valida versiones previas o el recibo anterior, rechaza cambios desconocidos
y trabajos activos/desconocidos, comparte el lock de admisión y conserva respaldo
con reversión ante fallo. Se instala explícitamente por `preparar_entorno.py
--install-package`; no modifica SSH, cuentas, puentes, pools ni invitados. Conserva
la configuración existente y no habilita perfiles.

En la VM real se instaló `python3-jsonschema` y el paquete común (recibo de código
`28dffb74042e9f5f84d44f3fe826131ab1653f7698a295fb2f08519f75776617`). La comprobación
root `selfcheck.run()` usó una unidad systemd temporal y un canario aleatorio:
entrega por LoadCredential, registro durable de carga antes de retirar el origen,
retiro de la copia al finalizar, depuración byte a byte, replay/ACK y ausencia del
canario en spool/metadata/journal. También comprobó una unidad inexistente mediante
el adaptador real: systemctl devuelve 1 en ese caso, que se admite sólo para esta
consulta cerrada. Se retiraron unidad y directorio de comprobación. Un primer control
agotó 5 s consultando el journal; el diagnóstico ahora tiene 15 s y límite de salida.

Esta comprobación acredita **mecanismos comunes del nodo**, sin certificar perfiles,
Docker/Core definitivos, red de invitados ni entrega de una aplicación. El inventario
posterior conserva sólo CT 100 Draw.io, corriendo. No se habilitó ningún perfil nuevo.

El cliente del portal usa OpenSSH con destino institucional y hostkey fijada,
stdin privado y respuesta acotada/correlacionada. Las llamadas duran hasta 30 s;
sólo las consultas pueden repetirse. Start y ACK se envían una vez; cortar o cancelar
el transporte local no cancela ni reinicia el trabajo remoto. La imagen de API incluye
únicamente el contrato del nodo, sin su ejecutor root. Construcción comprobada y
consulta real `profiles` desde la cuenta limitada: respuesta válida con lista vacía.

## Validación

- Suite completa de backend ordinaria: **860 aprobadas**, antes de añadir la prueba
  adicional de rotación HMAC. Ninguna prueba conecta al Proxmox real.
- Selección 011 posterior: **55 aprobadas**. Aplicaciones/runner histórico: **79
  aprobadas y 5 integraciones omitidas explícitamente**.
- Migraciones 009/010/011: se corrigió el backfill previo a 010 para diferir columnas
  011; las fixtures de un esquema congelado 009 usan SQL de esa versión.
- PostgreSQL 16 temporal, puerto 55432/esquemas aleatorios: carreras de secretos,
  unicidad de intento/dirección activa y takeover sin renumeración. Las restricciones
  no sustituyen las pruebas pendientes del asignador/admisión de T012/T023/T030.
- Suite PostgreSQL completa: 119 aprobadas y una expectativa de revisión antigua
  detectada en restauración; corregida y verificada mediante la selección afectada:
  **10 aprobadas**, incluyendo la nueva carrera del asignador. No es una segunda
  ejecución completa ni acredita instalaciones PVE.
- Laboratorio 011: **98 aprobadas**, incluye Core real en Docker sin red; sigue
  siendo distinto de los ensayos físicos documentados en `compuertas.md`.

No se certificó la red o el clúster universitario. El uso productivo de perfiles
continúa condicionado a T050 y T061 y a las aceptaciones de cada historia.

Validación adicional de este incremento: **158 aprobadas y 6 integraciones omitidas**
en aplicaciones/runner/builder; **3 aprobadas** con procesos locales reales para
stdin, códigos de salida, cuota y deadline; **70 aprobadas** para cliente nuevo,
cliente histórico y contrato del backend. Laboratorio + infra en contenedor aislado:
**248 aprobadas y 13 omitidas**, antes de los últimos ajustes de observación de unidad
y lock de actualización; selección posterior de instalador/autocomprobación/bootstrap:
**17 aprobadas**, más una nueva prueba de manifiesto corrupto (instalador: **7 aprobadas**).
Estos conteos son ejecuciones distintas y no se suman como pruebas únicas.

## Ingesta y retención — T010/T031

`consola_operacion_service.py` conserva una cabecera por raíz y serializa productores
con locks de operación/intento/cabecera. El runner usa source_seq como clave; los
hitos del portal derivan su clave del intento/fase/evento y sólo admiten textos
cerrados. El evento del portal y su cambio de fase se guardan en la misma transacción.
Se retienen tombstones de hitos en el contexto seguro y el cursor del runner en el
intento: purgar texto no permite volver a insertarlo al repetir una consulta.

El helper de ingesta verifica identidad, lease/generación, fingerprint, boot, cursores
y contrato del lote; rechaza huecos sin declaración de pérdida. Un descarte del nodo
agrega aviso y contador probado. No inventa bytes para una parte de un rango original
que también contiene mensajes ya ingeridos. Un resultado final del portal espera
haber ingerido el cursor final anunciado por el nodo; sin job se admite el resultado
de un fallo de creación, pero nunca anunciar una aplicación disponible.

La cuota de 10 000 000 bytes UTF-8 y los 30 días se aplican a la raíz compartida por
todos los intentos/productores. La purga usa lotes acotados y conserva cabecera,
cursor, resultado y filas de historia. `ingerir_y_confirmar` cierra la transacción
antes de usar SSH para ACK. Un commit fallido no envía ACK; un ACK perdido se puede
repetir después de ingerir idempotentemente el mismo lote. No hay SSH bajo locks SQL.

Verificación: **17 pruebas ordinarias** de ingesta; **3 pruebas PostgreSQL** con
sesiones concurrentes, cuota compartida entre intentos y claves locales iguales de
productores diferentes. Depuración/colector/spool: **20 aprobadas**, incluida falta
de memoria del consumidor sin bloquear el drenaje. La prueba PostgreSQL de exportación
y la integración a la UI siguen pendientes en T078/T081; no se atribuye a
estas pruebas la aceptación completa de la consola visible.

Regresión ordinaria completa posterior: **903 aprobadas, 124 PostgreSQL excluidas**
en 8 min 49 s. Las tres pruebas PostgreSQL nuevas se ejecutaron por separado en
el servicio aislado (puerto 55432); no representan una nueva ejecución completa
de aquella suite. API local: health 200 tras las verificaciones.

## Admisión declarativa — T030

La selección administrativa admite una configuración inmutable nueva o una definición
histórica, sin mezclar orígenes. Evaluación/aprobación revalidan oferta, modelo, base,
perfil habilitado, tamaños Small/Medium, destino e imagen disponible. La firma vincula
también configuración/perfil y snapshot/hash de red institucional. El pedido de la
cátedra sigue usando aplicación, propósito y fechas; no incorpora hardware ni campos
internos al formulario.

La aprobación conserva documento/digests, perfil, red y referencias privadas en el
snapshot y crea un solo compromiso de capacidad. Los datos privados administrativos
son write-only: se cifran antes de persistir y la idempotencia guarda únicamente un
HMAC contextual. El replay no genera otra reserva ni otro secreto. Las renovaciones
conservan la configuración de su instancia original.

Se puede encolar inmediatamente o más adelante sin crear un CT dentro del HTTP.
Al encolar se valida la revisión **aprobada**, aunque la oferta se haya retirado o
actualizado. El bloqueo técnico del perfil o una modificación de la red aprobada
impide continuar. Los caminos históricos e IaaS permanecen separados.

Validación proporcional acordada con Mauro: **13 pruebas específicas aprobadas en
10,67 s**, incluyendo flujo IaaS anterior, aprobación histórica, autorización de
secretos, pedido declarativo, snapshots, retiro/bloqueo y errores de infraestructura.
**Una carrera PostgreSQL aprobada en 2,23 s**: dos aprobaciones para la capacidad de
un solo Medium dejan una reserva y un rechazo. No se repitió la regresión general
de 903 pruebas ni se ejecutaron ensayos nuevos en Proxmox, porque este bloque cambia
admisión local. T032 y las estrategias definitivas siguen pendientes: no acredita
instalación completa ni habilita ofertas o perfiles en el laboratorio.

## Creación declarativa y worker — T012/T032 parcial/T033

La rama nueva evita el bootstrap histórico. Consulta capacidades del nodo y comprueba
la decisión vigente; reserva identidad/VMID/red, crea intento/execution_id y cabecera
de consola, y registra el hito antes del POST a PVE. UUID y nonce hexadecimal son
nuevos por identidad; la marca del LXC contiene sólo su hash y los hashes aprobados.
La creación usa `unprivileged=1`, `start=0`, `onboot=0`, red estática reservada y
`firewall=1`. No se entregan contraseñas NAP ni flags de ejecución del usuario.

El recurso materializado conserva la configuración aprobada y queda sin acceso
entregado. La intención de instalar se confirma en DB antes de enviar `start` al
runner. Ante pérdida de respuesta se consultan tarea/trabajo existentes: takeover
incrementa la reclamación histórica, sin cambiar intento efectivo/execution_id ni
crear otro CT o reenviar la instalación. Un fallo conocido de creación conserva la
consola y sólo libera identidad/red/capacidad tras ausencia confirmada de CT y discos.

El worker registra ingesta cada 1 s, orquestación cada 5 s y purga cada 60 min. El
poller adquiere un lease, lee por cursor, confirma DB y luego envía ACK, con heartbeat
y sin SQL abierto durante SSH. No depende del navegador ni puede iniciar trabajos.
Un lote vacío actualiza la hora de consulta exitosa, conservando la hora de captura
y la secuencia: distingue silencio del instalador de una consulta interrumpida sin
inventar mensajes o avance. Esta diferencia se verificó con reloj inyectado.
Un fallo de consulta conserva incertidumbre y no se interpreta como entrega/fallo
del instalador. Un resultado fallido sólo termina el pedido tras ingerir su cursor
final y confirmar el ACK. Si se pierde esa respuesta, el siguiente tick reintenta
la confirmación sin duplicar texto ni reinstalar; no cierra la operación dejando
el spool remoto pendiente. El confirmado queda esperando las comprobaciones de T034.

La admisión del instalador se serializa bajo el lock de capacidad y cuenta también
intenciones persistidas y trabajos inciertos: máximo dos por clúster/nodo. El resto
queda detenido con un hito de espera, sin enviar `start`. La purga conserva resumen,
cabecera e historia incluso si ya terminó la operación. IaaS y aprobación históricas
siguen en su rama original.

Verificación acotada: **10 pruebas aprobadas en 9,50 s**, incluyendo creación detenida,
ambas pérdidas de respuesta, seguimiento sin navegador, resultado fallido, cadencias,
purga y regresiones IaaS/históricas. **Una carrera PostgreSQL aprobada en 2,68 s**:
dos candidatos para un lugar libre sólo inician uno. Prueba adicional del fallo de
creación con ausencia y liberación: **1 aprobada en 1,32 s**. Dobles PVE/runner;
PostgreSQL real aislado. No se repitieron suites generales ni ensayos anteriores.
El ajuste de consulta vacía/ACK perdido se verificó sólo con los dos casos afectados
del worker; no se volvió a ejecutar el resto de esa selección.

**T032 sigue parcial**: `firewall=1` no acredita aislamiento efectivo. Faltan política
externa comprobada, TLS por instancia, estrategias definitivas y sus ensayos reales
T050/T061 antes de habilitar perfiles. No se instalaron aplicaciones nuevas en la VM
ni se certificó el clúster/red universitarios mediante estas pruebas.

## Asignador de red — T023 parcial

Nueva rama separada para perfiles `nap-application-network/1`, vacíos por defecto.
Valida direcciones/MAC/DNS, plataforma de destino, administración, gateway y solapes
con slots históricos y otros perfiles. Incluye las direcciones de administración
efectivas en el snapshot y su hash. Reserva bajo el lock único de capacidad;
replay devuelve la misma asignación sin sustituir el snapshot aprobado. La liberación
exige identidad retirada y ausencia confirmada del mismo recurso, conservando la fila.
El slot se puede reutilizar con otra identidad; las identidades no se reciclan.

Pruebas locales nuevas + regresión de red histórica: **22 aprobadas**. PostgreSQL:
dos asignaciones concurrentes toman slots diferentes y repetir una no duplica filas.
No crea invitados, DNS, certificados ni claves TLS. T023 sigue pendiente hasta unir
la creación de identidad/nonce nuevos y TLS por instancia al camino definitivo.

## Política externa común — avance de T032 (27/10/2026)

`infra/applications/job/network.py` compila una política cerrada de nftables bridge
por UUID; el paquete común la incluye. El adaptador nativo sólo la instala sobre
un CT propio, detenido y no privilegiado, con una única interfaz cuya MAC, IPv4 y
puente coinciden. Revalida la configuración inmediatamente antes del efecto.
No admite fragmentos nft, nombres de interfaz libres, comandos, puertos arbitrarios
para infraestructura, redes cliente universales ni modificaciones de tablas ajenas.

La tabla se crea de forma exclusiva en un solo lote. No se adopta una tabla ya
existente ni se hace flush/delete tras una respuesta perdida: ese caso exige
reconciliación del driver. La diferencia entre `create` y `add` está documentada
en el [manual oficial de nftables](https://netfilter.org/projects/nftables/manpage.html).
Las reglas se atan por nombre a la veth que aparecerá al arrancar; filtran forward,
input y output del bridge. Bloquean suplantación de MAC/IPv4, IPv6 y protocolos no
previstos, nodo/pares y destinos privados/especiales; las únicas excepciones de
salida son endpoints institucionales tipados y descargas HTTP(S) públicas.
Los clientes autorizados pueden entrar sólo al puerto principal, con respuestas
de la conexión permitidas sin habilitar conexiones nuevas del guest hacia clientes.

**Verificación acotada:** 38 pruebas aprobadas en 0,35 s para política, adaptador y
paquete. Una de ellas usa nftables/kernel reales en un user/network namespace
local descartable: instalación del lote, rechazo de replay sin cambio de reglas y
conservación de una tabla ajena. Se amplió esa misma prueba con tráfico Ethernet
real sobre dos pares veth y un bridge: pasa DNS autorizado; se bloquean nodo, par,
metadata link-local, MAC/IP suplantadas e IPv6. Las 18 pruebas de política pasaron
en 1,85 s tras esa ampliación. No se ejecutó la regresión completa.

**Límite explícito:** no es un ensayo Proxmox ni acredita el bridge de la VM.
T032 permanece pendiente: faltan cargar la política desde la configuración
institucional del nodo, integrarla con el driver definitivo antes del arranque,
reconciliar su estado durable y repetir las comprobaciones reales T050/T061.
No se conectó una política enviada por el usuario/SSH ni se habilitaron perfiles.
TLS por instancia (T023/T034) sigue pendiente. No se modificó la red del host,
Proxmox ni el servicio Draw.io existente.

## Arranque protegido y TLS por identidad — integración común (27/10/2026)

El runtime acepta `networks` institucionales opcionales en el archivo privado del
nodo, sin ampliar el protocolo SSH. Un registro vacío sigue siendo válido para
consultar perfiles; intentar instalar sin red preparada se rechaza. Los slots
se cotejan por IP y MAC con la configuración real del CT; no se infiere DHCP.
El worker de producción recibe el adaptador del nodo y prepara red, material TLS
y aislamiento antes de invocar cualquier estrategia. Un fallo impide entrar al
instalador y conserva incertidumbre. Los workers de pruebas pueden inyectar dobles;
el entry point instalado siempre suministra el adaptador real.

`job/tls.py` emite una clave EC y certificado de servidor únicos por resource UUID,
con SAN DNS/IP exactos y máximo 180 días, limitado además por la CA institucional.
La CA se lee sólo desde `/etc/nap/applications-011/pki/{ca.crt,ca.key}`, con recorrido
sin enlaces, archivos privados y tamaño acotado. El paquete prepara el directorio
privado `/var/lib/nap-application-tls`; cada material se escribe atómicamente bajo
lock por recurso. El replay verifica firma, clave, SAN, vigencia, CA y binding
clúster/recurso/nonce. No cambia material existente al vencer, corromperse o cambiar
la identidad. Otra instancia del mismo slot obtiene otra clave/serial.
La CA y las claves no se incorporan al manifiesto del job, respuesta SSH ni spool.
La clave de instancia se registra también en la depuración de salida antes del
instalador y se conserva al cambiar de colector. La CA privada nunca va al guest.

Pruebas afectadas del bloque: **45 aprobadas y una integración de nft omitida**
(al no repetirla por rutina). Selección posterior de TLS y conexión del adaptador:
**12 aprobadas en 0,23 s**, incluyendo dos casos añadidos y revalidación del módulo
TLS tras incorporar su loader privado. TLS se comprobó con sockets/SSL reales y
certificados efímeros de prueba: DNS/IP correctos aceptados y nombre ajeno rechazado.
También se comprobaron replay, identidad distinta, expiración, corrupción, enlaces,
permisos y ausencia de entrada al instalador tras fallo de aislamiento.

T023/T032/T034 continúan parciales: faltan configurar CA/red reales en el nodo,
conectar el borde/probes y registrar entrega automática; no se instaló este paquete
nuevo en Proxmox ni se habilitó un perfil con estas pruebas locales.

## Gateway genérico y entrega web automática — T035 / T034 parcial

Se conserva el adaptador Draw.io y se agrega una rama distinta para configuraciones
011. La apertura usa el código de un uso/sesión vigente de NAP y redirige a `/`, sin
parámetros del editor. El destino se deriva de identidad, asignación aprobada y slot
activo; revalida perfil/red y no usa URLs del navegador ni resolución DNS upstream.
Las lecturas largas de WebSocket refrescan identidad/pedido/slot desde la DB.

`application_proxy_service.py` conserva autenticación y cookies nativas, elimina
nombres NAP, rechaza dominios ajenos y convierte las cookies aceptadas a host-only
Secure. El cliente compartido no retiene cookies. Admite los siete métodos previstos,
con Origin propio obligatorio para escrituras, carga <=20 MiB y descarga <=32 MiB
en streaming; exceso de descarga corta el stream y cierra upstream. Host/SNI y CA
siguen fijados sobre la IP institucional. Redirecciones sólo al origen propio,
con rutas `_nap` reservadas. Conserva CSP nativa además de la política del gateway,
no inspecciona HTML como si todas las aplicaciones fueran Draw.io y no oculta
respuestas de login 401/403 de la aplicación. Sigue bloqueando service workers.

`application_websocket_service.py` comprueba declaración/origen antes del upgrade,
pone límites de mensajes/colas, usa TLS por host sobre IP fija y revalida acceso
cada 5 s. La pérdida de sesión cierra el canal; no hay fallback a otra URI, proxy
ambiental ni redirects, tampoco del mismo host. Se usa la API fijada de websockets
16 ([documentación primaria](https://websockets.readthedocs.io/en/16.1/reference/asyncio/client.html)).
Es tráfico de la aplicación; no sirve para escribir comandos en la consola.

La ingesta puede cerrar entrega web automáticamente sólo con cursor final guardado,
ACK confirmado, prueba terminal del job que incluya aislamiento/runtime/salud/acceso,
PVE fresco propio y arrancado, asignación/cobertura vigentes y probe HTTPS externo
del destino exacto. El probe tiene presupuesto total, TLS estricto, redirecciones
deshabilitadas y cuerpo acotado. Se confirma pedido/servicio/compromiso/consola/aviso
en una transacción, sin SQL abierto durante la conexión. No se duplican secretos
ni se exige evidencia manual. Un job exitoso con probe/destino incorrecto sigue sin
entrega y conserva recursos. La UI de acceso usa instrucciones genéricas.

Verificación proporcional: primera selección **36 aprobadas** (proxy y regresión
Draw.io); ampliación WebSocket/chunked **17 aprobadas**. Circuito de entrega con PVE
y probe dobles: los fallos de destino/prueba/estado no entregan; se corrigieron sólo
dos expectativas de fixture (objeto expirado y dominio bajo el portal de prueba).
El éxito corregido + selección gateway dio **18 aprobadas**; probes acotados **4**;
entrada HTTP real de la API/gateway con transport simulado y límites/CSP **3**.
La entrada integrada verifica cookie nativa, página propia, código NAP y revocación.
No se repitió una suite general; no se presenta MockTransport como conexión Proxmox.

**T035 completada; T034 sigue parcial**: el acceso TCP necesita configuración nativa
MariaDB y SELECT 1 autenticado/TLS desde red autorizada. Se mantiene cerrado hasta
esa implementación; un puerto abierto no entrega un pedido. T008/T036 conservan
pendiente ese alcance y las compuertas completas. Las estrategias finales y sus
pruebas físicas siguen pendientes antes de habilitar ofertas nuevas.
La selección final por cambios de refresco de identidad y acceso incluyó regresión
legacy de entrega y las cinco mutaciones de destino: **15 aprobadas en 13,57 s**.
