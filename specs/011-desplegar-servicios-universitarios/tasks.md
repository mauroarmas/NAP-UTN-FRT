# Tasks: Desplegar servicios universitarios desde imágenes y biblioteca

**Input**: `specs/011-desplegar-servicios-universitarios/` — [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/) y [quickstart.md](quickstart.md).

**Branch**: `011-desplegar-servicios-universitarios` · **Constitución**: 4.2.0.

**Tests**: obligatorios para orquestación, estados y capacidad por constitución; la spec también exige pruebas de acceso, consola, fallos y regresión. Escribir las pruebas de cada bloque antes de su implementación, comprobar que detectan la conducta ausente y después hacerlas pasar. PostgreSQL aislado acredita concurrencia; fakes y SQLite no acreditan Proxmox ni carreras SQL reales.

**Organización**: cinco historias P1 en el orden de la spec. El primer incremento demostrable es US1; no equivale a terminar la feature. No modificar servicios actuales para fabricar una demostración.

## Formato y reglas de ejecución

- `Tnnn`: identificador secuencial; `[USn]`: historia; `[P]`: trabajo independiente dentro del bloque indicado, una vez cumplidos sus prerrequisitos. No autoriza editar simultáneamente el mismo archivo.
- Rutas relativas a la raíz del repositorio. Las rutas nuevas son destinos de implementación, no archivos que ya existen.
- Alta habitual: **elegir → agregar → disponible para solicitar**. Sin crear CT/reservas por oferta, Guardadas, preparación/publicación manual, ensayo de 24 horas ni formularios de evidencia.
- Small: 1 vCPU/512 MB/4 GB; Medium: 2 vCPU/1024 MB/8 GB. Medium inicial conservador, Small sólo tras medir el perfil y aplicación completos. Sin cuotas por cátedra ni mínimos inventados.
- Mantener IaaS Ubuntu/Debian, Draw.io, `nap-guest-runner/1`, manifiestos históricos y datos existentes. No ejecutar el wrapper host Community ni ampliar el token a root.
- Los reportes técnicos siguientes son evidencia de desarrollo; no aparecen como trámites en el portal. Nunca contienen secretos, dumps privados o contraseñas de prueba.
- Compuerta real pendiente/bloqueada no se marca completada por simulación. Puede avanzarse en trabajo independiente con fakes, manteniendo deshabilitado el perfil afectado. No completar una historia ni anunciar compatibilidad mientras falte su aceptación real.

## Phase 1: Setup — pruebas y factibilidad inicial

**Objetivo**: disponer de fixtures y detectar incompatibilidades físicas antes de desarrollar sobre una suposición falsa. Reutilizar el entorno existente; no reinicializar el proyecto ni actualizar dependencias sin necesidad.

- [ ] T001 Crear fixtures compartidas de PVE, registry, runner durable, reloj y dos cátedras en `backend/tests/fixtures/despliegue_011.py`; integrarlas en `backend/tests/conftest.py` y reutilizar el aislamiento de `backend/tests/postgres/conftest.py`, sin conectarse a la base operativa.
- [ ] T002 [P] Crear la imagen de ensayo propia con salud y lectura/escritura persistente en `infra/applications/fixtures/campus-demo/Dockerfile`, `infra/applications/fixtures/campus-demo/app.py` y `infra/applications/fixtures/campus-demo/README.md`; documentar publicación en registry de ensayo sin incorporar un build al portal.
- [ ] T003 [P] Preparar el manifiesto de candidatos y el preflight de sólo lectura en `infra/laboratorio/011/candidatos.json` e `infra/laboratorio/011/preflight.py`: versiones/base/hashes, recursos, systemd, red, registry/CA y permisos; parámetros privados fuera del repositorio y perfiles inicialmente pendientes.
- [ ] T004 Tras T003, construir y ejecutar el spike controlado Docker en `infra/laboratorio/011/spike_docker.py`; verificar LXC no privilegiado, nesting/keyctl cerrados, AppArmor/seccomp activos, filesystem, pull público/privado, retirada del login y encaje en Medium; registrar resultado seguro en `docs/evidencia/011/factibilidad-docker.md`, sin fallback privilegiado o unconfined.
- [ ] T005 Tras T003, construir y ejecutar el spike del instalador guest/Core fijado en `infra/laboratorio/011/spike_community.py`; comprobar carga local, dependencias cerradas, ausencia de prompts/logs crudos/telemetría/autologin y de efectos en el nodo para MariaDB/Caddy; registrar límites y recursos en `docs/evidencia/011/factibilidad-community.md`.
- [ ] T006 Consolidar los resultados de T004/T005 y las condiciones de parada en `docs/evidencia/011/compuertas.md`: perfil/plataforma pendiente, habilitable o bloqueado y motivo; distinguir laboratorio de universidad y no habilitar perfiles de producción por estos prototipos.

**Checkpoint**: fixtures disponibles y factibilidad conocida. Las verificaciones de producción se repiten con el paquete definitivo antes de habilitar perfiles en T043/T060. Si no hay infraestructura, conservar explícitamente pendientes T004–T006 y las aceptaciones dependientes.

## Phase 2: Foundational — contratos, identidad y ejecución común

**Objetivo**: construir la base compartida de los dos orígenes. Este bloque es prerrequisito de todas las historias; no crear otra máquina de estados, ledger de capacidad o cola académica.

### Pruebas previas de la base

- [ ] T007 [P] Crear `backend/tests/test_configuracion_despliegue_011.py` con contratos estrictos, exclusión legacy/configuración, revisiones inmutables, límites de variables/rutas, perfiles bloqueados y prohibición de comandos/secretos en documentos públicos; crear `backend/tests/test_application_gateway_011.py` para aislamiento de cookies/destinos, revocación y acceso web/TCP según los contratos comunes.
- [ ] T008 [P] Crear `infra/applications/tests/test_job_protocol.py` y `infra/applications/tests/test_job_supervisor.py` para replay, fingerprint distinto, lease obsoleto, respuesta perdida, SSH caído, reboot, identidad ajena y rechazo de comandos/rutas/unidades libres; conservar pruebas de protocolos históricos en `infra/runner/tests/test_runner.py`.
- [ ] T009 [P] Crear `infra/applications/tests/test_redaction.py`, `infra/applications/tests/test_spool.py` y `backend/tests/test_ingesta_consola_011.py`: secretos partidos en cada frontera, representaciones declaradas, UTF-8, salida desconocida, ANSI/OSC, memoria/disco lleno, límites/retención, deduplicación y ACK sólo después del commit, sin retención cruda.
- [ ] T010 [P] Crear `backend/tests/postgres/test_migracion_011.py` para upgrade desde `010_06_acceso_aplicacion`, constraints/FK/índices y conservación de usuarios, cátedras, pedidos, servicios y marcadores legacy; incluir política de downgrade seguro sin pérdida silenciosa.
- [ ] T011 [P] Crear `backend/tests/postgres/test_jobs_011.py` para admisión/takeover concurrentes, unicidad de intento/execution_id, slots disjuntos y reserva de red; comprobar que reclamar lease no incrementa el intento efectivo ni duplica compromisos.

