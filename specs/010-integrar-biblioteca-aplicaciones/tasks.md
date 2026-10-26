# Tasks: Biblioteca de aplicaciones reutilizables

**Input**: `specs/010-integrar-biblioteca-aplicaciones/` — [spec](spec.md), [plan](plan.md), [investigación](research.md), [modelo](data-model.md), [API](contracts/biblioteca-api.md), [runner](contracts/preparacion-runner.md), [UI/pedidos](contracts/catalogo-pedidos-ui.md) y [validación](quickstart.md).

**Branch**: `010-integrar-biblioteca-aplicaciones` · **Fecha**: 2026-10-25.

**Organización**: las tres historias tienen prioridad P1. US1 entrega el primer incremento; US2 y US3 completan el piloto utilizable. No implementar nuevos frameworks, cambiar rama ni sobrescribir trabajo preexistente. Paths relativos a la raíz del repositorio; archivos nuevos son salidas propuestas de implementación.

**Pruebas**: se incluyen las aceptaciones de la spec y las compuertas obligatorias de la constitución 4.0.0 para orquestación/estados/capacidad: fallo de infraestructura simulado y concurrencia real PostgreSQL. Ninguna prueba requiere un Proxmox real salvo las tareas explícitas de staging. No se ha ejecutado implementación ni aceptación al generar esta lista.

**Formato**: `- [ ] Tnnn [P?] [USn?] Acción con ruta`. `[P]` permite trabajo simultáneo dentro del grupo indicado, después de sus prerrequisitos; no habilita saltar dependencias ni editar el mismo archivo a la vez. Setup/fundación/cierre no llevan etiqueta de historia.

## Phase 1: Setup — contexto y dobles compartidos

Preparar la ejecución sobre el árbol existente sin reinicializar el proyecto ni sobrescribir cambios de 009. No crear instalaciones reales durante setup.

- [X] T001 Registrar rama, revisión, head Alembic detectado, cambios preexistentes y comandos de suites en `docs/evidencia/010/base-implementacion.md`; distinguir contexto observado de pruebas aún no ejecutadas.
- [X] T002 Crear dobles deterministas de fuente y builder en `backend/tests/fakes_biblioteca.py` y `backend/tests/fakes_builder.py`, reutilizando `backend/tests/fakes.py` y `backend/tests/fakes_runner.py`; soportar pérdida de confirmación, trabajo incierto, inspección y limpieza fallida, bloqueando efectos externos no previstos.

## Phase 2: Foundational — contratos y configuración comunes

Bloquea el inicio de historias. Reutilizar autenticación, sesiones, Idempotency-Key, keyring y errores institucionales; no desarrollar un segundo framework.

- [X] T003 Agregar configuración validada de fuente/hosts permitidos, límites/cache, host builder, perfiles de ensayo, TTL/aviso y presupuestos a `backend/app/config.py` e `infra/production/settings.example.json`; rechazar secretos en ejemplos, destinos arbitrarios y perfiles incompletos antes de crear recursos. Mapear hosts al scope físico canónico compartido y validar presupuesto/configuración por scope.
- [X] T004 Definir contratos cerrados compartidos de revisión esperada, paginación, estados/errores seguros y respuestas 202 en `backend/app/schemas/biblioteca_common.py`, reutilizando `backend/app/schemas/common.py` y formato de `backend/app/utils/errors.py`; documentar claves estables de auditoría sin comandos crudos ni secretos.

## Phase 3: User Story 1 — Buscar e incorporar una aplicación (P1, MVP)

**Objetivo:** buscar Draw.io y otras candidatas desde Definiciones e incorporar un borrador editable con origen y faltantes, sin instalar ni publicar.

**Prueba independiente:** con fuente simulada encontrar Draw.io mediante los tres términos y categoría, incorporar dos veces con claves distintas, editar y reimportar sin pérdida; ninguna llamada PVE/builder, reserva o publicación. Probar vacío/fallo/cache y recorrido de teclado. La medición humana con proveedor disponible acredita SC-001.

**Pruebas de aceptación:** contratos de la spec y plan; no se impone una metodología TDD adicional. Escribir los casos antes de cerrar implementación y ejecutarlos después de integrar.

