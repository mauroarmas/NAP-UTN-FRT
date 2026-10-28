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
- Mantener IaaS Ubuntu/Debian, Draw.io, `nap-guest-runner/1`, manifiestos históricos y datos existentes. No ejecutar scripts del proveedor en el nodo ni ampliar el token a root.
- Los reportes técnicos siguientes son evidencia de desarrollo; no aparecen como trámites en el portal. Nunca contienen secretos, dumps privados o contraseñas de prueba.
- Compuerta real pendiente/bloqueada no se marca completada por simulación. Puede avanzarse en trabajo independiente con fakes, manteniendo deshabilitado el perfil afectado. No completar una historia ni anunciar compatibilidad mientras falte su aceptación real.

## Phase 1: Setup — pruebas y factibilidad inicial

**Objetivo**: disponer de fixtures y detectar incompatibilidades físicas antes de desarrollar sobre una suposición falsa. Reutilizar el entorno existente; no reinicializar el proyecto ni actualizar dependencias sin necesidad.

- [X] T001 Crear fixtures compartidas de PVE, registry, runner durable, reloj y dos cátedras en `backend/tests/fixtures/despliegue_011.py`; integrarlas en `backend/tests/conftest.py` y reutilizar el aislamiento de `backend/tests/postgres/conftest.py`, sin conectarse a la base operativa.
- [X] T002 [P] Crear la imagen de ensayo propia con salud y lectura/escritura persistente en `infra/applications/fixtures/campus-demo/Dockerfile`, `infra/applications/fixtures/campus-demo/app.py` y `infra/applications/fixtures/campus-demo/README.md`; documentar publicación en registry de ensayo sin incorporar un build al portal.
- [X] T003 [P] Preparar el manifiesto de candidatos y el preflight de sólo lectura en `infra/laboratorio/011/candidatos.json` e `infra/laboratorio/011/preflight.py`: versiones/base/hashes, recursos, systemd, red, registry/CA y permisos; parámetros privados fuera del repositorio y perfiles inicialmente pendientes.
- [X] T004 Tras T003, crear y ejecutar el bootstrap técnico en `infra/laboratorio/011/preparar_entorno.py`: preparar registry de ensayo TLS/acceso privado, CA/DNS/slots disjuntos/firewall, bases candidatas y permisos de ensayo con respaldo e idempotencia; verificar con `infra/laboratorio/011/preflight.py` antes de los spikes, sin habilitar perfiles ni modificar servicios existentes. No depender de paquetes definitivos aún no construidos; instalarlos después en T028/T050 y conservar parámetros privados fuera del repositorio.
- [X] T005 Tras T004, construir y ejecutar el spike controlado Docker en `infra/laboratorio/011/spike_docker.py`; verificar LXC no privilegiado, nesting/keyctl cerrados, AppArmor/seccomp activos, filesystem, pull público/privado, retirada del login y encaje en Medium; registrar resultado seguro en `docs/evidencia/011/factibilidad-docker.md`, sin fallback privilegiado o unconfined.
- **T006 — retirada del alcance**: spike Community completado históricamente; conservar evidencia, no repetir ni contarlo como trabajo activo.
- [X] T007 Consolidar el resultado Docker de T005 (T006 queda como antecedente histórico, no dependencia activa) y las condiciones de parada en `docs/evidencia/011/compuertas.md`: perfil/plataforma pendiente, habilitable o bloqueado y motivo; distinguir laboratorio de universidad y no habilitar perfiles de producción por estos prototipos.

**Checkpoint**: fixtures disponibles y factibilidad conocida. Las verificaciones de producción se repiten con el paquete definitivo antes de habilitar perfiles en T050. Si no hay infraestructura, conservar pendientes sólo las tareas activas y aceptaciones realmente bloqueadas; T006 está retirada.

## Phase 2: Foundational — contratos, identidad y ejecución común

**Validación acordada con Mauro**: ejecutar selecciones afectadas por bloque, sin regresión
completa entre fases. Los checks críticos y las aceptaciones reales se conservan; las suites
generales se reservan para un hito importante o la entrega. No repetir una comprobación verde
si el cambio siguiente no la afecta. No eliminar pruebas existentes por este ajuste.

**Objetivo**: construir la base del motor Docker común. Este bloque es prerrequisito de todas las historias; no crear otra máquina de estados, ledger de capacidad o cola académica.

### Pruebas previas de la base

- [X] T008 [P] Crear `backend/tests/test_configuracion_despliegue_011.py` con contratos estrictos, exclusión legacy/configuración, revisiones inmutables, límites de variables/rutas, perfiles bloqueados y prohibición de comandos/secretos en documentos públicos; crear `backend/tests/test_application_gateway_011.py` para aislamiento de cookies/destinos, revocación y acceso web/TCP según los contratos comunes.
- [X] T009 [P] Crear `infra/applications/tests/test_job_protocol.py` y `infra/applications/tests/test_job_supervisor.py` para replay, fingerprint distinto, lease obsoleto, respuesta perdida, SSH caído, reboot, identidad ajena y rechazo de comandos/rutas/unidades libres; conservar pruebas de protocolos históricos en `infra/runner/tests/test_runner.py`.
- [X] T010 [P] Crear `infra/applications/tests/test_redaction.py`, `infra/applications/tests/test_spool.py` y `backend/tests/test_ingesta_consola_011.py`: secretos partidos en cada frontera, representaciones declaradas, UTF-8, salida desconocida, ANSI/OSC, memoria/disco lleno, límites/retención y ACK sólo tras commit; probar eventos portal sin job, colisiones de claves locales entre productores, replay de hitos y orden causal sin retención cruda.
- [X] T011 [P] Crear `backend/tests/postgres/test_migracion_011.py` para upgrade desde `010_06_acceso_aplicacion`, constraints/FK/índices y conservación de usuarios, cátedras, pedidos, servicios y marcadores legacy; incluir política de downgrade seguro sin pérdida silenciosa.
- [X] T012 [P] Crear `backend/tests/postgres/test_jobs_011.py` para admisión/takeover concurrentes, unicidad de intento/execution_id, slots disjuntos y reserva de red; comprobar que reclamar lease no incrementa el intento efectivo ni duplica compromisos.

### Implementación común