### Implementación común

- [ ] T012 Implementar esquemas discriminados y errores seguros en `backend/app/schemas/configuracion_despliegue.py` e `infra/applications/job/protocol.py`, y publicar `infra/applications/schemas/nap-deployment-1.json`; aplicar `contracts/configuracion.md` y `contracts/runner.md` con límites estrictos y sin campos libres de ejecución.
- [ ] T013 Implementar el registro institucional de perfiles en `backend/app/services/application_profiles_service.py`, `infra/applications/profiles/registry.py` y `backend/app/config.py`: revisión/hash/base exactos, estado pendiente/habilitado/bloqueado, presupuesto 45 min, dos trabajos activos por nodo y motivos seguros; no habilitar por éxito de fakes.
- [ ] T014 [P] Tras T012, crear `backend/app/models/configuracion_despliegue.py` con revisiones únicas, documento/hash canónico, validaciones de alcance declarado, autor y retirada lógica; prohibir edición de revisiones validadas.
- [ ] T015 [P] Tras T012, crear `backend/app/models/secreto_despliegue.py` con unicidad pedido/nombre/revisión, valor cifrado y contexto autenticado; sin credenciales efectivas en la configuración de oferta.
- [ ] T016 [P] Tras T012, crear `backend/app/models/intento_despliegue.py` y extender `backend/app/models/operacion_infraestructura.py` con raíz lógica, execution_id y número efectivo estable; preservar el contador histórico de reclamaciones y operaciones terminales.
- [ ] T017 [P] Tras T012, crear `backend/app/models/consola_operacion.py` con cabecera por raíz, fragmentos ordenados/deduplicados, bytes y metadatos de recorte/expiración; conservar cabecera y resultado tras purgar texto.
- [ ] T018 [P] Tras T012, crear `backend/app/models/reserva_red_aplicacion.py` con identidad única, snapshot de slot/perfil y unicidad parcial activa por dirección/slot; conservar asignaciones históricas al liberar.
- [ ] T019 Tras T014–T018, agregar FK nullable y exclusión de origen a `backend/app/models/recurso_template.py`, `backend/app/models/pedido.py` y `backend/app/models/servicio.py`; agregar campos de agenda al pedido y registrar modelos en `backend/app/models/__init__.py`, sin backfill que altere decisiones previas.
- [ ] T020 Crear `backend/alembic/versions/011_01_despliegue_aplicaciones.py` desde `010_06_acceso_aplicacion` con tablas, FK, constraints e índices del modelo; hacer pasar T010 sobre una copia aislada y verificar que no hay borrados/recreaciones de datos existentes.
- [ ] T021 Implementar `backend/app/services/secreto_despliegue_service.py` reutilizando keyring: generación por instancia, entrada write-only, referencias/revisión, HMAC contextual para idempotencia y descifrado sólo tras autorización; no regenerar en replay ni duplicar secretos nuevos en campos legacy de Servicio.
- [ ] T022 Implementar asignación transaccional de slots en `backend/app/services/reserva_red_service.py` y validación de perfiles en `backend/app/services/application_profiles_service.py`; excluir administración/pools legacy, generar resource UUID/nonce/claves nuevos y liberar slot únicamente con ausencia confirmada.
- [ ] T023 Añadir despacho cerrado `nap-application-job/1` a `infra/runner/nap_guest_runner.py` e `infra/runner/node_executor.py`: profiles/start/status/read/ack, hostkey/destinos y propietario exactos, sin shell/URLs/argv libres; mantener intactos guest-runner/1 y build-runner.
- [ ] T024 Implementar supervisor durable en `infra/applications/job/supervisor.py` e `infra/applications/job/state.py`: manifest previo al efecto, archivos atómicos sin symlinks, lock por recurso, fingerprint/generación/tombstone, unidad fija Type=exec sin PTY/pipe/wait y estado incierto tras boot/unidad sin prueba; takeover no mata ni reinicia la instalación.
- [ ] T025 Implementar redacción incremental y eventos permitidos en `infra/applications/job/redaction.py`: registrar secretos antes de ejecutar, suprimir salida desconocida con aviso fijo, eliminar controles y depurar antes de cualquier persistencia/transmisión; sin stdout/stderr crudo en journal.
- [ ] T026 Implementar colector/spool en `infra/applications/job/spool.py` y `infra/applications/job/collector.py`: source_seq, captura por stream, flush <=250 ms, fragmentos <=8 KiB, lectura <=64 KiB, almacenamiento acotado, pérdidas explícitas y purga por ACK sin bloquear la aplicación cuando no hay lector.
- [ ] T027 Completar canal privado de credenciales y distribución del paquete en `infra/applications/job/credentials.py`, `infra/runner/install.sh` e `infra/runner/README.md`: credenciales efímeras /run cargadas por systemd y retiradas del origen, permisos mínimos, stdout seguro y respaldo/rollback; ningún secreto en argv, propiedades de unidad, spool o repositorio.
- [ ] T028 Implementar `backend/app/services/application_job_client.py` con llamadas cortas, JSON acotado, hostkey fijada, reintento sólo de consultas y correlación de identidad/generación; timeout de start produce reconciliación, nunca otra ejecución automática.
- [ ] T029 Integrar la rama declarativa en `backend/app/services/perfiles_service.py`, `backend/app/services/evaluacion_service.py` y `backend/app/services/admision_service.py`: revalidación bajo locks, snapshot aprobado inmutable con hash/perfil/fuentes/red/referencias sensibles y reserva única; conservar verificación legacy e IaaS y el flujo inmediato actual para permitir el MVP antes de US3.
- [ ] T030 Integrar creación de exactamente un CT detenido en `backend/app/services/orquestacion_service.py`, `backend/app/services/identidad_infra_service.py`, `backend/app/services/proxmox_client.py` e `infra/runner/node_executor.py`: persistir identidad/intento antes del efecto, marcador propio, start=0, firewall externo antes de arrancar y acción interna fija nesting/keyctl sólo para CT propio/detenido del perfil Docker; no elevar el token.
- [ ] T031 Implementar ingesta canónica y retención en `backend/app/services/consola_operacion_service.py`: transacción corta por cabecera, deduplicación execution_id/source_seq, secuencia por raíz, commit antes de ACK, cuota 10 000 000 bytes entre intentos, purga a 30 días y resultado/historia conservados.
- [ ] T032 Integrar trabajos cortos de ingesta cada 1 s y purga en `backend/app/worker.py`, manteniendo tick de orquestación de 5 s y límite de dos instalaciones activas por nodo; no sostener transacciones SQL durante SSH, pull o instalación y no depender del navegador.
- [ ] T033 Extender `backend/app/services/service_access_service.py` y `backend/app/services/verificacion_acceso_service.py` con acceso/probes web y TCP tipados, pertenencia vigente, TLS/certificado por instancia y comprobaciones automáticas registradas; credenciales nativas por instancia y ningún éxito por un mero exit 0 o puerto abierto.
- [ ] T034 Añadir adaptador web genérico separado en `backend/app/application_gateway.py` según `contracts/acceso-ui.md`: origen por servicio, destino TLS fijado, métodos/streaming acotados, cookies nativas aisladas sin cookie jar compartido ni credenciales NAP upstream, redirects propios y WebSocket sólo declarado con revalidación cada 5 s; conservar adaptador Draw.io y bloqueo de service workers.
- [ ] T035 Ejecutar las pruebas comunes T007–T011, incluidas `backend/tests/test_application_gateway_011.py` y `backend/tests/test_ingesta_consola_011.py`; verificar cookies/headers eco, origen/redirect/SSRF, revocación HTTP/WebSocket, TCP, ACK y regresión del protocolo legacy, registrando resultados y límites en `docs/evidencia/011/base-comun.md`.