- [X] T005 [P] [US1] Definir pruebas de autenticación/rol, JSON cerrado, códigos, CAS, reimportación y ausencia de I/O de instalación para búsqueda/incorporaciones en `backend/tests/test_biblioteca_api_010.py`, según `contracts/biblioteca-api.md`. Incluir categoría sin q, filtros AND y rechazo de ambos filtros vacíos.
- [X] T006 [P] [US1] Cubrir alias/categorías, datos desconocidos, 404/429/timeout, cache desactualizada, límite de bytes/entradas, árbol truncado y rechazo de rutas/redirecciones arbitrarias en `backend/tests/test_biblioteca_fuente_010.py`; guardar respuestas públicas con revisión en `backend/tests/fixtures/biblioteca/`. Verificar consulta sólo por categoría además de alias.
- [X] T007 [P] [US1] Probar con sesiones PostgreSQL independientes dos importaciones simultáneas, claves distintas y edición concurrente en `backend/tests/postgres/test_biblioteca_incorporacion_010.py`; obtener un único borrador y conflicto CAS sin sobrescritura.
- [X] T008 [P] [US1] Cubrir búsqueda, ficha, compatibilidad no comprobada, faltantes, errores/cache, doble envío y conservación/foco/teclado en `frontend/tests/biblioteca.test.jsx`, usando respuestas del contrato y sin API externa.
- [X] T009 [US1] Crear `IncorporacionAplicacion` en `backend/app/models/incorporacion_aplicacion.py` y registrarla en `backend/app/models/__init__.py`; separar snapshot fuente y ediciones, versión nullable y unicidad por aplicación/versión conocida o revisión si se desconoce. La incorporación no mantiene una FK singular a definición; las revisiones técnicas se relacionan desde DefinicionServicio.
- [X] T010 [US1] Crear `backend/alembic/versions/010_01_biblioteca.py` sobre el head real detectado y ampliar `infra/production/permisos.sql` con permisos DML necesarios; construir tabla/constraints/índices de incorporación sin modificar datos históricos ni conceder DDL al runtime.
- [X] T011 [US1] Implementar schemas de búsqueda, ficha, filtros/cursor y edición administrativa en `backend/app/schemas/biblioteca.py`; no aceptar comandos, URLs de ejecución, versiones inventadas ni campos extra desde el cliente.
- [X] T012 [US1] Implementar lectura por revisión del árbol oficial y construcción de índice en `backend/app/services/community_scripts_client.py`; aplicar deadlines 10 s/conexión 3 s, límites 10.000/8 MiB, cache 15 min, refrescos coalescidos y errores explícitos, sin analizar/ejecutar shell.
- [X] T013 [US1] Implementar búsqueda normalizada y alta/listado/detalle/edición de incorporaciones en `backend/app/services/biblioteca_service.py`; declarar alias Draw.io/diagramas como NAP, validar fuente en servidor, deduplicar incluso con otra clave y no sobrescribir cambios ni crear definición técnica en la incorporación inicial.
- [X] T014 [US1] Exponer GET `/biblioteca/aplicaciones`, POST/GET `/biblioteca/incorporaciones` y GET/PATCH de detalle en `backend/app/routers/biblioteca.py`, registrar router en `backend/app/main.py` y aplicar acceso administrador, CSRF vigente, no-store, Idempotency-Key y CAS.
- [X] T015 [US1] Agregar funciones de búsqueda/incorporación/edición a `frontend/src/services/api.js`, preservando la misma Idempotency-Key para reintentar una intención sin confirmación y conservando formato de errores institucionales.
- [X] T016 [US1] Crear búsqueda/ficha editable en `frontend/src/components/BibliotecaAplicaciones.jsx` e integrarla en `frontend/src/pages/Definiciones.jsx`; mostrar comando sólo informativo, origen externo/NAP, faltantes y límites de compatibilidad, sin botones activos de preparación para productos sin adaptador.
- [X] T017 [US1] Agregar recorrido independiente de búsqueda/incorporación con mocks y teclado en `frontend/tests/e2e/biblioteca-incorporacion.spec.js`; ejecutar pruebas US1 y registrar resultados reales y medición SC-001 cuando haya proveedor disponible en `docs/evidencia/010/us1-incorporacion.md`.

## Phase 4: User Story 2 — Preparar y publicar Draw.io (P1)

**Objetivo:** preparar desde NAP una imagen reutilizable, comprobar dos LXC de ensayo, validar/publicar una oferta Software y limpiar recursos efímeros conservando artefactos e historia.

**Prueba independiente:** partir de una incorporación Draw.io, fijar/confirmar entradas, construir, desplegar dos ensayos, registrar ciclo editable/red/aislamiento y publicar perfil; bloquear incompletos/fallidos. Simular incertidumbre, expiración y limpieza fallida sin duplicados ni capacidad liberada prematuramente. Ensayo real requerido para declarar oferta comprobada.

**Orden interno:** pruebas → modelos/migración → contratos/capacidad → receta/transportes → estados/worker → endpoints/UI → validación. Las pruebas [P] se escriben con la fase 2 completa, en archivos distintos.

