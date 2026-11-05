# Research: despliegue universitario común

Investigación inicial: 2026-10-26. Alcance vigente actualizado el 27/10/2026 por R15.
R05/R06 y sus pilotos quedaron retirados; no son dependencias de entrega.

Alcance: lectura del repositorio y fuentes primarias, sin ejecutar instaladores,
crear invitados, cambiar permisos del nodo ni acreditar compatibilidad operativa. Las decisiones
resuelven el diseño; las compuertas reales indicadas más abajo deben verificarse durante implementación.

## R01 — Integrar el ciclo existente, sin otro orquestador académico

**Decision**: reutilizar `RecursoTemplate`, `Pedido`, `Servicio`, identidad, compromiso de capacidad,
admisión, leases y máquina central de estados. Incorporar una configuración declarativa inmutable
para el origen Docker/OCI común a las dos entradas de catálogo, separada de las definiciones históricas de artefactos.

**Rationale**: `perfiles_service` y `admision_service` suponen un manifiesto 1.1, una imagen preparada,
un bundle y evidencia previa. Extender ese contrato como si una referencia Docker fuera un tar LXC
rompería las garantías existentes. Una FK nueva permite discriminar el origen sin reinterpretar
filas previas ni imponer otra pantalla de definiciones.

**Alternatives considered**: reemplazar todos los manifiestos; usar `config_extra` sin esquema;
crear otra cola de pedidos. Se descartan por migración riesgosa, validación débil o doble contabilidad.

El catálogo valida referencias/configuración y ofrece un servicio **solicitable**. No crea invitados
ni reservas. La instancia se instala con el pedido aprobado y vigencia habilitada. La constitución
4.2.0 ya expresa esta separación; no queda excepción normativa pendiente.

## R02 — Una aplicación Docker por LXC no privilegiado

**Decision**: un LXC Ubuntu 24.04 identificado por NAP por instancia, con runtime Docker preparado
por infraestructura, una imagen Linux compatible y un puerto principal. No usar Docker del nodo
Proxmox ni un daemon compartido entre cátedras. Mantener el stack del portal.

**Rationale**: preserva correspondencia recurso/reserva/servicio y reutiliza iniciar/detener/eliminar.
La ejecución de imágenes admite aplicaciones diferentes sin escribir su instalador. El perfil de
runtime contiene versiones exactas de base, Docker/containerd/runc, filesystem y política de acceso;
se valida como una unidad. El Docker 29.1.3 del host local sólo es una observación del entorno, no
una certificación del runtime anidado ni una versión impuesta a todos los nodos.

**Alternatives considered**: QEMU por servicio cambia el alcance LXC y sus mínimos; Docker rootless
agrega namespaces/cgroups sin demostrar que evite restricciones del host; OCI directo como LXC es
una tecnología distinta que upstream todavía marca experimental. No se adoptan como fallback.

**Restricción verificada**: Proxmox documenta `keyctl` para Docker y la exposición adicional de
procfs/sysfs asociada a `nesting`. No es aislamiento equivalente a una VM. Crear detenido y usar
una acción cerrada del runner para establecer exactamente el perfil autorizado y verificarlo antes
de iniciar: la comprobación upstream de features puede exigir `root@pam` para `keyctl`, por lo que
no se amplía el token API a root. No se habilita `unconfined`, LXC privilegiado, dispositivos,
capabilities o montajes del nodo para hacer pasar una prueba.