**Checkpoint**: contratos/migración/identidad/jobs/registro seguro disponibles y pruebas comunes verdes. Un trabajo no confirmado conserva contabilidad; el resultado del nodo no entrega por sí solo el pedido. Perfiles siguen pendientes hasta la comprobación real correspondiente.

## Phase 3: US1 — Ofrecer una aplicación propia desde su imagen (P1, primer incremento)

**Objetivo**: agregar una imagen como oferta y desplegarla con el flujo inmediato de pedidos existente, mediante el mismo motor para aplicaciones distintas.

**Prueba independiente**: con base común y perfil Docker comprobado, agregar campus-demo y whoami sin código específico, verificar cero invitados/reservas en el alta y entregar un pedido de cada una; campus-demo conserva un dato y se verifica pull privado con credencial institucional. No depende de US2, agenda futura o consola visual de US4.

### Pruebas primero

- [ ] T036 [P] [US1] Crear `backend/tests/test_templates_aplicaciones_011.py` y `backend/tests/test_orquestacion_aplicaciones_011.py` para POST alta/cambio de configuración, admin/CSRF/idempotencia, revisión esperada, datos inválidos, cero creación/reserva al agregar y decisiones previas conservadas; probar entrega comprobada y fallo de pull/probe sin éxito falso antes de implementar la estrategia.
- [ ] T037 [P] [US1] Crear `backend/tests/test_oci_registry_011.py` para imagen/index/manifest/config digest, arquitectura, tag cambiado, registry privado/CA, token realm/redirect/DNS maliciosos y ausencia de credenciales en errores.
- [ ] T038 [P] [US1] Crear `infra/applications/tests/test_docker_runtime.py` para pull por digest, ENTRYPOINT/CMD intactos, volúmenes declarados identificados, límites/features, recursos insuficientes, secretos efímeros, logs none y HEALTHCHECK sin retención insegura.
- [ ] T039 [P] [US1] Crear `frontend/tests/aplicacion-propia.test.jsx` con campos básicos, configuración sólo cuando se necesita, error que conserva valores, alta pendiente/éxito y control exclusivo de admin, sin preparar/publicar.

### Implementación

- [ ] T040 [US1] Implementar `backend/app/services/oci_registry_service.py`: resolver OCI sin ejecutar imágenes, distinguir digests de índice/manifest/config, validar plataforma y CA/endpoints autorizados en cada conexión, limitar descargas y no seguir credenciales a destinos ajenos.
- [ ] T041 [US1] Implementar alta/revisión inmutable en `backend/app/services/configuracion_despliegue_service.py`: validación externa acotada, mínimos reales y Config.Volumes explícitos, revalidación de perfil/rol al commit y configuración+template atómicos sin invitado/reserva/borrador visible.
- [ ] T042 [US1] Implementar POST `/templates/aplicaciones` y `/templates/{id}/configuracion` en `backend/app/routers/templates.py` y `backend/app/schemas/template.py`; respuestas compatibles, idempotencia y estado «Disponible para solicitar», conservando rutas históricas.
- [ ] T043 [US1] Empaquetar perfil/base runtime en `infra/applications/profiles/docker/ubuntu24.json` e `infra/applications/docker/runtime.py`; fijar versiones/features/storage/política, revalidar el paquete definitivo con T004 en Medium y sólo habilitar el perfil si pasa, registrándolo en `docs/evidencia/011/perfil-docker.md`.
- [ ] T044 [US1] Implementar estrategia genérica en `infra/applications/docker/deploy.py`: pull del digest aprobado, container/labels y volúmenes deterministas dentro del rootfs, recursos/capabilities/no-new-privileges, secretos por instancia y retirada de credencial del registry antes de arrancar; sin overrides de comando, montajes del nodo o daemon compartido.
- [ ] T045 [US1] Implementar borde y probes del origen Docker en `infra/applications/docker/access.py` e `infra/applications/docker/probes.py`: upstream local, HTTPS gestionado, puerto/probe aprobado, salida segura de arranque y comprobación de acceso; TCP requiere política nativa admitida, no una apertura genérica de puerto.
- [ ] T046 [US1] Conectar estrategia y confirmación final en `backend/app/services/orquestacion_service.py` y `backend/tests/test_orquestacion_aplicaciones_011.py`: job persistido, fases reales, salud/acceso y configuración comprobados antes de `pedido_service.transicionar`, aviso habitual y acceso del servicio; cubrir fallo de pull/probe sin éxito falso.
- [ ] T047 [US1] Crear `frontend/src/components/AplicacionPropiaForm.jsx` y llamadas tipadas en `frontend/src/services/api.js`: nombre/imagen/puerto, opcionales plegados sólo cuando necesarios, feedback inmediato y errores conservando datos, sin parámetros internos.
- [ ] T048 [US1] Integrar las dos entradas en `frontend/src/components/AgregarServicioModal.jsx` y `frontend/src/pages/Definiciones.jsx`: una ventana amplia/simple, catálogo administrativo sólo admin, filtros IaaS/PaaS/SaaS, ofertas IaaS/Draw.io intactas y mensaje de disponibilidad para pedir, sin Guardadas ni preparación/publicación.
- [ ] T049 [US1] Ejecutar aceptación de las dos imágenes y registry privado según `quickstart.md` y documentar `docs/evidencia/011/us1-imagenes.md`: alta <=3 min con un admin, ninguna reserva/CT por oferta, digest congelado, dato persistente y acceso sin filtrado de cookies NAP; indicar claramente qué se verificó en infraestructura real.