- [X] T018 [P] [US2] Cubrir contratos de crear/consultar ensayo, confirmar entradas, comprobar, reintentar, descartar, revelar acceso y publicar-oferta en `backend/tests/test_ensayos_api_010.py`; verificar roles, CAS, 202 durable y bypass de publicación rechazado. Probar múltiples revisiones desde una incorporación sin cambio de comando, antecedente y versión mayor; misma revisión devuelve 200 sin sobrescribir.
- [X] T019 [P] [US2] Definir pruebas de fallos builder/PVE, respuesta perdida tras dispatch, reconciliación, UPID, lease vencido y dos workers en `backend/tests/test_ensayo_worker_010.py`, usando dobles que detecten recursos duplicados. Entregar órdenes builder fuera de orden, incluido build después de cancel/cleanup, y reiniciar ejecutor para verificar cierre durable.
- [X] T020 [P] [US2] Probar ensayo vs aprobación y dos ensayos compitiendo por última capacidad, reservas de dos recursos atómicas, ausencia de doble cómputo y presupuesto builder concurrente en `backend/tests/postgres/test_ensayo_capacidad_010.py`. Incluir dos primeras reservas con tabla PresupuestoBuilder vacía y hosts distintos que comparten scope.
- [X] T021 [P] [US2] Cubrir vencimiento durante resolver/build/crear/bootstrap, aviso previo, publicación vs vencimiento, descarte, eliminación parcial y limpieza fallida en `backend/tests/test_ensayo_limpieza_010.py`; exigir fencing, capacidad retenida y artefactos/evidencia preservados. No confirmar limpieza ni liberar espacio hasta cierre remoto durable, terminación de procesos y conciliación de dispatch/tareas PVE inciertos.
- [X] T022 [P] [US2] Probar manifiesto Draw.io 1.1 y evidencia válidos/inválidos, versiones exactas, publicación incompleta y regresión de manifiestos 1.0 en `backend/tests/test_drawio_contratos_010.py` y fixtures en `backend/tests/fixtures/drawio/`. Exigir check deployment_without_provider ligado a los dos ensayos como gate previo a validar/publicar.
- [X] T023 [P] [US2] Definir pruebas de protocolo builder cerrado, límites/timeout, idempotencia de job, directorio privado, saneamiento y build desde inputs fijados en `infra/builder/tests/test_executor.py`, `infra/services/tests/test_drawio.py` e `infra/runner/tests/test_drawio.py`; incluir probes/perímetro, bootstrap idempotente y rechazo de identidad ajena, sin red ni procesos reales por defecto. Agregar casos de generaciones obsoletas, cancel previo a build aún no recibido, reinicio y cierre remoto conservado tras cleanup.
- [X] T024 [P] [US2] Cubrir confirmación de entradas, estado recuperado tras recargar, polling/visibilidad, vencimiento, errores y publicación con limpieza pendiente en `frontend/tests/ensayos.test.jsx`.
- [X] T025 [US2] Crear modelos `EnsayoPreparacion`, `RecursoEnsayo`, `OperacionEnsayo` y `EventoEnsayo` en `backend/app/models/ensayo_preparacion.py`, `backend/app/models/recurso_ensayo.py`, `backend/app/models/operacion_ensayo.py` y `backend/app/models/evento_ensayo.py`; incluir estados/limpieza separados, actores, CAS/lease e índices de operación/ensayo abiertos. Persistir execution_generation monotónica por ensayo y confirmación de cierre remoto, separadas del lease por operación.
- [X] T026 [US2] Crear artefacto/réplicas, reserva de espacio builder y bitácora de publicación en `backend/app/models/artefacto_preparado.py`, `backend/app/models/reserva_espacio_builder.py` y `backend/app/models/publicacion_oferta.py`; registrar FKs/relaciones en `backend/app/models/__init__.py` y conservar retención independiente de los ensayos. Crear además PresupuestoBuilder en `backend/app/models/presupuesto_builder.py`, con PK scope_id y límite/revisión institucionales; ReservaEspacioBuilder referencia ese scope.
- [X] T027 [US2] Extender `backend/app/models/compromiso_capacidad.py` y `backend/app/models/identidad_infraestructura.py` con propietario de recurso de ensayo exclusivo del académico y unicidad global de VMID; añadir revisión CAS de definición en `backend/app/models/definicion_servicio.py` sin relajar inmutabilidad validada. Agregar incorporacion_id y base_definicion_id nullable a DefinicionServicio para origen 1:N y antecedente, manteniendo definición/código/version únicos.
- [X] T028 [US2] Crear `backend/alembic/versions/010_02_ensayos_artefactos.py` con tablas/FKs/índices nuevos, ledger académico-o-ensayo, revisión de definición y dependencias circulares mediante constraints posteriores cuando corresponda; actualizar `infra/production/permisos.sql` sin inventar snapshots históricos. Incluir tabla PresupuestoBuilder, FK de reserva a scope y FKs de origen/antecedente desde definición; no crear filas con destinos ficticios.
- [X] T029 [US2] Agregar esquema cerrado `backend/app/schemas/service-definition-1.1.schema.json` y selección por versión en `backend/app/schemas/definicion.py`; mantener 1.0, admitir sólo Draw.io/SaaS y campos de runtime/receta/probes/secretos definidos en el contrato, sin comandos ni URLs ejecutables.
- [X] T030 [US2] Extender `backend/app/schemas/evidence.schema.json`, `backend/app/schemas/evidencia.py` e `infra/services/build_image.py` para checks Draw.io de ciclo editable, perímetro, aislamiento y ausencia de dependencia del proveedor; preservar validación de evidencia 009 y exigir dos identidades coherentes con imagen/bundle. Emitir y exigir deployment_without_provider con identidades/digests de los dos LXC ensayados sin proveedor antes de publicar.
- [X] T031 [US2] Implementar contratos de ensayo, entradas fijadas y publicar-oferta en `backend/app/schemas/ensayo.py` y contrato independiente `nap-build-runner/1` en `backend/app/schemas/build_runner.py`; acotar tamaños/acciones y rechazar shell, rutas/URLs arbitrarias y secretos fuera del canal permitido. Incluir generation por ensayo, acción cancel, variantes de campos por acción, estados cancelled/not_found/unknown y max_generation/closed en respuesta de status.
- [X] T032 [US2] Extender `backend/app/services/capacidad_service.py` para ledger de ensayo en panorama/fingerprint y reserva indivisible de ambos LXC bajo lock 4001; mantener unión por identidad/scope, impedir sobreasignación de ensayo y filtrar expirador académico por pedido no nulo.
- [X] T033 [US2] Implementar admisión y conciliación de espacio por host/scope en `backend/app/services/builder_capacity_service.py`; inicializar PresupuestoBuilder mediante INSERT ON CONFLICT DO NOTHING y bloquear su fila por scope con SELECT FOR UPDATE en la misma transacción, con lock 4001 primero y scopes ordenados cuando se combina con PVE; persistir reserva antes del I/O, convertir bytes finales a ocupación retenida y no liberar temporales inciertos ni contar dos veces builder/registro compartidos.
- [X] T034 [US2] Ampliar primitivas de ownership/identidad en `backend/app/services/identidad_infra_service.py` y reserva de red en `backend/app/services/reserva_red_service.py` para pool institucional de ensayos y Draw.io; impedir pertenencia docente a ensayos y conservar UUID/MAC/nonce en reintentos.
- [X] T035 [US2] Agregar resolución cerrada de JRE 21/Tomcat 11/WAR Draw.io y paquete de fuentes en `infra/services/resolve_packages.py` e `infra/services/drawio/resolve.py`; producir versiones/digests/lock completos para revisión administrativa antes de construir, sin resolver `latest` durante build o bootstrap. Una revisión posterior puede resolver nuevos inputs desde la misma incorporación; nunca editar inputs de una revisión validada.
- [X] T036 [US2] Implementar `infra/services/drawio/build.sh` y extender `infra/services/build_image.py`, `infra/services/sanitize.py` e `infra/services/resolve.Dockerfile` para imagen Ubuntu 24.04 amd64 sin privilegios/nesting; verificar base, revisión comprometida, inventario/locks y hashes reales de imagen/bundle; excluir todo dato/identidad/credencial del ensayo.
- [X] T037 [US2] Implementar `infra/services/drawio/bootstrap.py` e integrar producto en `infra/services/common.py`: configurar nginx HTTPS/credencial de perímetro única, Tomcat sólo loopback, editor local y bootstrap/probes idempotentes, sin instalar/descargar paquetes al entregar una instancia.
- [X] T038 [US2] Crear ejecutor durable `infra/builder/executor.py` y entrada `infra/builder/nap-build-runner` para resolve/build/status/stage/cancel/cleanup; imponer allowlist de recetas/revisiones/destinos, trabajos privados, límites, consulta tras confirmación perdida y limpieza que nunca alcance artefactos finales. Persistir max_generation/closed fuera de temporales bajo lock de ensayo; rechazar órdenes antiguas o de ensayo cerrado, detener/recolectar procesos al cambiar generación/cancelar y exigir cancel antes de cleanup sin borrar su registro.
- [X] T039 [US2] Crear instalación y acceso acotado en `infra/builder/install.sh`, `infra/builder/sshd_config.example` e `infra/builder/sudoers.example`; fijar hostkeys/forced-command/cuenta dedicada y exponer sólo operaciones tipadas en host separado de PVE productivo.
- [X] T040 [US2] Implementar transporte/consulta de trabajos en `backend/app/services/build_runner_client.py`; reutilizar utilidades de límites del runner, validar respuesta/identidad/digests, retornar control sin esperar el build y conservar job_id ante timeout. Enviar generation y verificar respuesta; conciliar not_found frente a unknown sin recrear automáticamente, y no aceptar como cierre un resultado sin terminación confirmada.
- [X] T041 [US2] Implementar registro/distribución verificable en `backend/app/services/artefacto_service.py` y extender `infra/laboratorio/instalar_artefactos.py` y comprobación en `backend/app/services/catalogo_service.py`; stage temporal/cambio atómico, réplicas y revisión recargable coherente de registro API/worker/runner, sin edición manual por pedido.
- [X] T042 [US2] Ampliar registros cerrados Draw.io, access_password y resultados/probes en `backend/app/schemas/guest_runner.py`, `infra/runner/nap_guest_runner.py` e `infra/runner/node_executor.py`; verificar propiedad/bundle sin habilitar comandos libres ni invalidar productos anteriores.
- [X] T043 [US2] Ampliar `backend/app/services/preparacion_service.py` y `backend/app/services/probes_servicio.py` con generación cifrada de access_password antes del dispatch, usuario UUID y endpoint HTTPS del perfil; crear camino de validación exclusivo de artefacto de ensayo en `backend/app/services/ensayo_bootstrap_service.py`, manteniendo gate de publicación del bootstrap académico.
- [X] T044 [US2] Implementar máquina central/CAS y bitácora en `backend/app/services/ensayo_service.py`: iniciar con reservas y TTL, resolver/confirmar entradas, comprobar evidencia, reintentar tras conciliación y descartar; completar incorporación→definición Draw.io sin convertir otras fichas en productos soportados. Admitir varias revisiones desde una incorporación con antecedente del mismo código/producto, versión NAP semánticamente mayor e idempotencia por código/versión; aumentar execution_generation en toma de ejecución y cancelación, sin reabrir cierre terminal.
- [X] T045 [US2] Implementar pipeline de resolución/construcción/distribución y creación/bootstrap de dos LXC en `backend/app/services/ensayo_worker.py`, reutilizando primitivas PVE/ownership/UPID; persistir intención antes de I/O y aplicar lease/generación al confirmar cada efecto, sin crear pedidos académicos ficticios. Propagar execution_generation al builder y descartar resultados de generaciones antiguas; conciliar operaciones PVE en vuelo antes de declarar ausencia y conservar su capacidad si no puede acreditarse terminación.
- [X] T046 [US2] Implementar expiración/aviso, cancelación cercada y limpieza durable en `backend/app/services/ensayo_cleanup_service.py`, registrar jobs en `backend/app/worker.py` y avisos en `backend/app/services/notificacion_service.py`; conservar capacidad/presupuesto hasta ausencia/cleanup confirmados, artefactos e historia siempre retenidos. Persistir cierre local e incrementar generación, confirmar cancel remoto durable antes de cleanup builder y no liberar espacio mientras haya procesos o efectos de estado incierto.
- [X] T047 [US2] Implementar publicar-oferta en `backend/app/services/catalogo_service.py` y `backend/app/services/perfiles_service.py`: bloquear/revalidar definición/ensayo/perfil, publicar y crear/mover perfil estable con revisión/bitácora y cleanup en una transacción; comprobar vigencia/evidencia/réplicas y bloquear bypass por publicar previo, sin afectar productos 009. Exigir evidencia deployment_without_provider de ensayo antes de publicar, sin exigir un pedido de una oferta que todavía no está publicada.
- [X] T048 [US2] Exponer POST `/biblioteca/incorporaciones/{id}/definicion`, POST `/definiciones/{id}/ensayos` y `/publicar-oferta`, consulta/eventos/acciones de ensayo y revelado auditado de acceso en `backend/app/routers/biblioteca.py`, `backend/app/routers/definiciones.py` y `backend/app/routers/ensayos.py`; registrar en `backend/app/main.py` sin I/O PVE en routers. El endpoint de definición recibe base_definicion_id para nueva revisión y devuelve la lista de revisiones en el detalle de incorporación.
- [X] T049 [US2] Agregar creación de definición, ensayo/acciones, polling y publicación atómica a `frontend/src/services/api.js`; conservar claves/revisión de cada intención y separar revelado sensible de respuestas generales.
- [X] T050 [US2] Crear `frontend/src/components/EnsayoPreparacion.jsx` y `frontend/src/components/PublicarOfertaModal.jsx`; integrar en `frontend/src/pages/Definiciones.jsx` revisión de entradas, TTL/aviso, estado recuperable, comprobación y publicación con perfil, poll cada 5 s visible y conservación de formularios. Listar revisiones y ofrecer Nueva versión desde la misma incorporación, con antecedente y versión mayor, sin alterar la anterior.
- [X] T051 [US2] Integrar recorrido US2 con mocks en `frontend/tests/e2e/biblioteca-preparacion.spec.js`, registrar suite builder en `infra/pytest.ini` y `.github/workflows/009-validation.yml` y ejecutar pruebas US2 de backend/PostgreSQL/infra/frontend; guardar comandos y resultados en `docs/evidencia/010/us2-pruebas.md`.
- [ ] T052 [US2] Ejecutar ensayo real de dos LXC desde el paquete, saneamiento, ciclo crear/editar/exportar/reabrir `.drawio`, TLS/red, denegación cruzada, reinicio y limpieza por publicación/descarte/vencimiento según `specs/010-integrar-biblioteca-aplicaciones/quickstart.md`; registrar digests/versiones/resultados en `docs/evidencia/010/drawio-preparacion.md`, sin marcar aceptación si falta entorno o evidencia. Mantener el proveedor bloqueado durante creación/bootstrap de ambos ensayos desde artefacto retenido y registrar deployment_without_provider antes de validar/publicar; no esperar a un pedido académico para acreditar ese gate.