- [X] T013 Implementar esquemas discriminados y errores seguros en `backend/app/schemas/configuracion_despliegue.py` e `infra/applications/job/protocol.py`, y publicar `infra/applications/schemas/nap-deployment-1.json`; aplicar `contracts/configuracion.md` y `contracts/runner.md` con límites estrictos y sin campos libres de ejecución.
- [X] T014 Implementar el registro institucional de perfiles en `backend/app/services/application_profiles_service.py`, `infra/applications/profiles/registry.py` y `backend/app/config.py`: revisión/hash/base exactos, estado pendiente/habilitado/bloqueado, presupuesto 45 min, dos trabajos activos por nodo y motivos seguros; no habilitar por éxito de fakes.
- [X] T015 [P] Tras T013, crear `backend/app/models/configuracion_despliegue.py` con revisiones únicas, documento/hash canónico, validaciones de alcance declarado, autor y retirada lógica; prohibir edición de revisiones validadas.
- [X] T016 [P] Tras T013, crear `backend/app/models/secreto_despliegue.py` con unicidad pedido/nombre/revisión, valor cifrado y contexto autenticado; sin credenciales efectivas en la configuración de oferta.
- [X] T017 [P] Tras T013, crear `backend/app/models/intento_despliegue.py` y extender `backend/app/models/operacion_infraestructura.py` con raíz lógica, execution_id y número efectivo estable; preservar el contador histórico de reclamaciones y operaciones terminales.
- [X] T018 [P] Tras T013, crear `backend/app/models/consola_operacion.py` con cabecera por raíz, fragmentos con source/source_key y source_seq sólo runner, unicidad (execution_id, source, source_key), bytes y metadatos de recorte/expiración; conservar cabecera y resultado tras purgar texto.
- [X] T019 [P] Tras T013, crear `backend/app/models/reserva_red_aplicacion.py` con identidad única, snapshot de slot/perfil y unicidad parcial activa por dirección/slot; conservar asignaciones históricas al liberar.
- [X] T020 Tras T015–T019, agregar FK nullable y exclusión de origen a `backend/app/models/recurso_template.py`, `backend/app/models/pedido.py` y `backend/app/models/servicio.py`; agregar campos de agenda al pedido y registrar modelos en `backend/app/models/__init__.py`, sin backfill que altere decisiones previas.
- [X] T021 Crear `backend/alembic/versions/011_01_despliegue_aplicaciones.py` desde `010_06_acceso_aplicacion` con tablas, FK, constraints e índices del modelo; hacer pasar T011 sobre una copia aislada y verificar que no hay borrados/recreaciones de datos existentes.
- [X] T022 Implementar `backend/app/services/secreto_despliegue_service.py` reutilizando keyring: generación por pedido, entrada write-only, referencias/revisión, HMAC contextual para idempotencia y descifrado sólo tras autorización; conservar valores/referencias al reintentar el mismo pedido incluso tras recrear el CT, generar secretos propios para otro pedido de alta y no duplicarlos en campos legacy de Servicio.
- [ ] T023 Implementar asignación transaccional de slots en `backend/app/services/reserva_red_service.py` y validación de perfiles en `backend/app/services/application_profiles_service.py`; excluir administración/pools legacy, generar resource UUID/nonce/claves nuevos y liberar slot únicamente con ausencia confirmada.
- [X] T024 Añadir despacho cerrado `nap-application-job/1` a `infra/runner/nap_guest_runner.py` e `infra/runner/node_executor.py`: profiles/start/status/read/ack, hostkey/destinos y propietario exactos, sin shell/URLs/argv libres; mantener intactos guest-runner/1 y build-runner.
- [X] T025 Implementar supervisor durable en `infra/applications/job/supervisor.py` e `infra/applications/job/state.py`: manifest previo al efecto, archivos atómicos sin symlinks, lock por recurso, fingerprint/generación/tombstone, unidad fija Type=exec sin PTY/pipe/wait y estado incierto tras boot/unidad sin prueba; takeover no mata ni reinicia la instalación.
- [X] T026 Implementar redacción incremental y eventos permitidos en `infra/applications/job/redaction.py`: registrar secretos antes de ejecutar, suprimir salida desconocida con aviso fijo, eliminar controles y depurar antes de cualquier persistencia/transmisión; sin stdout/stderr crudo en journal.
- [X] T027 Implementar colector/spool en `infra/applications/job/spool.py` y `infra/applications/job/collector.py`: source_seq, captura por stream, flush <=250 ms, fragmentos <=8 KiB, lectura <=64 KiB, almacenamiento acotado, pérdidas explícitas y purga por ACK sin bloquear la aplicación cuando no hay lector.
- [X] T028 Completar canal privado y distribución del paquete común en `infra/applications/job/credentials.py`, `infra/runner/install.sh` e `infra/runner/README.md`; instalar el paquete construido mediante `infra/laboratorio/011/preparar_entorno.py` antes de sus pruebas reales, con respaldo/rollback y perfiles pendientes. Credenciales efímeras /run cargadas por systemd y retiradas del origen; ningún secreto en argv, propiedades de unidad, journal, spool o repositorio.
- [X] T029 Implementar `backend/app/services/application_job_client.py` con llamadas cortas, JSON acotado, hostkey fijada, reintento sólo de consultas y correlación de identidad/generación; timeout de start produce reconciliación, nunca otra ejecución automática.
- [X] T030 Integrar la rama declarativa en `backend/app/services/perfiles_service.py`, `backend/app/services/evaluacion_service.py` y `backend/app/services/admision_service.py`: revalidación bajo locks, snapshot aprobado inmutable con hash/perfil/fuentes/red/referencias sensibles y reserva única; conservar verificación legacy e IaaS y el flujo inmediato actual para permitir el MVP antes de US3.
- [X] T031 Implementar ingesta canónica, emisor de hitos portal y retención en `backend/app/services/consola_operacion_service.py`: lock de cabecera, deduplicación (execution_id, source, source_key), source_key derivada de source_seq para runner y estable por intento/fase/hito para portal, secuencia por raíz y evento portal con fase en la misma transacción. Sólo runner recibe ACK tras commit; si hubo job, ingerir su cursor final antes del hito final del portal. Cuota compartida 10 000 000 bytes/30 días con resultado/historia conservados; consulta sin job válida.
- [ ] T032 Integrar creación de exactamente un CT detenido en `backend/app/services/orquestacion_service.py`, `backend/app/services/identidad_infra_service.py`, `backend/app/services/proxmox_client.py` e `infra/runner/node_executor.py`: tras T031, persistir identidad/intento/cabecera y hito seguro antes del efecto; guardar hitos con cambios de fase incluso ante fallo sin job. Marcador propio, start=0, firewall externo y acción fija nesting/keyctl sólo para CT propio/detenido Docker; no elevar el token.
- [X] T033 Integrar trabajos cortos de ingesta cada 1 s y purga en `backend/app/worker.py`, manteniendo tick de orquestación de 5 s y límite de dos instalaciones activas por nodo; no sostener transacciones SQL durante SSH, pull o instalación y no depender del navegador.
- [ ] T034 Extender `backend/app/services/service_access_service.py` y `backend/app/services/verificacion_acceso_service.py` con acceso/probes web y TCP tipados, pertenencia vigente, TLS/certificado por instancia y comprobaciones automáticas registradas; credenciales nativas por instancia y ningún éxito por un mero exit 0 o puerto abierto.
- [X] T035 Añadir adaptador web genérico separado en `backend/app/application_gateway.py` según `contracts/acceso-ui.md`: origen por servicio, destino TLS fijado, métodos/streaming acotados, cookies nativas aisladas sin cookie jar compartido ni credenciales NAP upstream, redirects propios y WebSocket sólo declarado con revalidación cada 5 s; conservar adaptador Draw.io y bloqueo de service workers.
- [ ] T036 Ejecutar las pruebas comunes T008–T012, incluidas `backend/tests/test_application_gateway_011.py` y `backend/tests/test_ingesta_consola_011.py`; verificar cookies/headers eco, origen/redirect/SSRF, revocación HTTP/WebSocket, TCP, ACK y regresión del protocolo legacy, registrando resultados y límites en `docs/evidencia/011/base-comun.md`.