**Checkpoint**: US1 demostrable sin Community. Un perfil bloqueado explica el impedimento; no se anuncia instalación por validar sólo una referencia OCI.

## Phase 4: US2 — Convertir la biblioteca en ofertas desplegables (P1)

**Objetivo**: ejecutar instaladores guest compatibles con un harness común, nunca el wrapper host. MariaDB y Caddy son los dos perfiles iniciales, no una promesa de soportar todo el proveedor.

**Prueba independiente**: con base común, servicio/endpoint de alta reutilizable T041–T042 y perfiles comprobados, buscar MariaDB por nombre/categoría, agregar sin crear CT y entregar un pedido con SELECT 1 autenticado/TLS; repetir con Caddy por gateway usando el mismo motor. No necesita el runtime Docker para instalar Community ni depende de la agenda de US3; admite pedidos aprobados de fixture.

### Pruebas primero

- [ ] T050 [P] [US2] Crear `backend/tests/test_biblioteca_despliegue_011.py`: categorías/búsqueda, disponibilidad real por perfil, incompatibilidad con motivo, fallo/fallback identificado distinto de cero resultados, revisión fuente y alta sin ejecutar wrappers ni reservar.
- [ ] T051 [P] [US2] Crear `infra/applications/tests/test_community_harness.py` con loader local, manifiesto/hashes, rechazo de build.func/backend/URL libre, fuentes APT/releases mutables, preguntas, telemetría y caminos Core INSTALL_LOG/.log/.errinfo con secretos.
- [ ] T052 [P] [US2] Crear `infra/applications/tests/test_community_profiles.py`: respuestas cerradas MariaDB/Caddy, mínimos/OS, bloqueo Small, prueba TLS/credenciales únicas y denegación de instalaciones que necesitan privilegios o más de Medium.
- [ ] T053 [P] [US2] Crear `frontend/tests/biblioteca-despliegue.test.jsx` para categoría desplegable, resultado compatible/incompatible, motivo claro, fallback/reintento y botón de agregar con progreso/éxito/error, sin Guardadas o texto de preparación manual.

### Implementación

- [ ] T054 [US2] Empaquetar fuentes/licencias y locks en `infra/applications/community/sources.lock.json` e `infra/applications/community/package.py`: commits ProxmoxVE/Core de `research.md`, instaladores guest, manifiesto de helpers permitidos, snapshot Debian Release verificado y releases con versión/hash; ninguna descarga ejecutable no declarada.
- [ ] T055 [US2] Implementar `infra/applications/community/harness.py` e `infra/applications/community/policy.sh`: FUNCTIONS_FILE_PATH/local Core/loader cerrado, stdin sin preguntas, PASSWORD no vacío y SSH_ROOT=no, respuestas permitidas, sin tracing/telemetría/autologin, y reemplazo de logs/errores Core antes de usar secretos mediante el colector seguro común.
- [ ] T056 [US2] Definir perfiles declarativos pendientes en `infra/applications/profiles/community/mariadb.json` e `infra/applications/profiles/community/caddy.json`: Debian 13, Medium, fuentes/respuestas/persistencia/probes y política de secretos; ampliar otro perfil compatible por datos, sin duplicar el instalador completo.
- [ ] T057 [US2] Implementar configuración posterior tipada MariaDB en `infra/applications/community/access_mariadb.py`: PhpMyAdmin=no, base/usuario/contraseña por instancia, TLS obligatorio, clientes autorizados y SELECT 1 autenticado; no entregar root o cuentas compartidas.
- [ ] T058 [US2] Implementar configuración posterior tipada Caddy en `infra/applications/community/access_caddy.py`: xcaddy=no, var_appversion exacta/hash, servicio HTTP interno fijo, borde/gateway y probe esperado; no forzar mínimos de 6 GB a Small.
- [ ] T059 [US2] Conectar estrategia Community al supervisor común en `infra/applications/community/deploy.py` y `backend/app/services/orquestacion_service.py`: un único LXC NAP, identidad conservada, etapas/resultado seguro y confirmación automática de acceso; rechazo de script interactivo sin abrir shell ni crear otro CT.
- [ ] T060 [US2] Ejecutar el gate definitivo de harness/perfiles mediante `infra/laboratorio/011/spike_community.py`; actualizar estado habilitado/bloqueado por revisión sólo con instalación real, pruebas de secretos/red y recursos, y registrar `docs/evidencia/011/perfiles-community.md` sin marcar compatible un perfil que falle.
- [ ] T061 [US2] Enriquecer `backend/app/services/biblioteca_service.py`, `backend/app/routers/biblioteca.py` y `backend/app/schemas/biblioteca.py` con disponibilidad/motivo/perfil y categorías reales; conectar selección compatible a `backend/app/services/configuracion_despliegue_service.py`, conservando fallback y oferta Draw.io histórica.
- [ ] T062 [US2] Simplificar `frontend/src/components/BibliotecaAplicaciones.jsx` e integrar `frontend/src/components/AgregarServicioModal.jsx`: búsqueda/categoría, procedencia discreta, estado compatible y alta al catálogo por el endpoint común; incompatibilidad explica alternativa de imagen propia y un fallo no cierra ni vacía el formulario.
- [ ] T063 [US2] Ejecutar búsqueda→alta→pedido→acceso para MariaDB y Caddy, más error de fuente e instalador no admitido, y registrar `docs/evidencia/011/us2-biblioteca.md`: una sola creación por pedido, alta <=3 min, sin comando manual o publicación, cuatro fuentes/paquetes efectivos identificados según `quickstart.md`.