## Phase 5: User Story 3 — Seleccionar y reutilizar una oferta publicada (P1)

**Objetivo:** solicitar Draw.io desde ambos puntos de entrada, aprobar con versión vigente y desplegar instancias propias sin depender de Community Scripts, conservando aislamiento e historia.

**Prueba independiente:** con oferta preparada como fixture, dos cátedras solicitan y reciben instancias aisladas; cambio previo a aprobación usa versión vigente/notifica, cambio posterior conserva snapshot y publicación concurrente invalida evaluación. Prueba real con oferta aceptada de US2 acredita SC-003/004/006.

- [X] T053 [P] [US3] Cubrir selección original, versión vigente al aprobar, snapshot congelado posterior, retiro, renovación, «Otro» y notificación idempotente en `backend/tests/test_biblioteca_pedidos_010.py`, usando fixtures de oferta preparada y sin fuente externa.
- [X] T054 [P] [US3] Probar publicación entre evaluación y aprobación, dos aprobaciones y notificación transaccional con sesiones PostgreSQL independientes en `backend/tests/postgres/test_biblioteca_aprobacion_010.py`; exigir 409 para token anterior y reserva coherente de versión vigente.
- [X] T055 [P] [US3] Cubrir dos instancias y credenciales distintas, bootstrap repetido, fallo de infraestructura, gate externo de activación y despliegue sin consultas/descargas a Community Scripts en `backend/tests/test_drawio_entrega_010.py`; verificar consulta/operación cruzada denegada.
- [X] T056 [P] [US3] Cubrir oferta preseleccionada Catálogo→Nuevo pedido, ausencia de hardware, errores/retiro preservando campos y comparación solicitada/efectiva al aprobar en `frontend/tests/biblioteca-pedidos.test.jsx`.
- [X] T057 [US3] Añadir `seleccion_oferta_snapshot` a `backend/app/models/pedido.py` y `backend/alembic/versions/010_03_seleccion_oferta.py`; conservar nulos históricos sin reconstruirlos desde la versión vigente y ampliar permisos si corresponden.
- [X] T058 [US3] Extender creación/reenvío en `backend/app/services/solicitud_service.py` y serialización en `backend/app/schemas/pedido.py` para validar oferta/cátedra y guardar versión/revisión/nombre mostrados; conservar descripción de «Otro» y rechazar selección retirada sin perder datos del formulario.
- [X] T059 [US3] Extender `backend/app/services/perfiles_service.py`, `backend/app/schemas/template.py` y `backend/app/routers/templates.py` para servir oferta Software activa con versión/revisión/origen seguros; excluir retiradas/no comprobadas y conservar contratos/visibilidad de perfiles anteriores.
- [X] T060 [US3] Resolver puntero vigente para altas de biblioteca en `backend/app/services/evaluacion_service.py` y `backend/app/schemas/asignacion.py`; devolver comparación solicitada/efectiva, evaluar requisitos de esa versión e incluir revisión de perfil/definición/artefactos en token de 60 s, manteniendo snapshot de renovación.
- [X] T061 [US3] Revalidar token/puntero bajo locks de capacidad/filas al aprobar en `backend/app/services/admision_service.py`; ante cambio devolver 409 evaluacion_desactualizada, reevaluar administrativamente y congelar versión/recursos/destino vigentes sin confirmación docente ni cambios posteriores por publicar.
- [X] T062 [US3] Persistir comparación de versiones en historial/decision_snapshot mediante `backend/app/services/pedido_service.py` y `backend/app/services/historial_service.py`, y evento/outbox seguro en `backend/app/services/notificacion_service.py`; deduplicar aviso y mantener aprobación ante fallo SMTP.
- [X] T063 [US3] Integrar Draw.io con reserva SaaS de red/pool, bootstrap y verificación de acceso por servicio en `backend/app/services/orquestacion_service.py`, `backend/app/services/reserva_red_service.py` y `backend/app/services/verificacion_acceso_service.py`; crear sólo desde fecha inicial, usar artefacto retenido incluso retirado tras aprobación y nunca activar por un probe local aislado.
- [X] T064 [US3] Adaptar `frontend/src/pages/Catalogo.jsx`, `frontend/src/components/NuevoPedidoModal.jsx` y `frontend/src/components/ReenviarPedidoModal.jsx` para conservar perfil/versión mostrados y campos válidos, elegir Software sin hardware y mantener «Otro» en Plataforma/Software.
- [X] T065 [US3] Actualizar `frontend/src/components/AprobarPedidoModal.jsx`, `frontend/src/pages/Pedidos.jsx` y `frontend/src/services/api.js` con comparación solicitada/vigente y recuperación de 409 mediante nueva evaluación; mostrar versión autorizada e historia sin confirmación adicional docente.
- [X] T066 [US3] Agregar `frontend/tests/e2e/biblioteca-pedidos.spec.js` con ambas entradas, dos cátedras, versión anterior/nueva, retiro y errores; ejecutar pruebas US3 y registrar resultados en `docs/evidencia/010/us3-pruebas.md`.
- [ ] T067 [US3] Validar en staging dos entregas reales y un nuevo despliegue con Community Scripts bloqueado según `specs/010-integrar-biblioteca-aplicaciones/quickstart.md`; medir pedido <3 min, comprobar ciclo editable, aislamiento NAP/HTTPS y versión congelada, guardar tráfico seguro/digests/resultados en `docs/evidencia/010/drawio-entrega.md`. Este gate posterior acredita SC-006 con pedido real; no es prerrequisito para la primera publicación ya comprobada mediante ensayos.