**Checkpoint**: contratos/migración/identidad/jobs/registro seguro disponibles y pruebas comunes verdes. Un trabajo no confirmado conserva contabilidad; el resultado del nodo no entrega por sí solo el pedido. Perfiles siguen pendientes hasta la comprobación real correspondiente.

## Phase 3: US1 — Ofrecer una aplicación propia desde su imagen (P1, primer incremento)

**Objetivo**: agregar una imagen como oferta y desplegarla con el flujo inmediato de pedidos existente, mediante el mismo motor para aplicaciones distintas.

**Prueba independiente**: con base común y perfil Docker comprobado, agregar campus-demo y whoami sin código específico, verificar cero invitados/reservas en el alta y entregar un pedido de cada una; campus-demo conserva un dato y se verifica pull privado con credencial institucional. No depende de US2, agenda futura o consola visual de US4.

### Pruebas primero

- [ ] T037 [P] [US1] Crear `backend/tests/test_templates_aplicaciones_011.py` y `backend/tests/test_orquestacion_aplicaciones_011.py` para POST alta/cambio de configuración, admin/CSRF/idempotencia, revisión esperada, datos inválidos, cero creación/reserva al agregar y decisiones previas conservadas; probar entrega comprobada y fallo de pull/probe sin éxito falso antes de implementar la estrategia.
- [X] T038 [P] [US1] Crear `backend/tests/test_oci_registry_011.py` para imagen/index/manifest/config digest, arquitectura, tag cambiado, registry privado/CA, token realm/redirect/DNS maliciosos y ausencia de credenciales en errores.
- [ ] T039 [P] [US1] Crear `infra/applications/tests/test_docker_runtime.py` para pull por digest, ENTRYPOINT/CMD intactos, volúmenes declarados identificados, límites/features, recursos insuficientes, secretos efímeros, logs none y HEALTHCHECK sin retención insegura.
- [X] T040 [P] [US1] Crear `frontend/tests/aplicacion-propia.test.jsx` con campos básicos, configuración sólo cuando se necesita, error que conserva valores, alta pendiente/éxito y control exclusivo de admin, sin preparar/publicar.

### Implementación

- [X] T041 [US1] Implementar `backend/app/services/oci_registry_service.py`: resolver OCI sin ejecutar imágenes, distinguir digests de índice/manifest/config, validar plataforma y CA/endpoints autorizados en cada conexión, limitar descargas y no seguir credenciales a destinos ajenos.
- [X] T042 [US1] Implementar alta/revisión inmutable en `backend/app/services/configuracion_despliegue_service.py`: validación externa acotada, mínimos reales y Config.Volumes explícitos, revalidación de perfil/rol al commit y configuración+template atómicos sin invitado/reserva/borrador visible.
- [X] T043 [US1] Implementar POST `/templates/aplicaciones` y `/templates/{id}/configuracion` en `backend/app/routers/templates.py` y `backend/app/schemas/template.py`; respuestas compatibles, idempotencia y estado «Disponible para solicitar», conservando rutas históricas.
- [ ] T044 [US1] Empaquetar perfil/base runtime en `infra/applications/profiles/docker/ubuntu24.json` e `infra/applications/docker/runtime.py`; fijar versiones/features/storage/política y registrar su alcance en `docs/evidencia/011/perfil-docker.md`. Mantener perfil pendiente hasta instalar y validar la estrategia definitiva en T050, sin habilitarlo con módulos todavía incompletos.
- [ ] T045 [US1] Implementar estrategia genérica en `infra/applications/docker/deploy.py`: pull del digest aprobado, container/labels y volúmenes deterministas dentro del rootfs, recursos/capabilities/no-new-privileges, secretos por instancia y retirada de credencial del registry antes de arrancar; sin overrides de comando, montajes del nodo o daemon compartido.
- [ ] T046 [US1] Implementar borde y probes del origen Docker en `infra/applications/docker/access.py` e `infra/applications/docker/probes.py`: upstream local, HTTPS gestionado, puerto/probe aprobado, salida segura de arranque y comprobación de acceso; TCP requiere política nativa admitida, no una apertura genérica de puerto.
- [ ] T047 [US1] Conectar estrategia y confirmación final en `backend/app/services/orquestacion_service.py` y `backend/tests/test_orquestacion_aplicaciones_011.py`: job persistido, fases reales, salud/acceso y configuración comprobados antes de `pedido_service.transicionar`, aviso habitual y acceso del servicio; cubrir fallo de pull/probe sin éxito falso.
- [X] T048 [US1] Crear `frontend/src/components/AplicacionPropiaForm.jsx` y llamadas tipadas en `frontend/src/services/api.js`: nombre/imagen/puerto, opcionales plegados sólo cuando necesarios, feedback inmediato y errores conservando datos, sin parámetros internos.
- [X] T049 [US1] Integrar las dos entradas en `frontend/src/components/AgregarServicioModal.jsx` y `frontend/src/pages/Definiciones.jsx`: una ventana amplia/simple, catálogo administrativo sólo admin, filtros IaaS/PaaS/SaaS, ofertas IaaS/Draw.io intactas y mensaje de disponibilidad para pedir, sin Guardadas ni preparación/publicación.
- [ ] T050 [US1] Tras T044–T047, instalar el paquete Docker definitivo con `infra/laboratorio/011/preparar_entorno.py`, revalidar T005 y habilitar el perfil sólo si pasa; después ejecutar aceptación de campus-demo, whoami y registry privado según `quickstart.md`. Registrar en `docs/evidencia/011/us1-imagenes.md` alta <=3 min, cero reserva/CT por oferta, digest congelado, dato persistente y acceso sin cookies NAP filtradas, distinguiendo prueba real de simulación.