**Checkpoint**: biblioteca útil para desplegar los perfiles comprobados, con motivos honestos para los demás. No confundir ficha de metadata con oferta instalable.

## Phase 5: US3 — Solicitar y recibir una instancia por cátedra (P1)

**Objetivo**: completar ambos orígenes en el flujo docente y la aprobación, incluyendo Otro y programación por vigencia sin hardware para la cátedra.

**Prueba independiente**: dos cátedras reciben instancias y credenciales distintas de una oferta; repetir para ambos orígenes. Un pedido futuro reserva al aprobar pero no crea nada hasta su fecha; dos aprobaciones concurrentes no sobreasignan. La UI sólo requiere aplicación/propósito/fechas.

### Pruebas primero

- [ ] T064 [P] [US3] Crear `backend/tests/test_pedidos_aplicaciones_011.py` con Otro/imagen opcional, pertenencia, aprobación/aclaración/rechazo/reenvío, revisión congelada, valores sensibles write-only y avisos sin reservas o instalaciones prematuras.
- [ ] T065 [P] [US3] Crear `backend/tests/postgres/test_despliegue_011.py`: dos aprobaciones sobre capacidad compartida, oferta cambiada durante evaluación, dos admisiones/slots concurrentes y renovación que conserva snapshot; una única reserva efectiva por decisión.
- [ ] T066 [P] [US3] Crear `backend/tests/test_despliegue_programado_011.py` con reloj controlado: inicio inclusivo local, tick duplicado, revisión reemplazada, baja/revocación, perfil bloqueado, gracia desde max(aprobación,inicio), caída PVE y autor sistema sin CT anticipado.
- [ ] T067 [P] [US3] Ampliar `frontend/tests/pedidos-formularios.test.jsx` para ambas fuentes, Otro con imagen opcional, sin hardware docente y aprobación con tamaños admitidos/una decisión de despliegue; conservar aclaración y justificación pedagógica.

### Implementación

- [ ] T068 [US3] Extender `backend/app/schemas/pedido.py`, `backend/app/services/pedido_service.py` y `frontend/src/components/NuevoPedidoModal.jsx` para Otro con referencia opcional sin credenciales embebidas/instrucciones de uso; mantener datos como necesidad sin autorizar ejecución y conservar propósito/fechas y catálogo docente.
- [ ] T069 [US3] Completar evaluación/aprobación en `backend/app/services/evaluacion_service.py`, `backend/app/services/admision_service.py` y `backend/app/routers/pedidos.py`: hash/revisión/destino firmados, reserva indivisible, mínimos Small/Medium, ramas sin re-resolver fuentes y conflictos comprensibles; aclaración/rechazo no reserva ni instala.
- [ ] T070 [US3] Integrar valores sensibles por pedido en `backend/app/schemas/pedido.py`, `backend/app/services/secreto_despliegue_service.py` y `backend/app/routers/pedidos.py`: sólo admin cuando el perfil lo exige, cifrar antes de persistir y no conservarlos en idempotencia, snapshot/contexto/respuestas; replays usan las mismas referencias/credenciales.
- [ ] T071 [US3] Implementar `backend/app/services/despliegue_programado_service.py`: intención/revisión aprobada, clave estable por pedido/revisión, actor sistema, validación de vigencia/reserva/perfil y admisión única al inicio; decisión posterior/baja invalida la agenda anterior sin crear una máquina de estados adicional.
- [ ] T072 [US3] Registrar agenda en `backend/app/worker.py` y adaptar `backend/app/services/capacidad_service.py` y `backend/app/services/admision_service.py` para gracia de reserva futura; conservar semántica de desplegar_inmediatamente y rechazar decisiones contradictorias con 422, sin operación/CT antes de inicio.
- [ ] T073 [US3] Simplificar `frontend/src/components/AprobarPedidoModal.jsx` y `frontend/src/services/api.js`: tamaño permitido, vigencia/destino entendibles y una sola decisión de iniciar/programar; campos privados sólo cuando se requieren, evaluación obsoleta recuperable y feedback de reserva/programación/error sin UUID ni pasos extra.
- [ ] T074 [US3] Integrar entrega y avisos con `backend/app/services/pedido_service.py`, `backend/app/services/notificacion_service.py`, `backend/app/routers/servicios.py` y `frontend/src/components/AccesoServicio.jsx`: texto según producto, acceso sólo a responsable vigente/admin y notificación posterior a disponibilidad probada; conservar avisos de aclaración/rechazo/reenvío y no prometer SSO arbitrario.
- [ ] T075 [US3] Ejecutar aislamiento por dos cátedras para ambos orígenes y programación futura; documentar `docs/evidencia/011/us3-pedidos.md` con petición <=2 min, acceso ajeno denegado, datos/credenciales independientes y reserva/CT observados antes/después de inicio, sin exponer secretos.

**Checkpoint**: reserva al aprobar, instalación al inicio elegido, entrega sólo comprobada. El cambio de titular afecta acceso vigente y conserva la atribución histórica a la cátedra.

## Phase 6: US4 — Progreso y consola administrativa de lectura (P1)

**Objetivo**: hacer visible el trabajo de ambos orígenes sin terminal de escritura ni dependencia de una pestaña abierta.

**Prueba independiente**: con trabajos reales o eventos de fixture, abrir/cerrar/reabrir durante una operación de cada origen, recuperar mismo intento y mensajes sin duplicados; probar scroll, exportación, silencio, corte de consulta, recorte/vencimiento y revocación. La cátedra sólo ve progreso comprensible de lo propio.

### Pruebas primero

- [ ] T076 [P] [US4] Crear `backend/tests/test_consola_operacion_011.py` para contrato GET, cursores after/before/through_seq, tail inicial, límites, recorte/expiración, no-store y autorización admin vigente en cada página; diferenciar error de consulta y estado real.
- [ ] T077 [P] [US4] Crear `backend/tests/postgres/test_consola_011.py`: ingestas concurrentes, rollback antes de ACK, retransmisión, orden, 10 000 000 bytes entre intentos, purga a 30 días y exportación concurrente con append/purga, sin pérdida de cabecera/historia final.
- [ ] T078 [P] [US4] Crear `frontend/tests/consola-operacion.test.jsx`: negro/blanco/monoespaciado, texto literal, ventana DOM acotada, scroll pausado, páginas anteriores, deduplicación, silencio/error de consulta, intento estable, recorte y revocación durante lectura/exportación.

### Implementación