## Phase 6: Polish — regresión, operación y cierre

Completar después de integrar las tres historias. No confundir pruebas con dobles con aceptación real; dejar tareas de staging pendientes si la infraestructura no permite acreditarlas.

- [X] T068 [P] Verificar cadena Alembic completa sobre esquema/datos 009 aislados en `backend/tests/postgres/test_migracion_biblioteca_010.py`, preservación de snapshots/evidencias/owners académicos y restauración con nuevas tablas en `backend/tests/postgres/test_restauracion_biblioteca_010.py`. Verificar también tabla de presupuesto por scope y relación 1:N incorporación→definiciones, preservando revisiones y origen de versiones anteriores.
- [X] T069 [P] Actualizar operación/configuración/revelado de acceso, builder/registro/retención, limpieza fallida y retirada de feature sin borrar historia en `docs/manual-administrador.md`, `docs/manual-docente.md`, `docs/conexion-infraestructura.md`, `docs/operacion-respaldos.md` e `infra/services/README.md`; explicar guardado local de diagramas y credencial de perímetro.
- [X] T070 Integrar logs/contadores de ensayo/build/cleanup con IDs/fase/duración y errores seguros en `backend/app/services/ensayo_worker.py`, `backend/app/services/ensayo_cleanup_service.py` e `infra/builder/executor.py`; comprobar que logs/resultados no filtran comandos crudos, secretos, Authorization ni claves TLS en `backend/tests/test_biblioteca_redaccion_010.py`.
- [X] T071 Ejecutar regresión de backend/PostgreSQL, builder/runner/services/laboratorio y frontend conforme a `specs/010-integrar-biblioteca-aplicaciones/quickstart.md`; actualizar CI `.github/workflows/009-validation.yml` para exigir tests nuevos recolectados, sin saltar suites ausentes, y registrar resultados en `docs/evidencia/010/regresion.md`.
- [ ] T072 Medir SC-001 <2 min, SC-004 <3 min, consultas/estado p95 ≤1 s con 10 sesiones/100 muestras y búsqueda con deadline 10 s; registrar muestras/contexto en `docs/evidencia/010/rendimiento.md` y ajustar consultas/cache si incumplen, sin sustituir tiempos humanos por latencias técnicas.
- [ ] T073 Consolidar trazabilidad FR-001–FR-018/SC-001–SC-006, compuertas reales pendientes o cumplidas y evidencia sin secretos en `docs/evidencia/010/cierre.md`; actualizar `specs/010-integrar-biblioteca-aplicaciones/quickstart.md` con comandos/rutas finales y marcar tareas sólo tras su validación.