**Checkpoint**: US1 demuestra el motor OCI común. Un perfil bloqueado explica el impedimento; no se anuncia instalación por validar sólo una referencia OCI.

## Phase 4: US2 — Docker Hub como biblioteca del motor OCI (P1)

**Objetivo**: reemplazar Community Scripts por búsqueda en Docker Hub y reutilizar el alta/ejecución de US1. No construir otro runtime ni crear adaptadores por aplicación.

**Prueba independiente**: buscar whoami, seleccionar referencia, completar lo faltante en el formulario común y agregar sin CT/reserva. Entregar desde un pedido con el mismo motor ya validado en T050. Ingresar una referencia propia sigue disponible si falla la búsqueda.

### Pruebas primero

- [X] T051 [P] [US2] Crear o adaptar `backend/tests/test_biblioteca_despliegue_011.py` para búsqueda Docker Hub por nombre/paginación, referencia seleccionada validada por OCI, timeout/rate limit frente a cero resultados, categorías ausentes no bloqueantes y alta idempotente sin CT/reserva. Probar rechazo de altas/despacho nuevos `community_scripts` sin borrar datos legacy.
- [X] T054 [P] [US2] Crear o adaptar `frontend/tests/biblioteca-despliegue.test.jsx`: Docker Hub como biblioteca, datos/procedencia disponibles, categoría opcional, selección al formulario OCI común, referencia manual ante fallo, progreso/éxito/error conservando datos; sin Community, Guardadas o preparar/publicar.

### Implementación

- [X] T062 [US2] Reemplazar el proveedor en `backend/app/services/biblioteca_service.py`, `backend/app/routers/biblioteca.py` y `backend/app/schemas/biblioteca.py` por descubrimiento Docker Hub con endpoints fijos, límites, paginación y errores explícitos. Reusar `oci_registry_service.py` y `configuracion_despliegue_service.py` para validar/agregar: mismo `imagen_docker`, sin crear otra estrategia ni confiar en metadata como prueba. Retirar Community del alta/despacho y configuración por defecto, incluidos discriminadores/StrategyLoader expuestos para nuevas ejecuciones; preservar lectura/esquema/recibos legacy cuando sea necesario, sin reset DB. Categorías sólo si la API las ofrece; no construir caché/espejo nuevo.
- [X] T063 [US2] Adaptar `frontend/src/components/BibliotecaAplicaciones.jsx` y `AgregarServicioModal.jsx`: entradas «Docker Hub» e «Imagen propia», búsqueda por nombre, selección que precarga `AplicacionPropiaForm.jsx` y alta común. Puerto y demás campos sólo si faltan; omitir categorías inexistentes, mensajes breves y alternativa manual ante fallo. Retirar controles/consultas del proveedor Community, conservando oferta Draw.io histórica.
- [X] T064 [US2] Ejecutar búsqueda Hub→alta→pedido→acceso con whoami, fallo de búsqueda y referencia manual; registrar `docs/evidencia/011/us2-biblioteca.md`: <=3 min de alta, cero CT/reserva al agregar y un solo despliegue por pedido. Reutilizar evidencia del motor T050 cuando coincida paquete/perfil; no repetir sus pruebas de persistencia/registry privado sólo por cambiar la entrada de búsqueda.

**Retiradas, no pendientes ni completadas por este cambio**: T052, T053 y T055–T061 (tests/harness/Core/locks/perfiles/pilotos Community). Sus IDs quedan reservados; no reasignarlos. T006 conserva únicamente su antecedente histórico.

**Checkpoint**: Docker Hub e imagen propia convergen en una configuración y ejecución OCI. Una búsqueda exitosa no habilita un perfil bloqueado ni acredita instalación.

## Phase 5: US3 — Solicitar y recibir una instancia por cátedra (P1)

**Objetivo**: completar el motor Docker común en el flujo docente y la aprobación, incluyendo Otro y programación por vigencia sin hardware para la cátedra.

**Prueba independiente**: dos cátedras reciben instancias y credenciales distintas de una oferta del motor Docker común. Un pedido futuro reserva al aprobar pero no crea nada hasta su fecha; dos aprobaciones concurrentes no sobreasignan. La UI sólo requiere aplicación/propósito/fechas.

### Pruebas primero

- [ ] T065 [P] [US3] Crear `backend/tests/test_pedidos_aplicaciones_011.py` con Otro/imagen opcional, pertenencia, aprobación/aclaración/rechazo/reenvío, revisión congelada, valores sensibles write-only y avisos sin reservas o instalaciones prematuras.
- [ ] T066 [P] [US3] Crear `backend/tests/postgres/test_despliegue_011.py`: dos aprobaciones sobre capacidad compartida, oferta cambiada durante evaluación, dos admisiones/slots concurrentes y renovación que conserva snapshot; una única reserva efectiva por decisión.
- [ ] T067 [P] [US3] Crear `backend/tests/test_despliegue_programado_011.py` con reloj controlado: inicio inclusivo local, tick duplicado, revisión reemplazada, baja/revocación, perfil bloqueado, gracia desde max(aprobación,inicio), caída PVE y autor sistema sin CT anticipado.
- [ ] T068 [P] [US3] Ampliar `frontend/tests/pedidos-formularios.test.jsx` para las dos entradas de imágenes, Otro con imagen opcional, sin hardware docente y aprobación con tamaños admitidos/una decisión de despliegue; conservar aclaración y justificación pedagógica.

### Implementación