- [ ] T079 [US4] Implementar GET `/operaciones/{id}/consola` en `backend/app/routers/operaciones.py`, `backend/app/schemas/operacion.py` y `backend/app/services/consola_operacion_service.py` según `contracts/api.md`; revalidar rol/sesión actual, resolver raíz, límites/rango retenido y resultado incluso vencido, sin endpoint de escritura.
- [ ] T080 [US4] Crear `frontend/src/hooks/useConsolaOperacion.js` y cliente en `frontend/src/services/api.js`: consulta visible cada 1 s con cancelación, cursor/dedup y recuperación; mantener último estado ante fallo de consulta y borrar buffer/abortar al perder permiso, sin localStorage/caché de texto.
- [ ] T081 [US4] Crear `frontend/src/components/ConsolaOperacion.jsx`: fondo #000/texto #fff, monoespaciada, selección/teclado, fases/intento, ventana de render acotada y carga anterior, pausar al revisar historial y contador de nuevos mensajes; sin input, xterm o interpretación ANSI/HTML.
- [ ] T082 [US4] Añadir copia/descarga deliberada a `frontend/src/components/ConsolaOperacion.jsx` y `frontend/src/hooks/useConsolaOperacion.js`: congelar through_seq, paginar texto depurado con autorización por página, abortar ante revocación e informar recorte/purga sin exportar parcialmente como si fuera completo.
- [ ] T083 [US4] Actualizar `frontend/src/components/ProgresoDespliegue.jsx` y `frontend/tests/progreso-despliegue.test.jsx` para etapas reales/último avance, espera/incertidumbre/fallo/entrega, silencio y consulta interrumpida, sin porcentajes temporales o éxito inventados; cátedra sólo resumen.
- [ ] T084 [US4] Integrar «Ver consola» en `frontend/src/pages/Pedidos.jsx` y `frontend/src/pages/Servicios.jsx`, exclusivo admin; conservar la consola interactiva IaaS como acción distinta y comprobar que cerrar/reabrir no crea ni cancela operaciones.
- [ ] T085 [US4] Crear `frontend/tests/e2e/despliegue-aplicaciones.spec.js` con ambos orígenes, reabrir/reconectar/reiniciar worker, contenido malicioso literal, volumen de salida, scroll/exportación y pérdida de autorización; indicar qué casos usan backend simulado.
- [ ] T086 [US4] Instrumentar medición de captura→pantalla y apertura en `infra/laboratorio/011/medir_consola.py` y `frontend/tests/e2e/consola-rendimiento.spec.js`; ejecutar con dos trabajos reales y registro lleno y guardar p95 <=5 s/apertura <=3 s, más revisión de spool/journal/DB/export sin secretos, en `docs/evidencia/011/us4-consola.md`.

**Checkpoint**: lectura recuperable y autorizada, proceso independiente de la UI, estado final conservado aunque el texto expire. La consola no habilita respuestas a instaladores ni comandos en el nodo.

## Phase 7: US5 — Recuperar fallos y conservar el servicio (P1)

**Objetivo**: reconciliar antes de repetir, operar sin reinstalar y eliminar únicamente lo propio, liberando capacidad/red después de ausencia confirmada.

**Prueba independiente**: para cada origen perder respuesta tras crear/iniciar, cortar SSH/worker, recuperar y verificar una sola identidad/ejecución/reserva; después fallar y reintentar explícitamente, operar con datos persistentes y eliminar con identidad comprobada. Fallo de limpieza mantiene contabilidad y estado visible.

### Pruebas primero

- [ ] T087 [P] [US5] Crear `backend/tests/test_recuperacion_aplicaciones_011.py`: create/start con respuesta perdida, takeover, boot distinto, trabajo desaparecido, timeout, fuente inaccesible y fallo del probe; incertidumbre nunca permite recreación ciega o entrega.
- [ ] T088 [P] [US5] Crear `backend/tests/test_ciclo_vida_aplicaciones_011.py` para stop/start/restart sin pull/reinstalar/regenerar secretos, datos persistentes, identidad ajena, baja fallida/almacenamiento presente, renovación/vencimiento y oferta retirada.
- [ ] T089 [P] [US5] Crear `backend/tests/postgres/test_reintentos_011.py` para doble reintento y cleanup/admisión concurrentes, historial terminal intacto, raíz/cuota de logs compartida, unicidad de operación abierta y slot reutilizado con nueva identidad sólo tras ausencia.
- [ ] T090 [P] [US5] Crear `frontend/tests/recuperacion-aplicaciones.test.jsx` para fallo/reintento/incertidumbre/limpieza pendiente y confirmación destructiva clara, sin botón de reintento en un resultado desconocido ni reinicio de la instalación al consultar.

### Implementación

- [ ] T091 [US5] Extender `backend/app/services/reconciliacion_service.py` y `backend/app/services/orquestacion_service.py`: inspección de marcador/configuración/job/boot, mismo execution_id tras takeover y resultado incierto hasta prueba; observación sin repetir instalador y estados por `pedido_service.transicionar` con actor correcto.
- [ ] T092 [US5] Implementar POST `/operaciones/{id}/reintentar` en `backend/app/routers/operaciones.py` y `backend/app/services/operacion_service.py`: admin/CSRF/body vacío/idempotencia, fallo confirmado crea operación reparar e intento siguiente con raíz común; incertidumbre/ejecución/vigencia inválida devuelve 409, sin reabrir terminales ni sustituir configuración.
- [ ] T093 [US5] Integrar iniciar/detener/reiniciar en `backend/app/services/orquestacion_service.py`, `infra/applications/docker/lifecycle.py` e `infra/applications/community/lifecycle.py`: verificar identidad/snapshot/container/volúmenes y conservar credenciales/datos; no convertir una discrepancia en reinstalación automática.
- [ ] T094 [US5] Completar limpieza en `backend/app/services/orquestacion_service.py`, `backend/app/services/reserva_red_service.py` y `backend/app/services/capacidad_service.py`: destruir sólo recursos propios, confirmar ausencia de CT/almacenamiento antes de liberar red/ledger y conservar limpieza pendiente ante fallo; nueva admisión reclama identidad/secretos nuevos y revalida capacidad.
- [ ] T095 [US5] Integrar ambos orígenes con retirada/renovación/pausas/avisos en `backend/app/services/configuracion_despliegue_service.py`, `backend/app/services/vigencia_service.py`, `backend/app/services/vencimiento_service.py` e `backend/app/services/inactividad_service.py`: revisión original conservada, retirada sólo bloquea pedidos nuevos y vigencia no agrega borrado silencioso ni ensayo de 24 horas.
- [ ] T096 [US5] Integrar acciones de recuperación y baja en `frontend/src/pages/Pedidos.jsx` y `frontend/src/pages/Servicios.jsx`: resumen breve, consola disponible admin, reintento sólo admisible, limpieza pendiente visible y confirmación explícita de pérdida de datos antes de eliminar.
- [ ] T097 [US5] Ejecutar recuperación/lifecycle/limpieza reales para ambos orígenes con los scripts controlados de `infra/laboratorio/011/probar_recuperacion.py`; registrar identidades/compromisos observados, cortes, datos conservados, recursos ajenos intactos y ausencia confirmada o limpieza pendiente en `docs/evidencia/011/us5-recuperacion.md`.