## Dependencies & Execution Order

### Grafo de dependencias por historia

```text
Setup (T001, T002)
  → Fundación (T003, T004)
    → US1: búsqueda/incorporación (T005–T017)
      → US2: preparación/publicación (T018–T052)
        → US3: selección/entrega (T053–T067)
          → Cierre (T068–T073)
```

Todas las fases comparten código existente: no se presume independencia entre historias al editar servicios/UI comunes. Dentro de cada historia, seguir el orden listado salvo grupos `[P]` definidos abajo. Los gates reales de US2/US3 condicionan la aceptación, no la escritura de pruebas con fixtures ni la implementación local siguiente; el piloto no se declara completo hasta acreditarlos.

### Dependencias críticas de tareas

| Consumidor | Prerrequisitos | Motivo |
|---|---|---|
| T010 | T001, T009 | Head real y esquema de incorporación |
| T014 | T010, T011, T012, T013 | No exponer endpoints sin persistencia/servicios |
| T028 | T010, T025, T026, T027 | Crear presupuesto por scope, origen 1:N y FKs/constraints antes de ejecutar ensayos |
| T034 | T028, T032, T033 | No reclamar identidades fuera del ledger común |
| T036 | T029, T035 | Entradas fijadas e inventario antes de construir |
| T044 | T028, T031, T032, T033, T034, T040, T041, T043 | Decisiones de ensayo requieren contratos y efectos acotados |
| T045 | T044, T038, T039, T036, T037, T042 | Pipeline completo y leases antes del I/O real |
| T047 | T045, T046, T030, T041 | Comprobación, artefacto y limpieza durable antes de publicar |
| T052 | T051 + entorno/receta comprometida | Gate manual, no sustituible por mocks |
| T061 | T057, T058, T059, T060, T047 | Resolver y reservar versión vigente con token coherente |
| T067 | T052, T066 | Entregas reales desde una oferta ya comprobada |
| T073 | T068, T069, T070, T071, T072, T052, T067 | Ninguna aceptación o medición se presume realizada |