- [ ] T069 [US3] Extender `backend/app/schemas/pedido.py`, `backend/app/services/pedido_service.py` y `frontend/src/components/NuevoPedidoModal.jsx` para Otro con referencia opcional sin credenciales embebidas/instrucciones de uso; mantener datos como necesidad sin autorizar ejecución y conservar propósito/fechas y catálogo docente.
- [ ] T070 [US3] Completar evaluación/aprobación en `backend/app/services/evaluacion_service.py`, `backend/app/services/admision_service.py` y `backend/app/routers/pedidos.py`: hash/revisión/destino firmados, reserva indivisible, mínimos Small/Medium, ramas sin re-resolver fuentes y conflictos comprensibles; aclaración/rechazo no reserva ni instala.
- [ ] T071 [US3] Integrar valores sensibles por pedido en `backend/app/schemas/pedido.py`, `backend/app/services/secreto_despliegue_service.py` y `backend/app/routers/pedidos.py`: sólo admin cuando el perfil lo exige, cifrar antes de persistir y no conservarlos en idempotencia, snapshot/contexto/respuestas; replays usan las mismas referencias/credenciales.
- [ ] T072 [US3] Implementar `backend/app/services/despliegue_programado_service.py`: intención/revisión aprobada, clave estable por pedido/revisión, actor sistema, validación de vigencia/reserva/perfil y admisión única al inicio; decisión posterior/baja invalida la agenda anterior sin crear una máquina de estados adicional.
- [ ] T073 [US3] Registrar agenda en `backend/app/worker.py` y adaptar `backend/app/services/capacidad_service.py` y `backend/app/services/admision_service.py` para gracia de reserva futura; conservar semántica de desplegar_inmediatamente y rechazar decisiones contradictorias con 422, sin operación/CT antes de inicio.
- [ ] T074 [US3] Simplificar `frontend/src/components/AprobarPedidoModal.jsx` y `frontend/src/services/api.js`: tamaño permitido, vigencia/destino entendibles y una sola decisión de iniciar/programar; campos privados sólo cuando se requieren, evaluación obsoleta recuperable y feedback de reserva/programación/error sin UUID ni pasos extra.
- [ ] T075 [US3] Integrar entrega y avisos con `backend/app/services/pedido_service.py`, `backend/app/services/notificacion_service.py`, `backend/app/routers/servicios.py` y `frontend/src/components/AccesoServicio.jsx`: texto según producto, acceso sólo a responsable vigente/admin y notificación posterior a disponibilidad probada; conservar avisos de aclaración/rechazo/reenvío y no prometer SSO arbitrario.
- [ ] T076 [US3] Ejecutar aislamiento por dos cátedras para el motor Docker común y programación futura; documentar `docs/evidencia/011/us3-pedidos.md` con petición <=2 min, acceso ajeno denegado, datos/credenciales independientes y reserva/CT observados antes/después de inicio, sin exponer secretos.

**Checkpoint**: reserva al aprobar, instalación al inicio elegido, entrega sólo comprobada. El cambio de titular afecta acceso vigente y conserva la atribución histórica a la cátedra.

## Phase 6: US4 — Progreso y consola administrativa de lectura (P1)

**Objetivo**: hacer visible el trabajo de el motor Docker común sin terminal de escritura ni dependencia de una pestaña abierta.

**Prueba independiente**: con trabajos reales o eventos de fixture, abrir/cerrar/reabrir durante operaciones del motor común, recuperar mismo intento y mensajes sin duplicados; probar scroll, exportación, silencio, corte de consulta, recorte/vencimiento y revocación. La cátedra sólo ve progreso comprensible de lo propio.

### Pruebas primero

- [ ] T077 [P] [US4] Crear `backend/tests/test_consola_operacion_011.py` para contrato GET, cursores after/before/through_seq, tail inicial, límites, recorte/expiración, no-store y admin vigente por página; probar consola de creación fallida antes de job y distinguir error de consulta y estado real.
- [ ] T078 [P] [US4] Crear `backend/tests/postgres/test_consola_011.py`: ingestas concurrentes portal/runner con claves locales iguales, hitos idempotentes, rollback antes de ACK sólo runner, orden causal y secuencia global, 10 000 000 bytes entre intentos/ambos productores, purga a 30 días y exportación concurrente, sin perder cabecera/historia final.
- [ ] T079 [P] [US4] Crear `frontend/tests/consola-operacion.test.jsx`: negro/blanco/monoespaciado, texto literal, ventana DOM acotada, scroll pausado, páginas anteriores, deduplicación, silencio/error de consulta, intento estable, recorte y revocación durante lectura/exportación.

### Implementación

- [ ] T080 [US4] Implementar GET `/operaciones/{id}/consola` en `backend/app/routers/operaciones.py`, `backend/app/schemas/operacion.py` y `backend/app/services/consola_operacion_service.py` según `contracts/api.md`; revalidar rol/sesión actual, resolver raíz, límites/rango retenido y resultado incluso vencido, sin endpoint de escritura.
- [ ] T081 [US4] Crear `frontend/src/hooks/useConsolaOperacion.js` y cliente en `frontend/src/services/api.js`: consulta visible cada 1 s con cancelación, cursor/dedup y recuperación; mantener último estado ante fallo de consulta y borrar buffer/abortar al perder permiso, sin localStorage/caché de texto.
- [ ] T082 [US4] Crear `frontend/src/components/ConsolaOperacion.jsx`: fondo #000/texto #fff, monoespaciada, selección/teclado, fases/intento, ventana de render acotada y carga anterior, pausar al revisar historial y contador de nuevos mensajes; sin input, xterm o interpretación ANSI/HTML.
- [ ] T083 [US4] Añadir copia/descarga deliberada a `frontend/src/components/ConsolaOperacion.jsx` y `frontend/src/hooks/useConsolaOperacion.js`: congelar through_seq, paginar texto depurado con autorización por página, abortar ante revocación e informar recorte/purga sin exportar parcialmente como si fuera completo.
- [ ] T084 [US4] Actualizar `frontend/src/components/ProgresoDespliegue.jsx` y `frontend/tests/progreso-despliegue.test.jsx` para etapas reales/último avance, espera/incertidumbre/fallo/entrega, silencio y consulta interrumpida, sin porcentajes temporales o éxito inventados; cátedra sólo resumen.
- [ ] T085 [US4] Integrar «Ver consola» en `frontend/src/pages/Pedidos.jsx` y `frontend/src/pages/Servicios.jsx`, exclusivo admin; conservar la consola interactiva IaaS como acción distinta y comprobar que cerrar/reabrir no crea ni cancela operaciones.
- [ ] T086 [US4] Crear `frontend/tests/e2e/despliegue-aplicaciones.spec.js` con el motor Docker común, reabrir/reconectar/reiniciar worker, contenido malicioso literal, volumen de salida, scroll/exportación y pérdida de autorización; indicar qué casos usan backend simulado.
- [ ] T087 [US4] Instrumentar medición de captura→pantalla y apertura en `infra/laboratorio/011/medir_consola.py` y `frontend/tests/e2e/consola-rendimiento.spec.js`; ejecutar con dos trabajos reales y registro lleno y guardar p95 <=5 s/apertura <=3 s, más revisión de spool/journal/DB/export sin secretos, en `docs/evidencia/011/us4-consola.md`.

**Checkpoint**: lectura recuperable y autorizada, proceso independiente de la UI, estado final conservado aunque el texto expire. La consola no habilita respuestas a instaladores ni comandos en el nodo.