**Checkpoint**: fallo entendible y recuperable sin duplicar ni ocultar capacidad. El historial académico y los intentos anteriores permanecen aunque la oferta se retire o el registro operativo se purgue.

## Phase 8: Cierre y validación transversal

**Objetivo**: comprobar la feature completa sin atribuir al entorno universitario los resultados del laboratorio.

- [ ] T098 Crear y ejecutar regresión en `backend/tests/test_regresion_servicios_011.py` y `frontend/tests/e2e/regresion-servicios-011.spec.js`: usuarios/cátedras/pedidos/historial, IaaS Ubuntu/Debian, Draw.io/acceso con NAP, manifiestos/runner legacy, renovaciones y consola IaaS; registrar conservación real sin recrear instancias en `docs/evidencia/011/regresion.md`.
- [ ] T099 Ejecutar revisión de aislamiento/secretos extremo a extremo y pruebas adversarias en `backend/tests/test_aislamiento_aplicaciones_011.py` e `infra/applications/tests/test_secret_retention.py`: SSRF/DNS/realm, cookies/headers, imagen/script malicioso, red nodo/portal/otra cátedra, revocación y secretos en spool/journal/DB/archivos operativos; conservar reporte seguro en `docs/evidencia/011/seguridad.md`.
- [ ] T100 Completar instalación/configuración técnica reutilizable en `infra/laboratorio/011/preparar_entorno.py` y `docs/despliegue-aplicaciones.md`: bases/perfiles/runner/registry/CA/DNS/TLS/slots/firewall, respaldo y rollback, preflight/fallo comprensible; separar valores de laboratorio de los datos pendientes de infraestructura universitaria, sin gestor nuevo en el portal.
- [ ] T101 Ejecutar las suites seleccionadas de `specs/011-desplegar-servicios-universitarios/quickstart.md`, `infra/applications/tests/`, regresiones afectadas, PostgreSQL aislado, Vitest, build y Playwright; registrar comandos/resultados/fallos pendientes en `docs/evidencia/011/pruebas-automatizadas.md` y no ampliar testing sin cambio/fallo que lo justifique.
- [ ] T102 Ejecutar aceptación integrada con MariaDB, Caddy, campus-demo y whoami, dos instancias por origen y un admin del proyecto según `specs/011-desplegar-servicios-universitarios/quickstart.md`; consolidar SC-001–SC-009 con medidas/enlaces y resultados simulados/locales/pendientes institucionales en `docs/evidencia/011/aceptacion.md`, de forma secuencial si falta capacidad.
- [ ] T103 Actualizar instrucciones de uso cotidiano existentes en `docs/manual-administrador.md`, `docs/manual-docente.md`, `docs/laboratorio-biblioteca.md` y `AGENTS.md`: dos caminos simples, agregar no instala, pedidos/fechas/progreso/acceso y límites reales; conservar detalles técnicos sólo en la guía de infraestructura y no añadir specs por rutina.
- [ ] T104 Revisar trazabilidad FR/SC y checklist de cierre en `specs/011-desplegar-servicios-universitarios/tasks.md` y `docs/evidencia/011/aceptacion.md`: marcar sólo tareas verificadas, dejar bloqueos reales con motivo y siguiente acción, y confirmar que ningún perfil o entorno se anuncia certificado sin su evidencia.

## Dependencias y orden de ejecución

### Grafo de fases e historias

```text
Setup T001–T006 → Base común T007–T035
Base común → US1 T036–T049
Base común + alta común T041–T042 → US2 T050–T063
Base común → US3 T064–T074 (contratos/fixtures)
Base común → US4 T076–T084 (eventos/fixtures)
Base común → US5 T087–T096 (fallos/fixtures)
US1 + US2 → aceptación de ambos orígenes T075, T085–T086, T097
US1 + US2 + US3 + US4 + US5 → Cierre T098–T104
```

La independencia significa que cada historia puede probarse con sus prerrequisitos explícitos y fixtures comunes; US2 reutiliza el alta introducida en US1, pero no su estrategia Docker. Las aceptaciones reales de ambos orígenes necesitan sus estrategias y perfiles comprobados. No simular esa dependencia para marcar completa una historia.

| Bloque | Prerrequisitos concretos / orden interno |
|---|---|
| Setup | T001/T002/T003 pueden avanzar por separado; T004/T005 dependen de T003 y se ejecutan secuencialmente si comparten nodo/capacidad; T006 reúne ambos resultados |
| Pruebas comunes | T007–T011 tras fixtures; no necesitan un PVE real |
| Esquema | T012 antes de T014–T018; T019 reúne modelos; T020 registra/migra todo antes de servicios con persistencia |
| Perfil/secretos/red | T013 + T020 antes de T021/T022; no tomar slots o credenciales legacy de otra instancia |
| Runner durable | T023 → T024 → T025 → T026 → T027 → T028; pruebas T008/T009 primero; fingerprint/persistencia preceden efectos |
| Integración común | T029 después de esquema/perfiles/secretos/red; T030 después de T023–T029; T031 después de modelos/colector/cliente; T032 después de T030/T031; T033 → T034; T035 cierra el bloque |
| US1 | T036–T039 primero; T040 → T041 → T042; T043 → T044 → T045 → T046; T047 → T048 tras endpoint; T049 requiere ambas ramas y perfil real habilitado |
| US2 | T050–T053 primero; T054 → T055 → T056 → T057 → T058 → T059 → T060; T061 requiere T041–T042 y perfiles; T062 tras API; T063 requiere perfil real y UI |
| US3 | T064–T067 primero; T068 → T069 → T070 → T071 → T072 → T073 → T074; T075 requiere US1/US2 y red real |
| US4 | T076–T078 primero; T079 → T080 → T081 → T082 → T083 → T084; T085/T086 requieren integración de ambos orígenes para aceptación completa |
| US5 | T087–T090 primero; T091 → T092 → T093 → T094 → T095 → T096; T097 requiere ambos orígenes y recuperación observable |
| Cierre | T098–T100 antes de T101/T102; T103 documenta comportamiento final y T104 verifica cierre |