Las dependencias de esta tabla complementan el orden secuencial; no habilitan inversión de tareas intermedias. Antes de aplicar Alembic, consultar head real otra vez para no introducir una rama accidental si cambió el checkout. No escribir artefactos operativos con versiones/digests ficticios para desbloquear gates.

## Ejemplos de ejecución en paralelo

- **US1:** después de fundación, escribir T005, T006, T007, T008 en paralelo: contrato HTTP, fuente, carrera PostgreSQL y UI usan archivos separados. Después integrar modelo→servicios→router→cliente/UI y ejecutar todos los casos.
- **US2:** con US1 integrado, escribir T018–T024 en paralelo: endpoints, worker, capacidad, limpieza, manifiestos, infraestructura y UI tienen suites distintas. Implementación de catálogo/worker/modelos se hace en el orden listado para evitar archivos y contratos cambiantes.
- **US3:** con contratos de US2 disponibles, escribir T053–T056 en paralelo con fixtures de oferta preparada; integrar después snapshots→evaluación→aprobación→notificación→entrega/UI.
- **Cierre:** T068, T069 pueden avanzar juntos después de integrar las historias; ambos preceden al cierre final. Los gates de staging requieren coordinación del mismo entorno y no se marcan paralelizables.

## Trazabilidad y criterios de cierre

| Alcance | Implementación/validación |
|---|---|
| FR-001–FR-005 | T005–T017; sólo administrador, búsqueda/datos reales, importación única y ausencia de instalaciones |
| FR-006–FR-008 | T018–T052; producto cerrado, artefacto saneado, dos comprobaciones y publicación bloqueada sin evidencia |
| FR-009–FR-012 | T047, T057–T067; oferta estable, dos entradas, vigente al aprobar, instancias independientes |
| FR-013 | T019, T021, T038, T045, T054, T055; recuperación y duplicación evitada |
| FR-014 | T047, T061, T063, T067; retención histórica y despliegue sin Community Scripts |
| FR-015 | T053, T058, T064; «Otro» y vinculación administrativa |
| FR-016 | T008, T016, T024, T050, T056, T064; teclado, etiquetas, foco y datos válidos preservados |
| FR-017–FR-018 | T020, T021, T044, T045, T046, T052; ensayo desde NAP, TTL/aviso/limpieza y capacidad retenida |
| SC-001 | T017, T072; tarea humana <2 min con fuente disponible |
| SC-002 | T018, T022, T047, T052; 100 % de intentos incompletos/fallidos no seleccionables |
| SC-003 | T055, T052, T067; ciclo editable y aislamiento de dos cátedras |
| SC-004 | T066, T067, T072; pedido humano <3 min desde ambas entradas |
| SC-005 | T007, T019, T023, T054, T052; doble envío y pérdida de confirmación |
| SC-006 | T055, T067; enviar/aprobar/desplegar durante interrupción del proveedor |