## Phase 7: US5 — Recuperar fallos y conservar el servicio (P1)

**Objetivo**: reconciliar antes de repetir, operar sin reinstalar y eliminar únicamente lo propio, liberando capacidad/red después de ausencia confirmada.

**Prueba independiente**: para las dos entradas OCI perder respuesta tras crear/iniciar, cortar SSH/worker, recuperar y verificar una sola identidad/ejecución/reserva; después fallar y reintentar explícitamente, operar con datos persistentes y eliminar con identidad comprobada. Fallo de limpieza mantiene contabilidad y estado visible.

### Pruebas primero

- [ ] T088 [P] [US5] Crear `backend/tests/test_recuperacion_aplicaciones_011.py`: create/start con respuesta perdida, takeover, boot distinto, trabajo desaparecido, timeout, fuente inaccesible y fallo del probe; incertidumbre nunca permite recreación ciega o entrega.
- [ ] T089 [P] [US5] Crear `backend/tests/test_ciclo_vida_aplicaciones_011.py` para stop/start/restart sin pull/reinstalar/regenerar secretos, datos persistentes, identidad ajena, baja fallida/almacenamiento presente, renovación/vencimiento y oferta retirada.
- [ ] T090 [P] [US5] Crear `backend/tests/postgres/test_reintentos_011.py` para doble retry y cleanup/admisión concurrentes, historial terminal intacto, cuota compartida y operación abierta única; recrear el mismo pedido conserva valores/referencias de secretos de aplicación pero renueva UUID/nonce/TLS, una renovación conserva secretos del alta original y un nuevo pedido de alta no hereda secretos al reutilizar slot confirmado ausente.
- [ ] T091 [P] [US5] Crear `frontend/tests/recuperacion-aplicaciones.test.jsx` para fallo/reintento/incertidumbre/limpieza pendiente y confirmación destructiva clara, sin botón de reintento en un resultado desconocido ni reinicio de la instalación al consultar.

### Implementación

- [ ] T092 [US5] Extender `backend/app/services/reconciliacion_service.py` y `backend/app/services/orquestacion_service.py`: inspección de marcador/configuración/job/boot, mismo execution_id tras takeover y resultado incierto hasta prueba; observación sin repetir instalador y estados por `pedido_service.transicionar` con actor correcto.
- [ ] T093 [US5] Implementar POST `/operaciones/{id}/reintentar` en `backend/app/routers/operaciones.py` y `backend/app/services/operacion_service.py`: admin/CSRF/body vacío/idempotencia, fallo confirmado crea operación reparar e intento siguiente con raíz común; incertidumbre/ejecución/vigencia inválida devuelve 409, sin reabrir terminales ni sustituir configuración.
- [ ] T094 [US5] Integrar iniciar/detener/reiniciar en `backend/app/services/orquestacion_service.py`, `infra/applications/docker/lifecycle.py`: verificar identidad/snapshot/container/volúmenes y conservar credenciales/datos; no convertir una discrepancia en reinstalación automática.
- [ ] T095 [US5] Completar limpieza en `backend/app/services/orquestacion_service.py`, `backend/app/services/reserva_red_service.py` y `backend/app/services/capacidad_service.py`: destruir sólo recursos propios y confirmar ausencia CT/almacenamiento antes de liberar red/ledger, manteniendo limpieza pendiente ante fallo. Recrear el mismo pedido exige nueva identidad/nonce/claves TLS y capacidad revalidada, conserva secretos de aplicación y referencias aprobadas; sólo otro pedido de alta genera secretos de aplicación nuevos.
- [ ] T096 [US5] Integrar el motor Docker común con retirada/renovación/pausas/avisos en `backend/app/services/configuracion_despliegue_service.py`, `backend/app/services/vigencia_service.py`, `backend/app/services/vencimiento_service.py` e `backend/app/services/inactividad_service.py`: revisión original conservada, retirada sólo bloquea pedidos nuevos y vigencia no agrega borrado silencioso ni ensayo de 24 horas.
- [ ] T097 [US5] Integrar acciones de recuperación y baja en `frontend/src/pages/Pedidos.jsx` y `frontend/src/pages/Servicios.jsx`: resumen breve, consola disponible admin, reintento sólo admisible, limpieza pendiente visible y confirmación explícita de pérdida de datos antes de eliminar.
- [ ] T098 [US5] Ejecutar recuperación/lifecycle/limpieza reales para el motor Docker común con los scripts controlados de `infra/laboratorio/011/probar_recuperacion.py`; registrar identidades/compromisos observados, cortes, datos conservados, recursos ajenos intactos y ausencia confirmada o limpieza pendiente en `docs/evidencia/011/us5-recuperacion.md`.

**Checkpoint**: fallo entendible y recuperable sin duplicar ni ocultar capacidad. El historial académico y los intentos anteriores permanecen aunque la oferta se retire o el registro operativo se purgue.

## Phase 8: Cierre y validación transversal

**Objetivo**: comprobar la feature completa sin atribuir al entorno universitario los resultados del laboratorio.

- [ ] T099 Crear y ejecutar regresión en `backend/tests/test_regresion_servicios_011.py` y `frontend/tests/e2e/regresion-servicios-011.spec.js`: usuarios/cátedras/pedidos/historial, IaaS Ubuntu/Debian, Draw.io/acceso con NAP, manifiestos/runner legacy, renovaciones y consola IaaS; registrar conservación real sin recrear instancias en `docs/evidencia/011/regresion.md`.
- [ ] T100 Ejecutar revisión de aislamiento/secretos extremo a extremo y pruebas adversarias en `backend/tests/test_aislamiento_aplicaciones_011.py` e `infra/applications/tests/test_secret_retention.py`: SSRF/DNS/realm, cookies/headers, imagen/metadata maliciosa, red nodo/portal/otra cátedra, revocación y secretos en spool/journal/DB/archivos operativos; conservar reporte seguro en `docs/evidencia/011/seguridad.md`.
- [ ] T101 Revisar la preparación ya ejecutada y documentar operación/rollback en `docs/despliegue-aplicaciones.md` e `infra/laboratorio/011/preparar_entorno.py`: inventario/versiones instaladas, preflight repetible y separación de laboratorio/universidad. El bootstrap ocurre en T004 y la instalación definitiva en T028/T050; esta tarea de cierre no es prerrequisito pendiente de esos ensayos ni agrega un gestor al portal.
- [ ] T102 Ejecutar las suites seleccionadas de `specs/011-desplegar-servicios-universitarios/quickstart.md`, `infra/applications/tests/`, regresiones afectadas, PostgreSQL aislado, Vitest, build y Playwright; registrar comandos/resultados/fallos pendientes en `docs/evidencia/011/pruebas-automatizadas.md` y no ampliar testing sin cambio/fallo que lo justifique.
- [ ] T103 Ejecutar aceptación integrada con whoami descubierto en Docker Hub y campus-demo propia, dos cátedras aisladas con el mismo motor y un admin del proyecto según `specs/011-desplegar-servicios-universitarios/quickstart.md`; consolidar SC-001–SC-009 con medidas/enlaces y resultados simulados/locales/pendientes institucionales en `docs/evidencia/011/aceptacion.md`, de forma secuencial si falta capacidad.
- [ ] T104 Actualizar instrucciones de uso cotidiano existentes en `docs/manual-administrador.md`, `docs/manual-docente.md`, `docs/laboratorio-biblioteca.md` y `AGENTS.md`: dos caminos simples, agregar no instala, pedidos/fechas/progreso/acceso y límites reales; conservar detalles técnicos sólo en la guía de infraestructura y no añadir specs por rutina.
- [ ] T105 Revisar trazabilidad FR/SC y checklist de cierre en `specs/011-desplegar-servicios-universitarios/tasks.md` y `docs/evidencia/011/aceptacion.md`: marcar sólo tareas verificadas, dejar bloqueos reales con motivo y siguiente acción, y confirmar que ningún perfil o entorno se anuncia certificado sin su evidencia.