Fuentes: [pct.conf](https://pve.proxmox.com/pve-docs/pct.conf.5.html),
[código PVE de features](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm),
[PVE: contenedores y OCI](https://github.com/proxmox/pve-docs/blob/master/pct.adoc),
[Docker en Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
[caso real runc/AppArmor](https://github.com/opencontainers/runc/issues/4972).

## R03 — Fuentes inmutables y validación de imágenes

**Decision**: resolver una referencia Docker mediante OCI Distribution, sin ejecutarla: manifest,
plataforma del nodo y digest del manifest seleccionado. Conservar referencia original y digest de
índice si hay varias plataformas, sin confundirlos con ImageID/config ni con el hash de la base LXC.
La oferta validada es inmutable; la aprobación congela su revisión, perfil y red. Pull siempre por
digest; un tag cambiado no modifica la decisión ni un despliegue existente.

**Rationale**: permite alta rápida sin invitados de ensayo y evita sustituciones silenciosas.
La existencia de la imagen no prueba funcionamiento ni consumo máximo: eso se comprueba en el
pedido real y se comunica con precisión. Los mínimos del runtime incluyen base + daemon + capas
descomprimidas + escritura + volúmenes + registros. No inferir disco del tamaño comprimido.

**Alternatives considered**: ejecutar una imagen de prueba al agregar; resolver `latest` cada vez;
tratar la metadata de la imagen como garantía de recursos. No satisfacen FR-003/009/016.

Fuentes: [OCI Distribution](https://github.com/opencontainers/distribution-spec/blob/main/spec.md),
[pull por digest](https://docs.docker.com/reference/cli/docker/image/pull/).

## R04 — Registros privados y conexiones acotadas

**Decision**: perfiles institucionales de registry con endpoint HTTPS, CA y credencial de lectura
limitada a repositorios. Un resolver no acepta URLs libres, redes de administración, localhost ni
redirecciones/challenges de autenticación hacia destinos ajenos al perfil. Validar resolución DNS,
IP y TLS en cada conexión; los perfiles de registry locales sólo admiten su destino institucional
explícito. Nunca reenviar credenciales de GitHub al proveedor de metadata.

El worker entrega la credencial de pull por un canal privado temporal; la configuración de login
se elimina antes de arrancar la aplicación. No se monta Docker socket ni archivos del portal en
el contenedor de aplicación. La imagen no recibe credenciales de registry.

**Rationale**: Docker sin credential helper puede guardar autenticación en base64, que no es cifrado.
El secreto no puede quedar en argv, snapshots, contexto seguro de operaciones o consola.

**Alternatives considered**: `docker login -p`, credenciales en la referencia o daemon del nodo:
se descartan. Se usa el keyring existente y preparación técnica una vez.

Fuentes: [Docker login](https://docs.docker.com/reference/cli/docker/login/),
[CA de registry](https://docs.docker.com/engine/security/certificates/).

## R05 / R06 — Retiradas del alcance

La integración de instaladores y perfiles Community se descartó el 27/10/2026 para
reducir alcance. Sus análisis se conservan en [archivo histórico](archive/community-scripts-research.md),
sin obligaciones de implementación. R15 sustituye estas decisiones por descubrimiento
Docker Hub y reutilización del motor OCI.

## R07 — Trabajos duraderos e intento efectivo separado del lease

**Decision**: protocolo nuevo de trabajos de aplicación, manteniendo intacto `nap-guest-runner/1`
para legado. El runner del nodo admite start/status/read/ack mediante acciones cerradas y ejecuta
un programa fijo bajo una unidad systemd administrada, independiente de SSH. Persiste manifiesto,
fingerprint, estado y tombstone de la ejecución antes del efecto; ningún comando libre ni unit
arbitraria proviene del navegador. No hay `Restart=always` para una instalación interrumpida.

`OperacionInfraestructura.intento` cuenta reclamaciones del worker, no instalaciones. Agregar un
intento efectivo con UUID estable. Una recuperación de lease o lectura no crea otro intento. Un
reintento deliberado de fallo confirmado crea otra operación nativa `reparar`, vinculada a una raíz
lógica y al intento siguiente; no se reabre ni borra una operación histórica terminada. La consola
y su límite se asocian a esa raíz y abarcan todos sus intentos.

**Rationale**: el transporte actual mata SSH a los 180 s y el executor tiene 170 s; stdout es JSON
acotado y stderr se descarta. No basta conectarlo a un panel. Persistir primero, comprobar propiedad
y deduplicar `execution_id` resuelve la respuesta de inicio perdida. `lease_generation` controla
escritores y órdenes antiguas; no debe matar una instalación autorizada al cambiar el controlador.
Reiniciar el nodo exige reconciliar el trabajo y la aplicación; no reiniciar ciegamente el script.

**Alternatives considered**: tarea de FastAPI, PTY sobre SSH, timeout enorme o una segunda máquina
de estados de pedidos. No cumplen independencia, permisos o recuperación.

Fuentes: [systemd-run y servicio desacoplado](https://www.freedesktop.org/software/systemd/man/255/systemd-run.html),
[credenciales/salida systemd](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html).

## R08 — Registro seguro desde el productor

**Decision**: generar eventos estructurados seguros del runner y admitir sólo salida declarada
segura por el perfil. Descartar salida desconocida antes de cualquier spool, journal o fila y
sustituirla por un aviso de supresión. Los secretos conocidos se registran antes de ejecutar;
la depuración incremental cubre cortes de chunks y representaciones declaradas. Nunca ejecutar
ANSI/OSC/HTML/Markdown en la interfaz.

La unidad no copia salida cruda al journal; la depuración ocurre antes de cualquier
persistencia. Los riesgos de logs de Core pertenecen a la investigación retirada de R05/R06.
Docker usa driver de logging `none`; los mensajes iniciales admitidos se capturan por canal en
memoria y se depuran. No se exportan arbitrariamente archivos de log de las aplicaciones ni salidas
de HEALTHCHECK de una imagen: se usan probes de plataforma. La política conservadora se comunica
como «Parte de la salida técnica fue omitida para proteger datos sensibles».

**Rationale**: regex y diccionario no garantizan reconocer contraseñas desconocidas generadas por
un instalador. Un perfil que requiere publicar esa salida no puede declararse compatible. El
usuario obtiene progreso y diagnóstico real sin crear otro canal de exposición de credenciales.

**Alternatives considered**: `tee` hacia disco + depuración posterior, xterm o stdout ilimitado.

Fuentes: [OWASP registros](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## R09 — Consulta por cursor y almacenamiento canónico

**Decision**: PostgreSQL conserva fragmentos depurados. Ingesta del spool de trabajos activos cada
1 s, separada del tick de orquestación de 5 s; consulta visible de consola cada 1 s por Axios y
cookie existente, lotes de hasta 64 KiB. Deduplicar `(execution_id, source, source_key)` y asignar secuencia
por raíz de operación en transacción corta; ACK al runner sólo después del commit. Flush del
productor hasta 250 ms, sin depender de un navegador. Con sólo dos instalaciones activas no hace
falta otro broker ni una biblioteca de terminal.

Los hitos de creación del portal se guardan con su cambio de fase antes de start, sobre intento y
cabecera ya persistidos. Para runner la clave deriva de source_seq; para portal es estable por
fase/hito y source_seq es nulo. Ambos comparten seq/cuota, pero sólo runner tiene ACK. Un fallo de
creación sin job conserva su consola. Si hubo job, ingerir su cursor final antes del resultado final
del portal para conservar el orden causal.

**Rationale**: combina revocación por petición con p95 de captura a pantalla <=5 s. El tick actual
más consultas cada 2 s no alcanza ese presupuesto. Exportación por páginas con extremo superior
fijo revalida autorización por página y crea el archivo sólo después de completar las lecturas.

**Alternatives considered**: SSE con revalidación y buffering, WebSocket bidireccional, Redis como
registro maestro. Agregan obligaciones sin una necesidad de esta consola de lectura.

Fuentes: [SSE y reconexión](https://html.spec.whatwg.org/dev/server-sent-events.html),
[restricciones HTTPX](https://www.python-httpx.org/async/).

## R10 — Retención, límites e independencia del historial

**Decision**: 30 días desde captura y máximo **10 000 000 bytes UTF-8** por raíz de operación,
sumando intentos. Purgar fragmentos más antiguos, conservar encabezado con contadores de recorte,
intervalo retenido, resultado y motivo final. El spool tiene límite equivalente y borra ACKs;
no es otro archivo permanente. Caídas de DB o disco lleno no provocan salida cruda, éxito falso,
bloqueo infinito por falta de lector ni una nueva instalación automática.

**Rationale**: acota espacio con datos de aplicación y conserva la historia académica append-only.
La consola informa pérdida/recorte, no aparenta una ejecución sin eventos.

**Alternatives considered**: cuota por intento (se evade con reintentos), logs ilimitados, borrar
pedido/estado al purgar logs. No satisfacen FR-024 y Principio V.

## R11 — Red, acceso genérico y datos persistentes

**Decision**: reservar IP/MAC/DNS por identidad y aplicar aislamiento en PVE/red institucional
antes del arranque de código de aplicación: negar administración y tránsito entre cátedras,
permitir egress de instalación requerido e ingreso sólo desde gateway/clientes autorizados.
No confiar en UFW dentro del guest: Docker modifica reglas de publicación.

Una aplicación web obtiene un origen HTTPS exclusivo a través de un adaptador genérico separado
del de Draw.io, autorizando sesión NAP por solicitud. Mantiene la autenticación y cookies propias
de la aplicación, sin inyectar BasicAuth de Draw.io ni exigir su HTML. Se admiten HTTP usual,
streaming acotado y WebSocket con revalidación de sesión; los detalles se fijan en contrato.
TCP usa credenciales independientes y red del perfil: no se promete que cerrar NAP cierre una
conexión nativa ya establecida ni que NAP cree usuarios en cualquier software.

Volúmenes Docker deterministas dentro del rootfs LXC, nunca rutas del nodo ni volúmenes anónimos
no contabilizados. Configuración de la imagen declarada con `VOLUME` debe quedar mapeada o ser
rechazada. Detener/reiniciar conserva datos y el mismo contenedor; borrar destruye almacenamiento
sólo con autorización explícita y ausencia confirmada. No existe fallback de reinstalación para
arreglar datos de identidad distintos.

Fuentes: [firewall Docker](https://docs.docker.com/engine/install/ubuntu/),
[volúmenes](https://docs.docker.com/engine/storage/volumes/).

## R12 — Compuertas y evidencia que aún falta

**Decision**: el diseño está resuelto; compatibilidad operativa permanece **pendiente** hasta el
spike de infraestructura y ensayos reales. No se activan perfiles por inferencia ni con una fake.

- PVE/kernel/LXC/AppArmor/runtime: nested Docker no privilegiado, features exactas, filesystem,
  pull público/privado, storage y arranque con el tamaño completo. Medium inicial conservador;
  Small sólo se habilita con medición explícita para ese perfil y aplicación.
- Dos imágenes distintas (demo universitaria
  con persistencia y una imagen pública pequeña), usando los mismos mecanismos por configuración.
- Identidad, reservas, firewall, acceso, persistencia, caída de worker/respuesta perdida,
  revocación de consola, limpieza y regresión de Ubuntu/Debian/Draw.io.

Si el perfil requiere privilegios prohibidos o no cabe en Medium, se registra el bloqueo. No se
cambia a QEMU, LXC privilegiado, otro tamaño o shell interactivo sin otra decisión de alcance.
El laboratorio local no certifica la red ni el clúster universitario.

## R13 — Programación y reintentos sin reinterpretar campos existentes

**Decision**: extender explícitamente la admisión para solicitud automática futura. Hoy
`desplegar_inmediatamente` se rechaza con fecha futura y la UI lo omite: no existe un programador
que pueda darse por reutilizado. Agregar intención de despliegue y revisión de decisión al pedido;
un trabajo periódico admite el despliegue al habilitarse la vigencia, con autor sistema y clave
idempotente derivada de pedido/revisión. No crea LXC antes. Revalidar vigencia, reserva, perfil,
identidad y permisos en la admisión, sin resolver otra versión de la oferta.

La reserva de un despliegue programado no debe caducar antes de la fecha aprobada: su gracia de
admisión se ancla a la fecha inicial o a la aprobación actual si es posterior, manteniendo las
reglas de liberación y aviso existentes. No es un ensayo ni vencimiento de oferta. Una resolución
posterior o baja del pedido invalida la intención programada anterior.

Para reintentos, conservar operaciones terminales y crear otra operación `reparar` enlazada a la
raíz lógica. Si hay recurso incierto no se crea nuevo intento. Si la limpieza anterior confirmó
su ausencia, una nueva identidad y reserva necesitan la misma comprobación de capacidad bajo
bloqueo; nunca se reutiliza una identidad retirada como si el recurso siguiera presente.
Conservar en ese reintento los secretos de aplicación y referencias del mismo pedido; sólo la
identidad/nonce y claves TLS de infraestructura son nuevas. Un nuevo pedido de alta recibe secretos propios; una renovación conserva los del alta original.

**Rationale**: cumple FR-012/014/025 sin falsificar el contador de reclamaciones, ni cambiar
historia terminal, ni perder la capacidad reservada mientras se espera una fecha futura.

**Alternatives considered**: tratar el checkbox actual como programador ya implementado; reiniciar
el contador de lease; reabrir cualquier operación fallida. Son interpretaciones incorrectas del código.

## R14 — Reutilizar red sin reutilizar la identidad de un servicio retirado

**Decision**: el camino nuevo usa slots de red institucionales y una tabla de reserva activa por
identidad, liberada sólo con ausencia confirmada. Mantener el formato histórico de `instances`
para 009/010 y no reciclar sus resource UUIDs. Los slots nuevos son disjuntos y cada asignación
recibe UUID y claves de infraestructura nuevos; los secretos de aplicación de un reintento siguen
la regla del mismo pedido de R13. El perfil se configura una vez, no por cátedra o por alta.

**Rationale**: la reserva histórica toma UUIDs del archivo y considera usados todos los registrados;
tratarla como un pool reciclable agotaría direcciones después de sucesivos servicios o violaría la
unicidad de identidad. La nube pequeña necesita reutilizar capacidad de red sin borrar historia.

**Alternatives considered**: borrar identidades al dar de baja, reutilizar el nonce de un slot,
agregar manualmente un UUID en cada pedido. Rompen historia, aislamiento o simplicidad.

## Observación de metadata de la fixture pública

Consulta OCI de sólo lectura el 26/10/2026, sin pull ni ejecución:
`traefik/whoami:v1.11.0` respondió con índice
`sha256:200689790a0a0ea48ca45992e0450bc26ccab5307375b41c84dfc4f2475937ab`
y manifest linux/amd64
`sha256:4f90b33ddca9c4d4f06527070d6e503b16d71016edea036842be2a84e60c91cb`.
Es una referencia concreta para la prueba del resolver; no demuestra consumo, compatibilidad
anidada ni acceso. Ver [proyecto oficial](https://github.com/traefik/whoami).

## R15 — Docker Hub como biblioteca; un solo motor OCI

**Decision (Mauro, 27/10/2026)**: retirar Community Scripts. Las dos entradas son
búsqueda en Docker Hub y referencia de imagen propia (incluido registry privado
institucional). Ambas producen `imagen_docker` y reutilizan resolución OCI, alta,
aprobación, ejecución, consola y lifecycle. No crear otro origen por proveedor.

**Rationale**: el motor Docker ya tiene implementación parcial y elimina el segundo
harness, locks de paquetes por aplicación, perfiles MariaDB/Caddy y su mantenimiento.
La biblioteca pasa a descubrir imágenes empaquetadas. Se prueban whoami desde Hub
y campus-demo propia, con persistencia y descarga privada; no cuatro aplicaciones.
Los tamaños y el gate real de aislamiento no se reducen para ahorrar tiempo.

**API de búsqueda**: elegir un endpoint soportado de Docker Hub durante T062 y fijar
su destino, timeout, paginación y manejo de rate limits. La API OCI Distribution no
estandariza búsqueda por nombre/categoría. No deducir puertos/persistencia de una
ficha: el resolver verifica el manifiesto y sólo propone datos de la imagen cuando
son inequívocos. Categorías o distintivos sólo si el proveedor los expone; no son
prerrequisito de entrega. Ante fallo, ingresar una referencia conserva US1.

**Compatibilidad**: no ofrecer toda imagen encontrada sin validar plataforma,
recursos, acceso y configuración. No builds, Compose, comandos libres o privilegios.
Si una app requiere varios servicios o un perfil no disponible, explicar impedimento.
La procedencia oficial ayuda a elegir, no certifica seguridad ni que quepa en Medium.

**Migración mínima**: cambiar adaptador/UI de búsqueda y rechazar nuevos `community_scripts`
en alta/despacho; preservar migraciones, recibos y lectura histórica necesaria.
No tocar DB operativa ni reinstalar IaaS/Draw.io por editar el alcance.

Fuentes oficiales: [Docker Hub y búsqueda](https://docs.docker.com/docker-hub/image-library/search/),
[Hub API](https://docs.docker.com/reference/api/hub/latest/),
[Registry API / compatibilidad OCI](https://docs.docker.com/reference/api/registry/latest/),
[selección por digest](https://docs.docker.com/reference/cli/docker/image/pull/).