## Implementation Strategy

1. **MVP de descubrimiento:** completar setup/fundación y US1 hasta T017; validar búsqueda e incorporación sin instalación. Este incremento aporta valor administrativo, pero todavía no entrega Draw.io a cátedras.
2. **Preparación reutilizable:** completar US2, construir paquete limpio y comprobar los dos ensayos antes de publicar; mantener visible cualquier limpieza pendiente. Si falta infraestructura, conservar T052 pendiente y continuar sólo trabajo local que use dobles, sin falsear evidencia.
3. **Piloto completo:** completar US3 y su gate real, entregar dos instancias independientes y desplegar otra durante caída del proveedor. El MVP funcional de extremo a extremo requiere las tres historias P1.
4. **Cierre:** regresión/migración/restauración, mediciones y manuales; actualizar casillas sólo cuando la acción y sus pruebas/evidencia estén verificadas. No añadir implementación de cuentas Draw.io, colaboración, instalación genérica ni actualizaciones automáticas.

## Ajustes tras análisis de consistencia

- U1: generation/cancel y cierre remoto persistente se diseñan/implementan en T025, T031, T038, T040 y T044–T046; T019/T021/T023 verifican órdenes atrasadas y reinicio.
- I1: T022/T030/T047/T052 exigen prueba sin proveedor de los ensayos antes de publicar; T067 conserva la prueba posterior de SC-006 con un pedido.
- U2: T005/T006/T011–T013 permiten sólo categoría; rechazan ambos filtros vacíos y combinan texto/categoría con AND.
- U3: T026/T028/T033 crean e inicializan PresupuestoBuilder por scope; T020 verifica la primera admisión concurrente y disco compartido.
- U4: T018/T027/T028/T044/T048/T050 permiten varias revisiones desde la misma incorporación sin cambio externo, conservando antecedente e idempotencia.

## Hooks

Al generar este documento no existe `.specify/extensions.yml`; no hay hooks `before_tasks` ni `after_tasks` que despachar.

## Estado de ejecución local — 2026-10-25

69/73 tareas realizadas y verificadas; comandos/resultados y alcance en [regresión](../../docs/evidencia/010/regresion.md). T052, T067 y T072 requieren builder/perfiles/staging y medición real aún no disponibles. T073 tiene [trazabilidad y estado parcial](../../docs/evidencia/010/cierre.md), pero permanece abierta por sus dependencias de aceptación. Las pruebas con fixtures/dobles no acreditan esas compuertas.

Los checks de evidencia Draw.io se implementaron en validación de manifiesto/evidencia y builder; el schema genérico de evidencia existente ya admite nombres de checks y se conserva compatible. La distribución reutiliza las primitivas seguras del instalador y añade registro dinámico recargable en API/worker/runner. La serialización/historial y orquestación existentes consumen los snapshots nuevos sin duplicar sus servicios.

## Ajuste posterior autorizado: simplicidad del alta (25/10/2026)

El usuario pidió eliminar el ensayo de 24 horas y los pasos técnicos del administrador. El recorrido vigente y sus verificaciones están en [alta simple](contracts/alta-simple-api.md) y [evidencia](../../docs/evidencia/010/preparacion-simple.md). Sustituye la interfaz avanzada de T050 y el TTL/aviso de FR-018 para el alta normal. Las referencias anteriores se conservan como historia; no deben reintroducir esos campos al portal.

- [X] Alta administrativa con nombre, descripción opcional y Small/Medium; perfil y versión automáticos, preparación recuperable e idempotente.
- [X] Confirmación funcional desde la aplicación y publicación o eliminación, sin JSON de evidencia en el formulario.
- [X] Preparaciones sin vencimiento automático; migración 010_04 y preservación verificada de Usuarios/Cátedras.
- [X] Pruebas del recorrido, eliminación, permisos, concurrencia PostgreSQL y migración; documentación actualizada.

T052/T067/T072/T073 permanecen pendientes en cuanto requieren infraestructura y mediciones reales. La comprobación simple registra su alcance explícitamente; no acredita pruebas avanzadas no ejecutadas ni una aceptación operativa del clúster universitario.

### Conexión local posterior (26/10/2026)

Se configuró el constructor separado, runner, réplicas, red/TLS y acceso desde esta PC.
Draw.io quedó listo para probar en dos LXC reales. Los fallos detectados en la integración
se corrigieron directamente, sin abrir una spec nueva, siguiendo la decisión de simplicidad.
Ver [comprobaciones y límites](../../docs/laboratorio-biblioteca.md). La publicación sigue
siendo una decisión de administración; los pendientes institucionales anteriores no se cierran.