## Dependencias, entrega y trazabilidad vigentes

- Setup activo T001–T005/T007 → base T008–T036 → motor US1 T037–T050.
- Biblioteca US2: T051/T054 → T062 → T063 → T064; reutiliza T041–T043 y runtime T050.
- US3 T065–T076, US4 T077–T087 y US5 T088–T098 reutilizan la misma ejecución.
  Sus pruebas con fixtures pueden avanzar tras la base; aceptación real requiere T050.
- Cierre T099–T105: dos imágenes, dos entradas de catálogo, un solo motor.
- T006 y T052/T053/T055–T061 están retiradas. No mantener dependencias hacia ellas.
  T006 fue un spike histórico aprobado; las otras nueve no se hicieron ni se marcan hechas.

Prioridad inmediata: cerrar integración parcial y gate Docker definitivo; luego conectar
la biblioteca Hub sin rehacer el motor. Pedidos/agenda, consola y recuperación conservan
sus garantías. Pruebas afectadas una vez por bloque; regresión completa sólo en un hito.
No repetir una instalación por seleccionar la misma imagen desde otra entrada de UI.

| Requisitos | Tareas principales | Aceptación |
|---|---|---|
| FR-001–005 | T030, T037–T050, T063 | T050/T064/T099 |
| FR-006–009 | T014, T041–T043, T051/T054/T062–T064 | T064/T102 |
| FR-010–012 | T030, T065–T074 | T076/T102 |
| FR-013–017 | T022–T036, T045–T047, T075 | T050/T076/T100 |
| FR-018–024 | T010, T018, T026–T028, T031, T077–T087 | T087/T100 |
| FR-025–028 | T088–T098, T072–T073 | T098/T099 |
| FR-029–030 | T003–T005/T007, T011/T021, T036/T044, T099–T105 | T103–T105 |
| SC-001–003/008 | T050/T064/T076 | T103: dos imágenes, dos cátedras, dos entradas <=3 min; pedido <=2 min |
| SC-004 | T027/T033/T081–T082/T087 | T087/T103: dos trabajos, p95 <=5 s, apertura <=3 s |
| SC-005–007 | T009–T010/T026–T028/T088–T100 | Recuperación, secreto protegido y limpieza confirmada |
| SC-009 | T011/T021/T036/T099/T101–T105 | Legado intacto, evidencia diferenciada por entorno |

## Criterio de finalización y recuento

**43/95 tareas activas verificadas; 52 pendientes.** Los IDs originales se conservan:
10 tareas retiradas, de las cuales T006 ya estaba completada históricamente. Este
recorte no representa nuevas implementaciones. Los recuentos 38/105 y anteriores
que siguen abajo son snapshots históricos previos a la decisión del 27/10.

Marcar una tarea activa sólo después de implementar/verificar su resultado. No
acreditar instalación por documentación o fixtures ni quitar seguridad/recuperación
para acelerar. Estado y tareas retiradas: [cambio de alcance](cambio-alcance-oci.md).

## Avance de implementación — 2026-10-27 (US2 Docker Hub biblioteca)

T008 y US2 (T051, T054, T062, T063, T064) completadas. Se reemplazó el proveedor de
biblioteca por descubrimiento en Docker Hub en backend (`biblioteca_service.py`),
con paginación por cursor hash, manejo de rate limit (429) y timeout/errores (502),
categorías no bloqueantes y rechazo explícito de nuevos `community_scripts` preservando
la lectura histórica de incorporaciones legacy. En frontend (`BibliotecaAplicaciones.jsx`,
`AgregarServicioModal.jsx`, `AplicacionPropiaForm.jsx`) se integraron las dos entradas
«Docker Hub» e «Imagen propia», selección que precarga el formulario común de alta OCI
sin pasos de preparación/publicación manual, y fallback a referencia manual ante fallos.
7 pruebas backend aprobadas (6,4 s) y 3 pruebas Vitest aprobadas (4,1 s). Ver `docs/evidencia/011/us2-biblioteca.md`.
Estado actual: **43/95 tareas activas verificadas (52 pendientes)**.

## Historial previo al recorte — no usar como alcance vigente

Los checkpoints siguientes conservan resultados y decisiones de sus fechas; las
obligaciones Community y cuatro aplicaciones quedaron retiradas el 27/10.

## Avance de implementación — 2026-10-26

T001–T007 completadas. Bootstrap TLS verificado y factibilidad real local aprobada para
Docker/Ubuntu 24.04 y Core/MariaDB+Caddy sobre Debian 13. Los CT, discos y reglas temporales
quedaron retirados; Draw.io se conservó. Los perfiles definitivos permanecen pendientes.

Selección de laboratorio: 98 pruebas locales aprobadas; incluyen Core real aislado, sin red,
política Bash y regresiones de fuentes/ownership. No se confunden con los ensayos de Proxmox.
Ver `docs/evidencia/011/compuertas.md`, `factibilidad-docker.md` y `factibilidad-community.md`.

Base común parcial: T011, T013–T022 y T026 completadas. Se implementaron contratos/perfiles,
modelos y migración aditiva, secretos por pedido y biblioteca de depuración incremental.
La migración local se aplicó con respaldo privado verificado; el portal responde 200.
Ver `docs/evidencia/011/base-comun.md` para alcance y límites.