El orden predeterminado para una sola persona es el numérico. Las excepciones de paralelismo siguientes son para repartir trabajo con contratos claros, no instrucciones para crear agentes automáticamente. Los servicios/routers/componentes compartidos se integran de forma secuencial, especialmente `orquestacion_service.py`, `worker.py`, `AgregarServicioModal.jsx`, `api.js`, `Pedidos.jsx` y `Servicios.jsx`.

## Ejemplos de ejecución paralela

Cada fila permite trabajar en archivos distintos dentro del bloque indicado; resolver sus dependencias antes. Correr pruebas reales simultáneas sólo con recursos/capacidad de ensayo independientes.

| Historia/bloque | Trabajos paralelos seguros | Integración posterior |
|---|---|---|
| Setup | T001 fixtures backend / T002 imagen demo / T003 preflight | Spikes tras preflight, sin colisión sobre el nodo |
| Base | T007 contratos / T008 runner / T009 redacción / T010 migración / T011 carreras | Modelos T014–T018 tras T012; registro/migración unificados después |
| US1 | T036 contrato REST / T037 resolver OCI / T038 runtime / T039 formulario | T040–T048 y aceptación conjunta T049 |
| US2 | T050 búsqueda/API / T051 harness / T052 perfiles / T053 biblioteca UI | Ensamblaje/pilotos T054–T063 |
| US3 | T064 pedidos / T065 carreras PostgreSQL / T066 reloj/agenda / T067 formularios | Reserva/agenda/UI T068–T075 |
| US4 | T076 contrato consola / T077 carreras de ingesta / T078 componente | API/hook/componente T079–T086 |
| US5 | T087 recuperación / T088 persistencia / T089 carreras de retry / T090 acciones UI | Reconciliación/lifecycle T091–T097 |

No se marcan como paralelas tareas que dependen de una implementación todavía incompleta. Entre historias pueden adelantarse pruebas con fixtures; las modificaciones de archivos comunes esperan su integración precedente.

## Estrategia de implementación y puntos de pausa

1. **Factibilidad y base**: ejecutar Setup y base común; validar contratos/fallos/migración y registrar las compuertas reales. Si un perfil está bloqueado, mantenerlo fuera del catálogo sin cambiar alcance, tamaños o permisos para forzar éxito.
2. **MVP técnico, US1**: completar imagen propia de punta a punta con dos imágenes diferentes y un pedido inmediato. Permite demostrar el motor común y pausar con una prueba concreta. No requiere terminar la búsqueda Community ni la consola visual; por ello no satisface todavía todas las historias P1.
3. **Biblioteca, US2**: agregar los dos perfiles Community con el mismo ciclo de creación, trabajo y entrega. No modificar los artefactos Draw.io existentes ni prometer ejecución universal de scripts.
4. **Flujo académico, US3**: completar Otro, programación futura, avisos y dos cátedras aisladas para ambos orígenes.
5. **Feedback, US4**: exponer el registro seguro ya capturado en la base común, con progreso real y consola administrativa de lectura. Puede adelantarse su desarrollo con eventos de fixture después de la base.
6. **Recuperación, US5**: completar reintento explícito, reconciliación, operaciones/persistencia y baja con ausencia confirmada; probar ambos orígenes.
7. **Entrega completa**: cerrar regresión, seguridad, métricas y aceptación de las cuatro aplicaciones. Publicar estado real de cada compuerta; infraestructura universitaria pendiente no se convierte en PASS del laboratorio.

Pausas cómodas: después de T006, T035 y cada checkpoint de historia. Registrar progreso verificado y operaciones de ensayo pendientes antes de pausar; no dejar instalaciones sin identidad o liberar recursos inciertos para obtener un árbol limpio.

## Trazabilidad de cobertura

| Requisitos | Tareas principales | Aceptación |
|---|---|---|
| FR-001–003 | T029, T036, T041–T042, T048, T061–T062 | T049/T063/T098 |
| FR-004–005 | T012–T015, T021, T037–T047 | T049/T102 |
| FR-006–008 | T005, T013, T050–T062 | T060/T063 |
| FR-009 | T014, T019–T020, T029, T040–T042, T054, T065, T069 | T049/T063/T101 |
| FR-010–012 | T029, T064–T073 | T075/T101 |
| FR-013 | T021–T022, T030, T033–T035, T044–T045, T057–T058 | T075/T099 |
| FR-014–016 | T008, T011, T016, T023–T032, T046, T059, T091–T092 | T035/T097 |
| FR-017 | T033–T035, T045, T057–T058, T074 | T075/T098–T099 |
| FR-018–021 | T025–T026, T031–T032, T076–T085 | T086 |
| FR-022–024 | T009, T017, T021, T025–T027, T031, T055, T076–T082 | T086/T099 |
| FR-025–027 | T087–T094, T096 | T097/T101 |
| FR-028 | T071–T072, T088, T095 | T097–T098 |
| FR-029–030 | T003–T006, T010, T020, T035, T043, T060, T098–T100 | T102–T104 |
| SC-001/008 | T049, T063, T075 | T102: un admin, <=3 min alta; <=2 min pedido |
| SC-002/003 | T049, T063, T075 | T102: cuatro apps, dos cátedras por origen, acceso ajeno denegado |
| SC-004 | T026, T032, T080–T081, T086 | T086/T102: dos trabajos, p95 <=5 s, apertura <=3 s |
| SC-005/006 | T008, T011, T087–T097 | T097/T102: interrupción, retry y limpieza por ambos orígenes |
| SC-007 | T009, T025–T027, T051, T076–T086, T099 | T099/T102: sin secretos ni nuevas lecturas sin permiso |
| SC-009 | T010, T020, T035, T098, T100–T104 | T102/T104: legado intacto y evidencia separada por entorno |

## Criterio de finalización

Todas las tareas comienzan pendientes. Marcar una tarea sólo después de implementar y verificar su resultado; un impedimento real se documenta y conserva pendiente. Una aceptación parcial o simulada no cierra SC que exigen infraestructura real. No incluir secretos en commits de evidencia. El autocommit de Spec Kit registra avances del comando; no reemplaza ninguna comprobación anterior.