T009, T010, T024, T025, T027–T029 y T031 completadas: supervisor/worker durables,
paquete y credenciales efímeras, spool/colector, cliente SSH e ingesta/retención del portal.
El paquete se instaló en la VM con respaldo; autocomprobación real de systemd/credenciales,
spool/ACK y journal aprobada, sin CT nuevos ni perfiles habilitados. Consulta real por cuenta
limitada aprobada; Draw.io CT 100 sigue corriendo y no quedan unidades temporales.

T008 sigue parcial: faltan pruebas del gateway genérico. T012 y T033 se cerraron en
el checkpoint de creación/worker, con las pruebas acotadas documentadas al final.
T081 unirá la ingesta a la UI. T078 parcial: tres pruebas PostgreSQL cubren
concurrencia, cuota entre intentos y claves locales por productor; falta exportación concurrente.
T023 parcial: asignador transaccional de slots y liberación con ausencia probados; falta unir
la identidad/nonce y TLS por instancia al camino definitivo. Red nueva vacía por defecto.
Selecciones finales: 55 backend 011; 79 infra/runner aprobadas y 5 omitidas; 22 red nueva/legacy;
PostgreSQL completo detectó una expectativa antigua de revisión (119 aprobadas/1 fallo),
corregida y verificada con 10 pruebas afectadas y del asignador. Backend completo: 860 aprobadas
antes de la prueba adicional de rotación y de las pruebas nuevas de red. Sin regresiones abiertas.
Los módulos nuevos todavía requieren integración con el ejecutor y sus aceptaciones finales.
Las cinco historias y sus aceptaciones siguen pendientes. Paquetes, recibos y credenciales
se conservan en nap011 fuera de Git. No se certificó el clúster universitario ni se habilitaron
ofertas nuevas por estos prototipos.

Último checkpoint: **27/105 tareas verificadas**. Regresión posterior: **903 pruebas
ordinarias de backend aprobadas** (124 PostgreSQL excluidas), tres PostgreSQL nuevas
aprobadas y health local 200. No hay pruebas manuales pendientes de Mauro en este
punto; continúan pendientes la integración de admisión/orquestación y los paquetes
definitivos por origen antes de las aceptaciones completas.

Checkpoint de admisión: **T030 completada; 28/105 tareas verificadas**. Aprobación
declarativa con snapshots/referencias privadas, retiro de oferta y bloqueo de perfil;
13 pruebas afectadas y una carrera PostgreSQL aprobadas (~13 s entre ambas selecciones).
No se repitió la regresión general ni el laboratorio. Criterio de pruebas proporcionales
registrado en AGENTS.md; se conserva la cobertura existente. Siguen pendientes identidad/
TLS de T023 e integración de creación/estrategias antes de ofrecer despliegues completos.

Checkpoint de creación/worker: **30/105 tareas verificadas**. T012/T033 completadas
con admisión concurrente, intento estable al recuperar respuestas perdidas, límite de dos
instalaciones por nodo, ingesta independiente de 1 s y purga. T032 parcial: creación
detenida y despacho/consulta ya integrados; firewall externo efectivo, TLS y paquetes
definitivos siguen pendientes de sus compuertas reales. T023 añade UUID/nonce nuevos
al reclamar la red; conserva pendiente generación/distribución de claves por instancia.
Validación afectada: 10 pruebas + una carrera PostgreSQL + un fallo de creación con
liberación tras ausencia; sin regresión general ni nuevas pruebas físicas simuladas.

Avance 27/10 — T032 conserva estado parcial. Política común `job/network.py`
y acción interna `ApplicationNodeExecutor.install_isolation`: tabla nft exclusiva
por identidad, CT propio/detenido, una sola NIC, MAC/IP/puente exactos y sin
flush/adopción de reglas. El paquete distribuye el módulo. Pruebas afectadas:
38 aprobadas; ampliación de la prueba real en namespace local con tráfico veth,
18 casos de política aprobados. Faltan cargador institucional, recuperación durable,
integración previa al arranque y gate Proxmox final; no habilita perfiles ni cierra
T023/T032/T034. Evidencia y límites en `docs/evidencia/011/base-comun.md`.

Avance siguiente 27/10 — aislamiento ya conectado al entry point del worker antes
de la estrategia, con registro institucional privado de redes y correspondencia
IP/MAC del slot. TLS por identidad en `job/tls.py`, CA local privada, persistencia
atómica/replay y redacción de claves de instancia. Validación afectada: 45 aprobadas,
una integración omitida; selección posterior TLS/adaptador 12 aprobadas. T023/T032/T034
siguen parciales hasta configurar el nodo y completar borde/probes/gates reales.

Checkpoint de acceso web: **31/105 tareas verificadas**, T035 completada. Gateway
genérico separado de Draw.io, cookies nativas aisladas, streaming acotado, WS declarado
con revocación cada 5 s, destino TLS/IP fijado y sin redirects WS. T034 parcial:
entrega web automática conectada al worker después de cursor final+ACK, observación
PVE y probe HTTPS; transacción única de entrega/aviso. TCP autenticado sigue cerrado
hasta MariaDB. Evidencia y selecciones afectadas en `docs/evidencia/011/base-comun.md`.

Checkpoint de alta propia: **38/105 tareas verificadas**. T038/T040–T043/T048–T049
completadas: resolver OCI con DNS/IP/TLS y fuentes cerradas, alta/revisión atómicas
e idempotentes sin reserva/invitado, UI breve en el mismo modal, errores/progreso y
edición de metadata compatible. Consulta real Docker Hub verificada sin ejecución;
una carrera PostgreSQL y pruebas afectadas API/UI aprobadas, con inspección visual
móvil/escritorio. No se habilitan perfiles por fixtures. T037 conserva pendientes
las pruebas ligadas al runtime definitivo, y T039/T044–T047/T050 siguen pendientes.
Ver `docs/evidencia/011/us1-imagenes.md`.

Checkpoint de pausa solicitado por Mauro, 27/10: runtime Docker y recibos durables
implementados parcialmente; el ensayo Proxmox final se bloqueó antes del arranque
por `net0.type=veth`. Corrección local con pruebas aprobadas, aún no distribuida ni
validada en otro ensayo real. LXC/discos/pool temporales eliminados y Draw.io
preservado. No se habilitaron perfiles ni se marcaron tareas de aceptación como
completas: se mantiene **38/105**. Detalle y siguiente paso seguro en
`docs/evidencia/011/us1-imagenes.md`.
