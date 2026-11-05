# Tasks: Remediación de hallazgos y cierre funcional de la práctica

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/operations.md](contracts/operations.md), [contracts/auth.md](contracts/auth.md), [contracts/catalog-ui.md](contracts/catalog-ui.md), [contracts/guest-runner.md](contracts/guest-runner.md), [contracts/service-definition.schema.json](contracts/service-definition.schema.json), [contracts/evidence.md](contracts/evidence.md), [contracts/evidence.schema.json](contracts/evidence.schema.json), [contracts/console-access.md](contracts/console-access.md) y [quickstart.md](quickstart.md).

**Fecha**: 2026-10-18. **Rama actual**: `009-remediar-hallazgos-cierre` (creada por pedido del usuario). **Feature**: `009-remediar-hallazgos-cierre`. Continuar en esta rama; no crear otra como parte de las tareas.

**Tests**: requeridos por FR-057, escenarios de la spec y constitución 4.0.0. Escribir las regresiones antes del comportamiento que corrigen y comprobar que fallan por ese comportamiento; usar PVE/runner/SMTP dobles por defecto. Locks, carreras, índices parciales y migraciones requieren PostgreSQL real aislado, no SQLite.

**Alcance**: las ocho historias integran la entrega; P2 ordena, no excluye. MFA es voluntario para ambos roles. Solo LXC; QEMU histórico se conserva. BookStack usa lectores individuales gestionados en la aplicación, sin alumnos NAP. No implementar módulo de backups de aplicaciones, IPAM ni software arbitrario.

## Formato y ejecución

- Cada tarea sigue `- [ ] Tnnn [P?] [USn?] Descripción con rutas`. `[USn]` solo aparece en fases de historia; todas comienzan pendientes.
- `[P]` permite trabajar en archivos distintos **cuando estén terminadas sus dependencias y el prerrequisito de fase**. No ejecutar todas las marcas del documento al mismo tiempo. Los bloques de pruebas preparan casos independientes; los scripts de producto solo se paralelizan después del builder común.
- Dependencias de fase más dependencias indicadas son obligatorias. Dentro de una fase, ejecutar por ID salvo los conjuntos paralelos explícitos. No escribir en un archivo mientras otra tarea lo modifica; migraciones se integran en una cadena Alembic única.
- Rutas relativas a la raíz del repositorio. Las rutas nuevas son salidas a crear durante implementación. Usar el código actual como base, sin regenerar el proyecto ni sustituir el stack. El detalle de campos/respuestas proviene del modelo y los contratos enlazados.
- La fase 2 contiene esquema pasivo compartido y helpers necesarios por varias historias; cada historia implementa su comportamiento. Datos de otras historias para su prueba independiente se preparan con fixtures, sin declarar implementado el flujo completo.
- Verificaciones de código y verificaciones reales de entorno son tareas distintas. Si falta clúster/red/operador, continuar trabajo independiente y conservar sin marcar las tareas que necesitan esa evidencia.

## Fase 1 — Preparación compartida

**Objetivo**: Dejar herramientas y entornos de prueba reproducibles sin modificar el comportamiento del portal.

**Prueba independiente**: Instalar desde locks y ejecutar pruebas aisladas, sin conectar a Proxmox real.

**Prerrequisito**: artefactos de diseño disponibles. `T001` precede a la preparación; T002, T003, T004 admiten paralelismo.

- [X] T001 Registrar revisión, head Alembic, resultados actuales y fallo del límite de disco obsoleto en `docs/evidencia/009/baseline.md`; separar baseline de resultados de implementación.
- [X] T002 [P] Declarar cryptography/jsonschema y herramientas de auditoría/prueba, y generar versiones reproducibles en `backend/requirements.txt` y `backend/requirements.lock` sin cambiar el stack.
- [X] T003 [P] Configurar Vitest/Testing Library, Playwright y scripts test/test:e2e en `frontend/package.json`, `frontend/package-lock.json`, `frontend/vitest.config.js` y `frontend/playwright.config.js`; usar dobles por defecto y preparar ejecución de SPA compilada para rendimiento (FR-057, SC-010).
- [X] T004 [P] Crear PostgreSQL 16 de pruebas aislado en `docker-compose.test.yml` y `backend/tests/postgres/conftest.py` con TEST_DATABASE_URL, sesiones independientes, teardown seguro y rechazo de bases operativas.
- [X] T005 Ampliar `backend/tests/fakes.py`, `backend/tests/factories.py` y `backend/tests/fakes_runner.py` con inventario local/compartido, externos, UPID tardío/fallido, marcas de propiedad, reloj y tres cátedras; impedir red real en `backend/tests/conftest.py`. Crear `infra/pytest.ini` con testpaths runner/tests services/tests y pythonpath .. ../backend, y `infra/conftest.py` con dobles y bloqueo de red/ejecución de subprocess reales para ambas suites infra. Las integraciones reales son opt-in y se excluyen del job CI.
- [X] T006 Fijar Node 22 >=22.12 con digest comprobado en `frontend.dockerfile` y documentar ejecución de suites/entornos en `backend/README.md` y `frontend/README.md`. Dep.: T003.
- [X] T007 Añadir `.github/workflows/009-validation.yml` con jobs backend, PostgreSQL, frontend, contratos e infra sobre locks, sin secretos/clúster real. Job infra ejecuta explícitamente desde raíz `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests` (o Python equivalente del job); exige recolección no vacía en ambas suites y falla si faltan rutas o tests, sin confiar en backend/pytest.ini. Distinguir integración manual. Dep.: T002, T003, T004, T005.

**Checkpoint**: herramientas listas, sin despliegue de aplicación.

## Fase 2 — Fundamentos bloqueantes

**Objetivo**: Proveer esquema compartido, contratos de error, tiempo, cifrado e idempotencia antes de las historias.

**Prueba independiente**: Fresh install y upgrade aditivo funcionan en PostgreSQL; los helpers rechazan datos inválidos y la repetición local no duplica efectos.

**Prerrequisito**: fase 1 completa. Bloquea todas las historias.

- [X] T008 [P] Añadir pruebas de errores, recursos, UTC/fechas institucionales y snapshots sin secretos en `backend/tests/test_contratos_base.py`; cubrir fin inclusivo y datos fuera de rango antes de implementar.
- [X] T009 [P] Escribir carreras de una misma clave, payload distinto y rollback sin efecto en `backend/tests/postgres/test_decisiones_idempotentes.py`, usando conexiones independientes y sin Proxmox.
- [X] T010 [P] Escribir `backend/tests/test_evidencias_009.py` y `backend/tests/test_evidence_schema.py` antes del registro: tres tipos de evidence.schema.json, formatos, JSON duplicado/extra/sobredimensionado, rol, hash alterado, identidad/revisión incorrectas, simulación operativa, no-store y replay sin otra fila (FR-035, FR-037, FR-052, FR-057).
- [X] T011 Crear modelos compartidos en `backend/app/models/definicion_servicio.py`, `identidad_infraestructura.py`, `compromiso_capacidad.py`, `operacion_infraestructura.py`, `calendario.py`, `vigencia.py`, `decision_idempotente.py`, `evidencia.py` y `cambio_acceso_consola.py` según data-model.md; FK/uniques/índices parciales y estados pasivos, sin lógica externa. Dep.: T008, T009, T010.
- [X] T012 Extender `backend/app/models/pedido.py`, `backend/app/models/servicio.py`, `backend/app/models/servicio_historial.py` y `backend/app/models/__init__.py` con revisiones, snapshots de modelo/recursos/definición/destino, identidad, disponibilidad y autor de sistema; preservar campos legacy e historial. Dep.: T011.
- [X] T013 Crear revisión aditiva `backend/alembic/versions/009_01_base_cierre.py` sobre el head real y `backend/tests/postgres/test_migracion_base_009.py`; verificar base vacía/copia sin destruir relaciones ni completar datos desconocidos. Dep.: T012.
- [X] T014 Implementar errores estructurados y esquemas comunes con extra=forbid en `backend/app/schemas/common.py`, `backend/app/utils/errors.py` y `backend/app/main.py`; conservar 403/409/422/502 y unidades GiB/MiB coherentes. Dep.: T013.
- [X] T015 Crear `backend/app/services/vigencia_service.py` y `backend/app/utils/clock.py` con zona IANA, intervalos UTC [inicio,fin_exclusivo), resolución de períodos configurados y cobertura de períodos aprobados y rechazo de activación sin vigencia fiable; pruebas con reloj inyectable. Dep.: T014.
- [X] T016 Implementar `backend/app/services/idempotencia_service.py` con clave por actor/método/ruta/hash, decisión y respuesta segura en la misma transacción, replay autorizado y conflicto 409; sin commits internos que separen efecto e historia. Dep.: T014.
- [X] T017 Implementar Fernet/keyring versionado, claves JWT/CSRF separadas y redacción en `backend/app/utils/secretos.py`, `backend/app/config.py` y `backend/tests/test_secretos.py`; probar descifrado/rotación y ausencia de valores en logs. Dep.: T014.
- [X] T018 Implementar `backend/app/services/evidencia_service.py`, `schemas/evidencia.py` y `routers/evidencias.py`, registrado en main.py: POST/GET admin, 64KiB, canonicalización/checksum, JSON inmutable y metadatos del servidor, referencias tipadas/revisión, idempotencia y rechazo de simulación en operación según contracts/evidence.md; sin rutas/URLs libres ni descarga. Dep.: T010, T013, T016, T017 (FR-035, FR-037, FR-052).
- [X] T019 Centralizar historia con actor usuario/sistema, motivo, operation_id y evento único en `backend/app/services/historial_service.py` y `backend/app/services/pedido_service.py`; probar append-only y efectos repetidos en `backend/tests/test_historial_eventos.py`. Dep.: T014, T016.

**Checkpoint**: migración aditiva/helpers comprobados; pueden comenzar historias.

## Fase 3 — US1: Operar únicamente sobre cátedras autorizadas (P1)

**Objetivo**: Cerrar lecturas y mutaciones ajenas por cualquier ruta, preservando la titularidad histórica.

**Prueba independiente**: Dos titulares y una persona con varias cátedras operan solo lo propio; reasignar o retirar permisos afecta la siguiente solicitud.

**Cobertura**: FR-001, FR-002, FR-003, FR-052. SC-001.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T020 [P] [US1] Ampliar `backend/tests/test_aislamiento_multicatedra.py` con detalle/última métrica/acceso/historial/consola propios y ajenos, sesión previa a reasignación y ausencia de efectos externos al denegar.
- [X] T021 [P] [US1] Crear `backend/tests/test_autorizacion_acciones_pedido.py` para cancelar/reenviar propios y ajenos como docente (403 sin efecto) y admin autorizado con motivo; rol falsificado y PATCH /pedidos/{id}/estado retirado; cubrir aprobar sin reserva antes de permitir vías nombradas.
- [X] T022 [P] [US1] Crear `backend/tests/test_revocacion_consola_009.py` y casos PostgreSQL en `backend/tests/postgres/test_cambios_consola.py` con doble de sesiones/ACL: bloquear antes de transferir, evidencia tardía/ajena/revisión cambiada, reinicio/replay, otros pools legítimos, fallo pendiente sin nuevo titular y concurrencia que considera administradores retirados/degradados pendientes (FR-001, FR-002, FR-052, SC-001).

### Implementación e integración

- [X] T023 [US1] Ampliar `backend/app/services/acceso_service.py` con comprobaciones de pertenencia y permiso actual reutilizables por lectura/servicio mutante; no confiar en catedra_id o rol enviados por cliente. Dep.: T020, T021.
- [X] T024 [US1] Aplicar guards antes de serializar o consultar infraestructura en `backend/app/routers/metricas.py`, servicios.py, pedidos.py y catedras.py; incluir ultimo_snapshot, historial, acceso y destino exacto de consola. Dep.: T023.
- [X] T025 [US1] Aplicar autorización dentro de `backend/app/services/pedido_service.py`, orquestacion_service.py y usuario_service.py; aprobar/rechazar/corregir/reenviar/cancelar/asignar/gestionar solo admin, incluso en pedidos propios. Docente crea/consulta pedidos, solicita renovación y opera servicios propios según constitución. Dep.: T023.
- [X] T026 [US1] Implementar `backend/app/services/consola_access_service.py` y extender acceso_service.py, usuario_service.py y catedra_service.py: trámite duradero de console-access.md, revisión e inventario de identidad nativa en models/usuario.py y catedra.py con migración aditiva; crear `backend/scripts/importar_identidades_consola.py` con actor/referencia y validación del inventario institucional, bloqueos por alcance y exclusión de cambios abiertos; operador institucional ejecuta revocación nativa, evidencia confirma antes de aplicar cambio. Revalidar último admin incluidas bajas pendientes y conservar otros pools; sin locks durante intervención externa ni comandos nuevos de runner. Dep.: T022, T018, T024, T025.
- [X] T027 [US1] Escribir primero `frontend/tests/cambios-consola.test.jsx` para roles y orden; después adaptar `backend/app/routers/usuarios.py`, catedras.py y crear cambios_consola.py registrado en main.py con 202/Location, GET/fallo/confirmación admin; crear `frontend/src/components/RegistroEvidencia.jsx` y `frontend/src/pages/CambiosConsola.jsx`, integrar App.jsx/api.js y administración de usuarios/cátedras con estados pendiente/fallido/completado y sin entrega anticipada. Solo importación de JSON tipado/UUID, sin secretos. Dep.: T026, T018.
- [X] T028 [US1] Retirar PATCH genérico de estado con 405 en `backend/app/routers/pedidos.py` y eliminar su uso en `frontend/src/services/api.js` y `frontend/src/pages/Pedidos.jsx`; usar acciones nombradas sin asignaciones directas de estado. Dep.: T024, T025.
- [X] T029 [US1] Ejecutar casos de `backend/tests/test_aislamiento_multicatedra.py`, test_autorizacion_acciones_pedido.py, test_revocacion_consola_009.py, postgres/test_cambios_consola.py y `frontend/tests/cambios-consola.test.jsx`; registrar denegaciones propias/ajenas y pendientes sin transferencia en `docs/evidencia/009/us1.md`. Prueba nativa real queda para T101/T102; dobles no acreditan esa revocación. Dep.: T028, T027.

**Checkpoint**: comprobar US1 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 4 — US2: Completar acceso y conservar administración (P1)

**Objetivo**: Exigir cambio inicial y MFA cuando fue activado, permitir recuperación y conservar administración sin credenciales conocidas.

**Prueba independiente**: Probar los cuatro propósitos, cuenta sin MFA, recuperación de un uso, logout/rotación y degradación concurrente del último administrador.

**Cobertura**: FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-046, FR-069, FR-070, FR-071. SC-002, SC-015.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T030 [P] [US2] Crear `backend/tests/test_auth_contrato_009.py` para cookies/CSRF/Origin, cuatro propósitos, login sin MFA, cambio inicial directo, setup cancelado, desafíos de cinco minutos y respuestas no-store según contracts/auth.md.
- [X] T031 [P] [US2] Añadir `backend/tests/postgres/test_auth_concurrencia_009.py` con replay TOTP/código, regenerar/desactivar simultáneos, ventana móvil de fallos y degradaciones/retiros concurrentes que preserven un admin.
- [X] T032 [P] [US2] Crear `frontend/tests/auth-flow.test.jsx` y `frontend/tests/e2e/auth.spec.js` con sesión restaurada, JSON local dañado, onboarding sin portal detrás, MFA opcional, recuperación/códigos y logout real.

### Implementación e integración

- [X] T033 [US2] Añadir `backend/app/models/autenticacion.py`, `backend/app/models/evento_seguridad.py` y campos en `backend/app/models/usuario.py`, registrados en `backend/app/models/__init__.py`; crear `backend/alembic/versions/009_02_autenticacion.py` para sesiones/desafíos/códigos/ventana móvil/eventos, cifrando TOTP legacy sin desactivarlo y rechazando JWT sin sid. Dep.: T030, T031.
- [X] T034 [US2] Implementar `backend/app/services/auth_service.py` y `backend/app/utils/security.py` con JWT en cookie, sid revocable, versión, expiración/rotación por propósito, antirreplay TOTP y bcrypt compatible sin truncar >72 bytes. Dep.: T033.
- [X] T035 [US2] Implementar ventana móvil serializada de cinco fallos/cuenta y treinta/origen en quince minutos, espera de quince minutos y mensajes indistinguibles en `backend/app/services/auth_intentos_service.py`; aceptar IP reenviada solo de proxies confiables. Dep.: T033.
- [X] T036 [US2] Implementar setup/replacement confirmados, diez códigos hash por generación, consumo único, recuperación restringida y desactivación deliberada en `backend/app/services/segundo_factor_service.py`; preservar factor activo hasta confirmar sustituto. Dep.: T034, T035.
- [X] T037 [US2] Adaptar `backend/app/routers/auth.py` y `backend/app/schemas/auth.py` a login/me/csrf/logout, challenge, contraseña inicial, setup/verify/replacement/recovery/regenerate/disable de contracts/auth.md; exigir sesión operativa en todos los routers de dominio. Dep.: T036.
- [X] T038 [US2] Proteger degradación/desactivación/retiro en `backend/app/services/usuario_service.py` y `backend/app/routers/usuarios.py` con lock administrativo común y conteo transaccional incluidas bajas/degradaciones pendientes; integrar trámite T026, invalidación de sesiones/bloqueo de dominio aun tras otro login al admitir y revalidación al completar sin cambios parciales ni cero administradores habilitados. Dep.: T037, T026.
- [X] T039 [US2] Crear `backend/scripts/bootstrap_admin.py` y `backend/scripts/recuperar_2fa.py` con alta inicial interactiva sin defaults y autorización asistida de 256 bits/cinco minutos/un uso, actor/motivo/referencia obligatorios; probarlos en `backend/tests/test_cli_identidad.py` sin cuentas auxiliares. Dep.: T038.
- [X] T040 [US2] Crear `backend/app/models/notificacion.py` y `backend/alembic/versions/009_03_outbox.py` con evento/destinatario/canal únicos, cátedra nullable y secreto provisional cifrado separado del payload; no incluir credenciales de servicios ni códigos. Dep.: T033.
- [X] T041 [US2] Implementar `backend/app/services/notificacion_service.py` y adaptar `backend/app/services/email_service.py` y `backend/app/services/usuario_service.py` con outbox transaccional, destinatarios vigentes, backoff/Message-ID y borrado del secreto temporal; probar fallo SMTP y logs mock sin contraseña en `backend/tests/test_outbox_bienvenida.py`. Dep.: T040, T037.
- [X] T042 [US2] Eliminar seeds/migraciones automáticas del arranque operativo en `backend/scripts/startup.sh` y separar `backend/scripts/seed_dev.py` y `backend/scripts/seed_admin.py` del bootstrap explícito; un reinicio no modifica cuentas existentes ni crea claves conocidas. Dep.: T039, T041.
- [X] T043 [US2] Adaptar `frontend/src/services/api.js`, `frontend/vite.config.js` y `frontend/src/hooks/useSession.js` a misma origin, cookies/CSRF y getMe; quitar bearer/perfil autoritativo de Web Storage y manejar 401/403/rotación sin perder formularios válidos. Dep.: T037.
- [X] T044 [US2] Implementar etapas y seguridad de cuenta en `frontend/src/pages/Login.jsx`, `frontend/src/pages/Seguridad.jsx`, `frontend/src/App.jsx`, `frontend/src/components/TopNav.jsx` y `frontend/src/components/CambiarPasswordInicialModal.jsx`; guardar códigos una vez y no imponer alta MFA a quien no la eligió. Dep.: T043, T036.
- [X] T045 [US2] Actualizar `backend/tests/conftest.py`, factories.py y fixtures de frontend/tests para autenticación por cookie/CSRF y propósito, preservando pruebas reales de ingreso y evitando JWT operativo inventado como prueba de MFA. Dep.: T037.
- [X] T046 [US2] Ejecutar suites US2 y ensayo asistido del único admin en entorno aislado; registrar MFA optativo, revocación, carreras y ausencia de seeds/secretos en `docs/evidencia/009/us2.md`. Dep.: T044, T045, T042, T038.

**Checkpoint**: comprobar US2 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 5 — US3: Comprometer capacidad real sin perder reservas (P1)

**Objetivo**: Usar una sola contabilidad por destino, serializar aprobación/inicio/liberación y conservar reservas hasta conocer el efecto real.

**Prueba independiente**: Con saldo de una asignación, diez repeticiones de decisiones concurrentes no duplican compromiso/historia; incluir externos y storage compartido/local.

**Cobertura**: FR-010, FR-011, FR-012, FR-013, FR-014, FR-015, FR-016, FR-017, FR-066. SC-003.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T047 [P] [US3] Ampliar `backend/tests/test_capacidad_reserva.py` y test_despliegue_usa_reserva.py con EN_DESPLIEGUE/ERROR incierto, unión propio/externo, almacenamiento elegible sin doble resta, físico/lógico, márgenes y snapshot inmutable.
- [X] T048 [P] [US3] Crear `backend/tests/postgres/test_admision_capacidad_009.py` con doble aprobación del mismo pedido, dos aprobaciones/inicios para saldo de uno y aprobar/revertir/expirar simultáneos; diez repeticiones con barreras y sesiones independientes.
- [X] T049 [P] [US3] Crear `backend/tests/test_evaluacion_asignacion_009.py` para POST de selección efectiva, token de sesenta segundos ligado a recursos/destino/fechas/revisión, stale 409, overrides prohibidos y sobreasignación con motivo.
- [X] T050 [P] [US3] Escribir primero regresiones en `backend/tests/test_reserva_expiracion.py` sobre alta futura, max(aprobación,inicio)+24h limitado por fin, despliegue frente a caducidad y comprobación inmediata aunque job no corrió; conservar períodos previos revocados.

### Implementación e integración

- [X] T051 [US3] Implementar inventario normalizado y perfiles permitidos en `backend/app/services/inventario_service.py`, `backend/app/services/proxmox_client.py` y `infra/profiles/inventory.example.json`; identificar pools compartidos una vez y rechazar información incompleta con 502. Dep.: T047, T048, T049, T050.
- [X] T052 [US3] Rehacer `backend/app/services/capacidad_service.py` sobre compromisos_capacidad e inventario por identidad/volumen; distinguir asignación configurada/físico libre, mantener disco detenido y no sumar reservas históricas del pedido como otro contador. Dep.: T051.
- [X] T053 [US3] Crear `backend/app/services/admision_service.py` con lock 4001 antes de row lock y relectura, control de vigencia/estado/destino/operación y registro conjunto de compromiso, decisión, operación pendiente, transición e historial; sin polling en transacción. Dep.: T052.
- [X] T054 [US3] Implementar evaluación firmada de asignación efectiva en `backend/app/services/evaluacion_service.py` y `backend/app/schemas/pedido.py`; incluir mínimos/definición, destino, períodos, revisión e inventario y exigir reevaluación al cambiar selección. Dep.: T053.
- [X] T055 [US3] Adaptar `backend/app/routers/pedidos.py` y capacidad.py a POST evaluacion/aprobar y panorama por destino; reservar alta futura desde aprobación, justificar sobreasignación y retirar GET de evaluación con 405. Dep.: T054.
- [X] T056 [US3] Unificar start/reactivar en `backend/app/services/orquestacion_service.py` e inactividad_service.py y `backend/app/routers/servicios.py` usando admisión común; sin capacidad/vigencia quedan detenidos con disco retenido, sin segunda reserva. Dep.: T055.
- [X] T057 [US3] Unificar reversión/ajuste/baja lógica de pedido y vencimiento de reserva en `backend/app/services/pedido_service.py` y capacidad_service.py: liberar y revocar período solo sin dispatch iniciado; incierto/en vuelo se reconcilia. Dep.: T056.
- [X] T058 [US3] Ejecutar pruebas US3 con PostgreSQL y doble PVE, y registrar identidad/compromiso único, almacenamiento externo y cada carrera de SC-003 en `docs/evidencia/009/us3.md`; no usar SQLite como evidencia de exclusión real. Dep.: T057.

**Checkpoint**: comprobar US3 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 6 — US4: Confirmar resultados y recuperar operaciones (P1)

**Objetivo**: Desacoplar HTTP y trabajo externo, conservar identidad/tarea y reconciliar sin recrear recursos.

**Prueba independiente**: Simular tarea fallida/tardía y caída antes/después del envío; recuperar un único recurso propio y no liberar capacidad antes de confirmar.

**Cobertura**: FR-019, FR-020, FR-021, FR-022, FR-033, FR-034, FR-048. SC-004.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T059 [P] [US4] Crear `backend/tests/test_operaciones_contrato_009.py` y `frontend/tests/e2e/operaciones.spec.js` para órdenes 202/Location, consulta autorizada, Idempotency-Key/alias, conflicto abierto y resultado confirmado distinto de acceso utilizable; usar contracts/operations.md.
- [X] T060 [P] [US4] Crear `backend/tests/test_operaciones_recuperacion.py` con corte dispatch/UPID/commit, tarea tardía/fallida, colisión ajena y éxito fuera de vigencia; verificar compromiso/historia y nunca adoptar por hostname.
- [X] T061 [P] [US4] Añadir `backend/tests/postgres/test_worker_leases.py` con SKIP LOCKED, lease expirado, worker viejo y bloqueo de operaciones incompatibles por identidad; probar que takeover no reenvía POST incierto.

### Implementación e integración

- [X] T062 [US4] Implementar `backend/app/services/operacion_service.py` y `backend/app/schemas/operacion.py`: admisión duradera, fases, claves/referencias, reclamación por lease/generación y confirmación CAS; errores seguros y consulta filtrada. Dep.: T059, T060, T061.
- [X] T063 [US4] Crear `backend/app/worker.py` y corregir `backend/app/services/scheduler.py` y `backend/app/main.py` para scheduler solo en worker, heartbeat/owner/generation y liberación condicional; API y ejecución manual comparten trabajos y locks. Dep.: T062.
- [X] T064 [US4] Adaptar `backend/app/services/proxmox_client.py` y crear infraestructura_io.py con timeout de transporte, to_thread/concurrencia máxima cuatro y resultados tipados, sin compartir AsyncSession ni cliente mutable inseguro entre tareas. Dep.: T063.
- [X] T065 [US4] Implementar `backend/app/services/identidad_infra_service.py` con reclamación VMID global, pool/resource_uuid/nonce, marca externa y reconciliación antes de adoptar; liberar identidad solo tras ausencia confirmada. Dep.: T064.
- [X] T066 [US4] Rehacer `backend/app/services/orquestacion_service.py` sobre operaciones: persistir dispatch_started antes del POST, guardar UPID y confirmar tarea+recurso; quitar credenciales/enlaces ficticios y bloquear QEMU antes del envío. Dep.: T065.
- [X] T067 [US4] Implementar `backend/app/services/reconciliacion_service.py` para pendientes/inciertas, éxito tardío, ausencia segura y detención fuera de cobertura; mantener compromiso hasta resultado y no regenerar identidad al reintentar. Dep.: T066.
- [X] T068 [US4] Adaptar `backend/app/routers/servicios.py`, pedidos.py y crear operaciones.py registrado en main.py: deploy/retry/start/reactivar/stop/restart/delete devuelven 202; jobs pausa/vencimiento usan el mismo ejecutor y confirman antes de liberar. Dep.: T067.
- [X] T069 [US4] Adaptar `frontend/src/services/api.js`, `frontend/src/hooks/useOperacion.js` y `frontend/src/pages/Servicios.jsx` con polling por recurso, recarga, backoff/visibilidad, bloqueo de doble confirmación y mensajes pendientes/fallidos/ inciertos sin éxito anticipado. Dep.: T068.
- [X] T070 [US4] Ejecutar pruebas US4 y `frontend/tests/e2e/operaciones.spec.js` con PVE lento y reinicio de worker; registrar exactamente un recurso propio, tarea real confirmada y consultas independientes responsivas en `docs/evidencia/009/us4.md`. Dep.: T069.

**Checkpoint**: comprobar US4 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 7 — US5: Solicitar y aprobar datos y vigencias coherentes (P2)

**Objetivo**: Completar calendario configurable y formularios, conservar períodos aprobados y pausar recesos sin perder datos.

**Prueba independiente**: Dos años, tres modalidades académicas y personalizada coinciden en formulario/aprobación/servicio; receso rechaza inicios y reactivación comprueba capacidad.

**Cobertura**: FR-018, FR-023, FR-024, FR-025, FR-026, FR-027, FR-028, FR-030, FR-031, FR-032, FR-041, FR-064, FR-065, FR-066, FR-068, FR-072. SC-006, SC-014, SC-016.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T071 [P] [US5] Crear `backend/tests/test_calendario_vigencias_009.py` para año/período ausente, fechas locales/fin exclusivo, aprobación futura, snapshot tras editar calendario, sustitución/reaprobación y validaciones de payload.
- [X] T072 [P] [US5] Crear `backend/tests/postgres/test_renovacion_periodos_009.py` con renovación pendiente/aprobada en receso, continuidad contigua, vencimiento concurrente, disco retenido y reactivación con/sin capacidad sin recreación.
- [X] T073 [P] [US5] Crear `frontend/tests/pedidos-formularios.test.jsx` y `frontend/tests/e2e/calendario-renovacion.spec.js` para cerrar/abrir, cambio de modelo/template/modalidad/año, reenvío solo admin y docente sin cancelar/reenviar propio, edición de costo con token invalidado, 409 y sobreasignación sin perder datos válidos.

### Implementación e integración

- [X] T074 [US5] Implementar `backend/app/services/calendario_service.py`, schemas/calendario.py y routers/calendarios.py con GET/PUT versionado por año, zona institucional y períodos incompletos explícitos; registrar rutas en main.py. Dep.: T071, T072, T073.
- [X] T075 [US5] Integrar resolución/snapshot de períodos en `backend/app/services/vigencia_service.py`, pedido_service.py y schemas/pedido.py; copiar fechas/revisión al aprobar, caducidad futura correcta y prohibir despliegue/inicio fuera de cobertura. Dep.: T074.
- [X] T076 [US5] Implementar renovación/modificación auditada en `backend/app/services/renovacion_service.py` y routers/servicios.py; crear nuevo período/revision_decision, excluir sustituido y resolver pedido sin nueva alta ni encender/reemplazar datos. Dep.: T075.
- [X] T077 [US5] Corregir `backend/app/services/vencimiento_service.py` e inactividad_service.py: pendiente/futura no extiende cobertura, aviso siete días o inmediato en período corto y pausa vía operación confirmada al comenzar receso; quitar fallback de 180 días. Dep.: T076.
- [X] T078 [US5] Endurecer `backend/app/schemas/pedido.py`, `backend/app/schemas/template.py`, `backend/app/schemas/usuario.py` y `backend/app/schemas/catedra.py` con recursos positivos, correo, compatibilidad/oferta vigente y opciones allowlist; preservar QEMU/plantillas retiradas solo en lectura histórica. Dep.: T075.
- [X] T079 [US5] Crear `frontend/src/pages/Calendario.jsx` e integrar ruta admin en `frontend/src/App.jsx` y `frontend/src/components/TopNav.jsx`, y calendario en `frontend/src/services/api.js`; mostrar fechas, revisión, períodos ausentes y conflicto al guardar. Dep.: T074.
- [X] T080 [US5] Corregir `frontend/src/components/NuevoPedidoModal.jsx`, ReenviarPedidoModal.jsx y AjustePedidoModal.jsx con reset al abrir, opciones compatibles, año/fecha y errores por campo, sin parámetros PVE docentes; reenvío/cancelación visibles solo admin, docente consulta motivos sin editar el pedido existente. Dep.: T078, T079, T025.
- [X] T081 [US5] Corregir `frontend/src/components/AprobarPedidoModal.jsx` y PanelCapacidad.jsx para evaluar la selección actual, destino/fechas reales, motivo de sobreasignación y 409 reevaluable; ninguna confirmación usa costo/token anterior. Dep.: T080.
- [X] T082 [US5] Actualizar `frontend/src/pages/Pedidos.jsx`, Servicios.jsx y components/PanelCatedra.jsx con períodos, próxima fecha, reserva/plazo y receso; distinguir Renovación registrada de contenedor encendido y prohibir PATCH vence_at. Dep.: T077, T081.
- [X] T083 [US5] Ejecutar casos US5 y `frontend/tests/e2e/calendario-renovacion.spec.js` con reloj controlado y dato persistente; registrar dos años, límites temporales, receso y resultados con/sin cómputo en `docs/evidencia/009/us5.md`. Dep.: T082.

**Checkpoint**: comprobar US5 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 8 — US6: Recibir una plataforma o aplicación utilizable (P2)

**Objetivo**: Construir referencias LXC reproducibles y entregar acceso real solo después de verificar la instancia, sin instalar a mano en cada despliegue.

**Prueba independiente**: Preparar dos PostgreSQL y dos BookStack desde catálogo, comprobar aislamiento/persistencia y dos lectores individuales por BookStack; Linux admite consola propia con login.

**Cobertura**: FR-028, FR-033, FR-034, FR-035, FR-036, FR-037, FR-038, FR-052, FR-061, FR-062, FR-063, FR-065, FR-067, FR-073. SC-005, SC-013, SC-017.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T084 [P] [US6] Crear `backend/tests/test_catalogo_definiciones_009.py` con Draft 2020-12/formatos, tres productos, transiciones, manifiesto parcial solo borrador, versión inmutable, retiro que respeta aprobación y rechazo de scripts/overrides libres.
- [X] T085 [P] [US6] Crear `infra/runner/tests/test_runner.py` y `backend/tests/test_guest_runner_client.py` para JSON limitado, hostkey errónea, identidad/pool/nonce/digest ajenos, symlinks, corte/reintento idempotente y ausencia de secretos en argv/log/salida; comprobar recolección con `infra/pytest.ini` y uso de dobles sin red/subprocess de infraestructura real en CI.
- [X] T086 [P] [US6] Crear `backend/tests/test_entrega_acceso_009.py` y `frontend/tests/acceso-servicio.test.jsx` para bootstrap confirmado sin entrega, admin solo_validacion, docente sin revelado prematuro, importación previa POST /evidencias y prueba de red por instancia; rechazar evidencia desconocida/alterada/otro tipo, otra identidad/nonce/preparación, simulación y endpoint/instante discordantes; 403/409/no-store.

### Implementación e integración

- [X] T087 [US6] Implementar `backend/app/services/catalogo_service.py`, schemas/definicion.py, routers/definiciones.py y scripts/validar_definicion.py con schema/digest/receta permitida y evidencia validacion_definicion del registro T018; comprobar UUID/hash/código/versión/imagen/receta y dos instancias/checks según contracts/evidence.md, publicar solo validada y retirar sin sustituir snapshots. Dep.: T084, T085, T086, T018.
- [X] T088 [US6] Integrar `backend/app/models/recurso_template.py`, schemas/template.py y routers/templates.py con perfiles de recursos ligados a definiciones compatibles; impedir QEMU/ofertas no publicadas para altas y conservar lectura de referencias antiguas. Dep.: T087.
- [X] T089 [US6] Crear `infra/services/build_image.py` y sanitize.py con rootfs Ubuntu 24.04 amd64, paquetes/commits fijados, digests y productor de JSON validacion_definicion para importación admin; eliminar bases/usuarios privados, claves/contraseñas/logs y probar saneamiento en `infra/services/tests/test_images.py`. Ejecutar explícitamente ambas suites infra con -c infra/pytest.ini y comprobar job CI/no red. Dep.: T088.
- [X] T090 [P] [US6] Crear `infra/services/linux/build.sh` y bootstrap.py para Linux no privilegiado con napadmin/guest_password de instancia, sudo local, root bloqueado y sin autologin; verificar login/configuración y reintento sin restablecer claves. Dep.: T089.
- [X] T091 [P] [US6] Crear `infra/services/postgresql/build.sh` y bootstrap.py para PostgreSQL 16: datos nuevos, rol/base propios sin superuser/createrole/replication, SCRAM/TLS/red permitida y probe de escritura/lectura revertida; no reutilizar base interna NAP. Dep.: T089.
- [X] T092 [P] [US6] Crear `infra/services/bookstack/build.sh` y `infra/services/bookstack/bootstrap.py` para BookStack 26.09.1, PHP 8.3 y MariaDB 10.11, APP_KEY/passwords únicos, APP_URL/TLS reales, docente admin local, público/registro desactivados y local_secure para imágenes/adjuntos. Dep.: T089.
- [X] T093 [US6] Implementar `infra/runner/nap_guest_runner.py`, authorized_keys.example y sudoers.example con forced-command, operaciones bootstrap/inspect/verify, propiedad antes/después, rutas/recetas fijas, temporales privados y deduplicación persistente por instancia/operación. Dep.: T090, T091, T092.
- [X] T094 [US6] Crear `backend/app/services/guest_runner_client.py` mediante OpenSSH/subprocess sin shell, JSON stdin, known_hosts fijo, credenciales montadas y deadlines; no aceptar host/URL/comandos del solicitante ni abrir SSH guest. Dep.: T093.
- [X] T095 [US6] Implementar `backend/app/services/preparacion_service.py` y probes_servicio.py integrados con orquestacion_service.py: secretos cifrados una vez antes de bootstrap, inspección real de IP/endpoint, salud autenticada y reanudación sin regenerar APP_KEY/datos. Dep.: T094.
- [X] T096 [US6] Crear `backend/app/services/service_access_service.py` y adaptar schemas/servicio.py/routers/servicios.py con metadatos y POST revelado separado, auditoría sin valores y acceso inicial tipado; retirar serialización de credenciales/enlaces falsos. Dep.: T095.
- [X] T097 [US6] Implementar POST verificar-acceso en `backend/app/services/verificacion_acceso_service.py` y routers/servicios.py usando referencia UUID previamente creada por T018: verificar hash/tipo, instancia/nonce_hash/preparación, endpoint/red/instante, pruebas funcionales y entorno real; solo evidencia válida activa pedido/entrega/aviso una vez. No descarga referencias ni admite booleano. Dep.: T096, T018.
- [X] T098 [US6] Crear `frontend/src/pages/Definiciones.jsx` y adaptar Catalogo.jsx, Templates.jsx, components/TemplatesAdmin.jsx, App.jsx y services/api.js con borrador/evidencia/publicación/retiro y perfiles; no exponer recetas o parámetros PVE al docente. Dep.: T097.
- [X] T099 [US6] Actualizar `frontend/src/pages/Servicios.jsx` y components/PanelCatedra.jsx con acceso tipado, solo_validacion, prueba admin e importación mediante RegistroEvidencia.jsx antes de verificar por UUID; revelado explícito sin copiar secretos por defecto y gestión de lectores dentro de BookStack. Reusar formulario en Definiciones.jsx para evidencia del builder. Dep.: T098, T027.
- [X] T100 [US6] Ampliar `specs/009-remediar-hallazgos-cierre/guia-servicios-referencia.md` y crear `infra/services/README.md` con build/validar/publicar/desplegar/mantener/retirar y registro de otro producto compatible sin cambiar flujo de pedidos; distinguir libro virtual definitivo. Dep.: T099.
- [X] T101 [US6] Preparar con infraestructura runner/hostkeys/ACL/perfiles e identidad PVE individual, demostrar procedimiento de revocación de permisos heredados y terminación de sesiones/consolas previas según contracts/console-access.md antes de habilitar consola. Construir/sanear imágenes y publicar tras dos ensayos con evidencia importada; registrar versiones/digests/operador y faltantes en `docs/evidencia/009/preparacion-servicios.md`. Sin prueba de revocación, consola no se habilita. Dep.: T100, T027.
- [ ] T102 [US6] Ejecutar desde otra computadora dos despliegues por producto sin instalación manual; PostgreSQL persistente, Linux consola propia y reasignación/retiro con sesión nativa abierta y URL guardada denegadas, otros pools legítimos conservados y fallo de revocación pendiente sin transferencia. BookStack con dos lectores, revocación aislada y archivos privados. Registrar UUID/checksum de evidencias reales en `docs/evidencia/009/us6.md`. Dep.: T101.

**Checkpoint**: comprobar US6 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 9 — US7: Comprender estado, alertas y acciones accesibles (P2)

**Objetivo**: Observar por intervalos reales, notificar incidentes y dar una UI accesible que distinga fallo de ausencia de datos.

**Prueba independiente**: Contadores reiniciados/duplicados y huecos no falsean actividad; un incidente genera apertura/recuperación únicas y los recorridos funcionan con teclado.

**Cobertura**: FR-029, FR-039, FR-040, FR-042, FR-043, FR-044, FR-045, FR-047, FR-048, FR-049, FR-050. SC-007, SC-008, SC-009, SC-010, SC-011.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T103 [P] [US7] Crear `backend/tests/test_metricas_intervalos_009.py` con contadores BIGINT, uptime/reset, deltas, huecos, duplicados y máximos de la misma muestra; GET no captura y manual no incrementa cobertura.
- [X] T104 [P] [US7] Crear `backend/tests/test_alertas_009.py` con dos negativos separados un minuto, quince minutos >90%, recuperación, falta de observación y deduplicación por incidente; incluir destinatario retirado y SMTP fallido sin revertir negocio.
- [X] T105 [P] [US7] Crear `backend/tests/test_resumen_historico_009.py` para agregación idempotente antes de purga, integrales/cobertura/deltas de borde y consumo por cátedra/período tras baja/reasignación.
- [X] T106 [P] [US7] Crear `frontend/tests/estados-accesibilidad.test.jsx` y `frontend/tests/e2e/teclado.spec.js` para carga/vacío/error/datos anteriores, fallos parciales, filtros por modelo, Clipboard denegado y foco/Tab/Escape/fondo inerte.

### Implementación e integración

- [X] T107 [US7] Extender `backend/app/models/metrica.py` y crear `backend/app/models/incidente.py` y `backend/app/models/metricas_resumen.py`, más `backend/alembic/versions/009_11_observacion.py` con minuto único, índices servicio/fecha, límites observados y único incidente abierto por servicio/tipo. Dep.: T103, T104, T105, T106.
- [X] T108 [US7] Rehacer `backend/app/services/metricas_service.py` para captura de estado/salud por minuto, batch con sesiones propias, calidad confirmada/no_confirmada, contadores/deltas/época y límites observados; manual y scheduler deduplican el mismo intervalo. Dep.: T107.
- [X] T109 [US7] Corregir `backend/app/services/inactividad_service.py` con siete días, >=80% de intervalos distintos, CPU máxima<5%, tráfico de ventana<1MB y gracia48h; avisar/cancelar pausa y ejecutar por operación confirmada, nunca por falta de observación. Dep.: T108.
- [X] T110 [US7] Crear `backend/app/services/alerta_service.py` y adaptar notificacion_service.py con reglas versionadas, apertura/recuperación únicas y outbox por evento/destinatario/canal; revalidar destinatarios al enviar y mostrar fallos solo a administración. Dep.: T109.
- [X] T111 [US7] Crear `backend/app/services/resumen_metricas_service.py` para resúmenes diarios con integrales/tiempos/asignación/cobertura y purga >90 días solo tras agregado cerrado; conservar extremos de delta e historia sin caducidad. Dep.: T108.
- [X] T112 [US7] Optimizar `backend/app/routers/metricas.py` y services/metricas_service.py con últimas muestras por lote, rango/resolución y <=500 puntos, sin llamadas PVE por fila/GET; añadir routers/alertas.py y lectura de estado de correo admin. Dep.: T110, T111.
- [X] T113 [US7] Registrar captura/alertas/vigencias/reservas cada minuto, operaciones cada cinco segundos, inactividad horaria y resumen/purga diaria en `backend/app/worker.py` y services/scheduler.py; manual usa mismo lock y no duplica cadencia por visitante. Dep.: T112.
- [X] T114 [US7] Crear `frontend/src/hooks/useRemoteData.js` y adaptar pages/Servicios.jsx, Metricas.jsx y components/PanelCatedra.jsx con errores por bloque, reintento/edad, cancelación de respuestas antiguas y filtro por modelo snapshot; añadir `frontend/src/components/AlertasServicio.jsx`. Dep.: T113.
- [X] T115 [US7] Corregir `frontend/src/components/ui.jsx` y `frontend/src/index.css` con nombre/semántica modal, foco inicial/retorno, ciclo Tab, fondo inerte, labels/errores y resultados accesibles; migrar formularios afectados y no cerrar un paso obligatorio al fondo. Dep.: T114.
- [X] T116 [US7] Aplicar carga diferida de rutas/gráficas y resumen textual de métricas en `frontend/src/App.jsx` y pages/Metricas.jsx; centralizar polling sin multiplicar capturas, registrar comparación de bundle en `docs/evidencia/009/frontend-rendimiento.md`. Dep.: T115.
- [X] T117 [US7] Crear `backend/scripts/validar_carga.py` con datos aislados de cien servicios/noventa días a un minuto (12,96M muestras), diez sesiones y despliegue simulado >=30s; exportar fixture/IDs de recorridos y latencias HTTP/consultas/índices como diagnóstico, no como aceptación SC-008; guardar recursos/entorno sin generar datos operativos. Dep.: T116.
- [X] T118 [US7] Implementar `frontend/tests/e2e/rendimiento.spec.js` y `frontend/scripts/validar_rendimiento.mjs`, y script test:performance en package.json, contra SPA compilada/API/PostgreSQL aislados de T117; diez contextos autenticados, cinco calentamientos por contexto/recorrido y >=100 muestras medidas por recorrido: pedidos, servicios filtrados y métricas. Medir interacción→resultado visible/utilizable incluyendo gráfica/texto, p95 <=3s por flujo y resultados válidos en <=3s en >=95% del total de muestras; errores/timeouts cuentan como incumplimientos. Exportar muestras y entorno en `docs/evidencia/009/rendimiento-navegador.json`, conforme quickstart (SC-008, FR-048). Dep.: T117, T003.
- [ ] T119 [US7] Ejecutar pruebas US7, ambas mediciones de carga distinguiendo p95 navegador del HTTP, teclado y responsable de una cátedra de prueba (pedido/consulta sin ayuda y formulario <=3min); corregir incumplimientos y registrar tiempos/resultados por recorrido, cobertura/incidentes en `docs/evidencia/009/us7.md`. Dep.: T118.

**Checkpoint**: comprobar US7 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 10 — US8: Operar y entregar un prototipo verificable (P2)

**Objetivo**: Completar migración y despliegue seguro, respaldar/restaurar y entregar documentos con evidencia real.

**Prueba independiente**: Fresh/upgrade y restauración en entorno separado preservan datos; portal y aplicaciones se usan desde otra computadora y la evidencia distingue simulación de integración.

**Cobertura**: FR-051, FR-052, FR-053, FR-054, FR-055, FR-056, FR-057, FR-058, FR-059, FR-060. SC-011, SC-012.

**Prerrequisito**: fases anteriores en el orden recomendado; ver dependencias y posibles adelantos al final.

### Pruebas antes de implementar

- [X] T120 [P] [US8] Crear `backend/tests/postgres/test_migracion_cierre_009.py` con copia legacy/fresh, UTC naive, VMID duplicados, fechas desconocidas, secretos no válidos y EN_DESPLIEGUE/ERROR; exigir esquema final coherente sin pérdida histórica.
- [X] T121 [P] [US8] Crear `backend/tests/test_restauracion_seguridad_009.py` para revocar sesiones/desafíos/códigos restaurados, preservar MFA y cancelar secretos antiguos de bienvenida; verificar claves necesarias y workers/outbox deshabilitados hasta reconciliar.
- [X] T122 [P] [US8] Crear `backend/tests/test_configuracion_operativa_009.py` con origins/keys/CA/token/perfiles/SMTP incompletos, URLs localhost de visitante y reinicio sin seeds; fallo de preflight debe explicar faltantes sin imprimir secretos.

### Implementación e integración

- [X] T123 [US8] Crear `backend/scripts/preflight.py` y services/preflight_service.py con informe sin secretos de entorno/inventario/datos, duplicados, períodos legacy y propiedad; no borrar historia ni modificar infraestructura desde validación. Dep.: T120, T121, T122.
- [X] T124 [US8] Crear `backend/scripts/backfill_cierre_009.py` con bitácora idempotente para snapshots, identidades, ledger y períodos fiables; regularizar duplicados/fechas mediante decisión admin, retener inciertos y convertir tiempos conocidos como UTC explícito. Dep.: T123.
- [X] T125 [US8] Exponer regularización auditada de recursos legacy en `backend/app/routers/servicios.py` y `frontend/src/pages/Servicios.jsx`: fechas fiables por decisión, conflictos de identidad y acceso no verificado; impedir nueva activación sin resolver, sin fechas inventadas. Dep.: T124.
- [X] T126 [US8] Crear `backend/alembic/versions/009_13_cierre_constraints.py` con CHECK/uniques/FK definitivos tras preflight/backfill y retirar secretos en claro/segundos contadores de modelos/schemas; fresh y upgrade deben converger sin downgrade destructivo. Dep.: T125.
- [X] T127 [US8] Crear `docker-compose.production.yml`, `infra/proxy/nginx.conf` y ejemplo de entorno operativo sin secretos; separar release migration/API/worker, misma origin HTTPS, DB no expuesta, CA PVE y claves montadas; adaptar `dockerfile`/DOCKER.md sin defaults demo. Dep.: T126.
- [X] T128 [US8] Ejecutar pip-audit/npm audit y contrastar advisories aplicables; corregir/pinear o mitigar con evidencia en `backend/requirements.lock`, `frontend/package-lock.json` y `docs/evidencia/009/dependencias.md`, reprobando flujos afectados. Dep.: T127.
- [X] T129 [US8] Crear `infra/backup/README.md` y `docs/operacion-respaldos.md` con copia diaria cifrada externa (siete diarias/cuatro semanales), roles/configuración/keyring, corte consistente MariaDB/archivos/APP_KEY y responsables/destino; no crear módulo NAP de respaldos. Dep.: T128.
- [X] T130 [US8] Crear `backend/scripts/preparar_restauracion.py` y procedimiento de reconciliación que invalide credenciales efímeras del corte, preserve MFA y cancele secretos/outbox antiguos antes de habilitar acceso o workers; exigir ensayo separado y no recrear cuentas. Dep.: T129.
- [ ] T131 [US8] Ejecutar copia/restauración separada de portal+keyring, PostgreSQL con dato y BookStack con libro/imagen/adjunto/cuentas/permisos; comparar corte, probar acceso y medir RTO/RPO observado en `docs/evidencia/009/restauracion.md`. Dep.: T130.
- [X] T132 [US8] Actualizar `docs/paper.md`, `docs/diagrama_bd.md` y `docs/nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md`; crear `docs/manual-docente.md` y `docs/manual-administrador.md` con entregado/limitaciones/responsables, autenticación opcional y recorrido sin ayuda del desarrollador. Dep.: T131.
- [ ] T133 [US8] Ejecutar desde otra computadora el recorrido real de ambos roles, consola propia, SMTP y aplicaciones con infraestructura; enlazar evidencia por SC-001–SC-017 y objetivos del informe en `docs/evidencia/009/aceptacion.md`, dejando faltantes como pendientes reales. Dep.: T132.

**Checkpoint**: comprobar US8 con sus recursos/fixtures preparados y registrar el resultado; conservar pendientes las comprobaciones externas no ejecutadas.

## Fase 11 — Cierre y comprobaciones transversales

**Objetivo**: Cerrar regresiones y consistencia de documentación sin ampliar alcance.

**Prueba independiente**: Todos los criterios disponen de resultado verificable; implementación y entorno coinciden con los contratos vigentes.

**Prerrequisito**: ocho historias comprobadas, incluida evidencia real aplicable; no reemplazar faltantes por simulaciones.

- [X] T134 Ejecutar suites completas backend/PostgreSQL/frontend, job de contratos y explícitamente infra/runner/tests, infra/services/tests e infra/laboratorio/tests con configuración infra/pytest.ini y recolección no vacía de las tres; ejecutar quickstart y SC-008 en navegador. Corregir expectativa obsoleta de test_escenario_5_abm_templates_y_limite_constitucional en `backend/tests/test_quickstart_e2e.py`, conservando discos grandes aceptados por test_templates_admin.py/test_templates_edicion.py; sin reintroducir tope.
- [X] T135 Contrastar API/schema/UI finales con `specs/009-remediar-hallazgos-cierre/contracts/operations.md`, auth.md, catalog-ui.md, guest-runner.md, console-access.md, evidence.md, evidence.schema.json y service-definition.schema.json; actualizar ejemplos/quickstart compatibles, validar schemas Draft2020-12 y trazabilidad sin marcar simulación como prueba real. Dep.: T134.
- [X] T136 Completar `docs/evidencia/009/matriz-trazabilidad.md` con FR-001–FR-073, SC-001–SC-017, A01–A16, UI/datos/entregables, prueba/resultado y limitaciones; no declarar aceptada una integración sin evidencia. Dep.: T135.
- [X] T137 Revisar con guía ajena al desarrollo `docs/manual-docente.md`, `docs/manual-administrador.md`, `DOCKER.md` y `docs/operacion-respaldos.md`; comprobar enlaces, inventario, claves sin valores y trabajo de infraestructura diferenciado. Dep.: T136.
- [X] T138 Registrar estado final de cada historia y evidencia en `docs/evidencia/009/cierre.md` y `specs/009-remediar-hallazgos-cierre/tasks.md`; marcar solo trabajo completado, conservando tareas de entorno pendientes si faltan accesos externos. Dep.: T137.

**Checkpoint**: matriz de aceptación y entrega consistente, con estado verdadero de cada tarea.

## Dependencias y orden de ejecución

El grafo principal de integración es el siguiente; los números se refieren a fases, no a nuevas ramas o agentes:

~~~text
Preparación (1) → Fundamentos (2) → US1 (3) → US2 (4) → US3 (5) → US4 (6)
                                                              │
                                                              ├→ US5 (7) → US6 (8)
                                                              └→ US7 (9), integrar salud real después de US6
US1 + US2 + US3 + US4 + US5 + US6 + US7 → US8 (10) → Cierre (11)
~~~

| Bloque | Dependencia efectiva | Qué puede validarse por separado |
|---|---|---|
| US1 | Fundamentos; autenticación actual como fixture hasta cambio de US2 | Pertenencia, rol y ausencia de efectos ajenos. |
| US2 | Fundamentos + guards US1 | Cuatro etapas, códigos, rate limit, administración y bienvenida con SMTP doble. |
| US3 | US1–US2 y helpers comunes de vigencia | Admisión/ledger con ejecutor doble; su despacho duradero se integra con US4. |
| US4 | Admisión US3 + outbox US2 | UPID/identidad/reinicio mediante dobles; preparación de producto usa adaptador doble hasta US6, sin fallback exitoso ficticio en operación. |
| US5 | US3–US4 | Fechas, calendario y receso con servicio/dato de prueba; no depende de instalar BookStack. |
| US6 | US4–US5; cifrado/sesión US2 | Catálogo/runner/recetas con dobles antes de habilitación real de T101, T102. |
| US7 | US2–US4; consumir vigencias US5 y probes reales US6 al integrar | Deltas, alertas, agregados y componentes con fixtures. Se pueden preparar las pruebas T103, T104, T105, T106 tras US4, sin adelantar cambios a archivos compartidos. |
| US8 | Todas las historias para aceptación final | Pruebas T120, T121, T122 y documentación de entorno pueden prepararse antes; ejecutar backfill/constraints/restore con los modelos definitivos. |

La cadena de revisiones prevista es T013, la revisión de acceso/consola de T026, T033, T040, T107 y T126. Revisar el head real al crear cada una. No cerrar constraints finales antes de regularizar datos ni mantener dos contadores de capacidad mutables.

Las tablas y helpers fundacionales permiten pruebas independientes; ninguna prueba con fixtures sustituye la aceptación completa del flujo. Por los archivos compartidos de esta remediación, no se promete implementación simultánea de todas las historias.

## Ejemplos de trabajo paralelo por historia

| Historia | Tareas listas en paralelo tras el prerrequisito | Archivos distintos y límite |
|---|---|---|
| US1 | T020 + T021 + T022 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US2 | T030 + T031 + T032 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US3 | T047 + T048 + T049 + T050 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US4 | T059 + T060 + T061 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US5 | T071 + T072 + T073 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US6 | T084 + T085 + T086 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US7 | T103 + T104 + T105 + T106 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |
| US8 | T120 + T121 + T122 | Pruebas de contrato/escenarios en los archivos de esas tareas; esperar sus casos antes de implementar. |

Otros conjuntos: T002, T003, T004 después de T001; T008, T009, T010 tras fase 1; T090, T091, T092 después de T089. Son 35 tareas con marca [P]. Integrar resultados antes de tocar migraciones, registros de modelos, routers comunes, api.js o App.jsx.

Ejemplo ejecutable de planificación US6: completar T089, preparar las recetas T090, T091, T092 en sus carpetas separadas y después continuar con T093. No instalar tres recetas sobre el mismo contenedor de prueba.

## Estrategia de implementación

1. Completar preparación y fundamentos. Mantener fuera de los commits datos/secretos de prueba y respetar cambios ajenos existentes.
2. **MVP para revisión: US1** (T020–T029). Demostrar aislamiento con tres cátedras y solicitudes directas; no equivale al cierre de la entrega.
3. Completar US2–US4 como primer bloque de seguridad/capacidad/recuperación y validar conjuntamente carreras, cookies y efectos de PVE. Continuar US5 sin esperar las imágenes reales.
4. Preparar/publicar las referencias US6 con infraestructura; avanzar pruebas/lógica de observación US7 mientras se obtiene el entorno, evitando conflictos de archivos.
5. Completar US8 y cierre con restauración, evidencia desde otra computadora y manuales. Marcar tareas solo después de ejecutar su comprobación; los ocho grupos son obligatorios.

## Cobertura de aceptación

| Criterio | Tareas que lo prueban o registran |
|---|---|
| SC-001 | T020, T022, T026, T027, T029, T102 |
| SC-002 | T030, T032, T046 |
| SC-003 | T048, T058 |
| SC-004 | T060, T070 |
| SC-005 | T102 |
| SC-006 | T071, T083 |
| SC-007 | T119 |
| SC-008 | T117, T118, T119 |
| SC-009 | T104, T110, T119 |
| SC-010 | T003, T106, T119 |
| SC-011 | T105, T119, T120, T121, T131 |
| SC-012 | T132, T133 |
| SC-013 | T102 |
| SC-014 | T071, T083 |
| SC-015 | T031, T032, T036, T046 |
| SC-016 | T072, T083 |
| SC-017 | T102 |

## Trazabilidad de requisitos

Las siguientes referencias apuntan a tareas con comportamiento o evidencia concreta; el grupo de historia complementa los contratos. La tabla evita perder requisitos transversales al descomponer por usuario.

| Requisito | Tareas |
|---|---|
| FR-001 | T020, T021, T022, T023, T024, T025, T026, T027, T029, T112 |
| FR-002 | T020, T021, T022, T023, T024, T025, T026, T029 |
| FR-003 | T021, T022, T023, T025, T026, T028, T029 |
| FR-004 | T030, T032, T033, T034, T036, T037, T044, T046, T121 |
| FR-005 | T030, T032, T033, T034, T037, T043, T044, T046 |
| FR-006 | T030, T031, T033, T034, T036, T037, T046 |
| FR-007 | T031, T033, T035, T037, T046 |
| FR-008 | T039, T040, T041, T042, T046, T122, T127, T130 |
| FR-009 | T031, T033, T038, T046 |
| FR-010 | T019, T021, T028, T047, T048, T053, T055, T058 |
| FR-011 | T011, T047, T052, T057, T058, T067, T126 |
| FR-012 | T009, T016, T048, T053, T055, T056, T058, T061 |
| FR-013 | T047, T051, T052, T055, T058 |
| FR-014 | T047, T049, T054, T058, T065, T085, T093, T094 |
| FR-015 | T048, T049, T054, T055, T058, T081 |
| FR-016 | T050, T057, T058 |
| FR-017 | T015, T053, T056, T058, T068, T125 |
| FR-018 | T056, T072, T076, T077, T082, T083 |
| FR-019 | T059, T060, T062, T064, T066, T068, T069, T070, T077, T094, T095, T097, T109 |
| FR-020 | T057, T059, T060, T061, T062, T063, T064, T065, T066, T067, T068, T069, T070, T085, T093, T094 |
| FR-021 | T011, T060, T061, T062, T063, T065, T066, T067, T070, T085, T093, T095 |
| FR-022 | T009, T011, T012, T016, T019, T028, T057, T059, T061, T062, T063, T067, T068, T070, T097 |
| FR-023 | T071, T073, T080, T083 |
| FR-024 | T071, T073, T075, T078, T080, T083, T088 |
| FR-025 | T071, T073, T075, T080, T083 |
| FR-026 | T049, T054, T073, T081, T083 |
| FR-027 | T008, T014, T071, T073, T078, T080, T081, T083 |
| FR-028 | T012, T076, T078, T082, T083, T084, T087, T088, T096, T098, T102, T124 |
| FR-029 | T106, T114, T119 |
| FR-030 | T015, T071, T074, T075, T079, T081, T082, T083, T125 |
| FR-031 | T008, T015, T071, T074, T075, T080, T083, T125 |
| FR-032 | T072, T076, T077, T082, T083, T109 |
| FR-033 | T066, T078, T084, T088 |
| FR-034 | T066, T070, T078, T084, T088, T090, T101, T102 |
| FR-035 | T010, T018, T086, T090, T091, T092, T095, T096, T097, T099, T102 |
| FR-036 | T017, T024, T040, T041, T085, T086, T095, T096, T097, T099, T102, T126 |
| FR-037 | T010, T018, T084, T087, T089, T098, T100 |
| FR-038 | T089, T091, T092, T095, T100, T101, T102 |
| FR-039 | T104, T107, T110, T112, T113, T114, T119 |
| FR-040 | T040, T041, T104, T109, T110, T112, T114, T119 |
| FR-041 | T015, T071, T074, T075, T077, T079, T082, T083 |
| FR-042 | T103, T107, T108, T109, T113, T119 |
| FR-043 | T103, T105, T107, T108, T111, T112, T114, T116, T119 |
| FR-044 | T069, T106, T114, T119 |
| FR-045 | T106, T115, T119 |
| FR-046 | T030, T032, T034, T037, T043, T044 |
| FR-047 | T069, T099, T106, T114, T115, T119 |
| FR-048 | T041, T063, T064, T068, T070, T094, T108, T112, T113, T116, T117, T118, T119, T127 |
| FR-049 | T103, T107, T108, T112, T113, T116, T117, T119 |
| FR-050 | T019, T105, T107, T111, T113, T117, T119, T124 |
| FR-051 | T042, T043, T122, T123, T127, T133, T137 |
| FR-052 | T010, T017, T018, T022, T024, T026, T027, T051, T085, T090, T093, T094, T096, T101, T122, T123, T127, T133 |
| FR-053 | T008, T010, T011, T012, T013, T014, T033, T040, T107, T120, T123, T124, T125, T126 |
| FR-054 | T001, T006, T013, T042, T120, T122, T123, T124, T125, T126, T127, T134 |
| FR-055 | T121, T129, T130, T131, T137 |
| FR-056 | T002, T128 |
| FR-057 | T003, T004, T005, T007, T009, T010, T045, T048, T060, T128, T133, T134, T135 |
| FR-058 | T001, T007, T029, T046, T058, T070, T101, T102, T119, T131, T133, T134, T135, T136, T138 |
| FR-059 | T132, T133, T135, T136, T137, T138 |
| FR-060 | T129, T132, T133, T136, T137, T138 |
| FR-061 | T011, T084, T087, T088, T089, T098, T100, T101 |
| FR-062 | T085, T089, T090, T091, T092, T093, T095, T098, T100, T101, T102 |
| FR-063 | T085, T086, T089, T090, T091, T092, T093, T095, T096, T101, T102 |
| FR-064 | T011, T071, T074, T079, T083 |
| FR-065 | T012, T071, T075, T076, T083, T084, T087, T098 |
| FR-066 | T050, T055, T058, T071, T075, T083 |
| FR-067 | T087, T098, T100, T102 |
| FR-068 | T015, T050, T071, T075, T082, T083 |
| FR-069 | T017, T031, T032, T033, T036, T037, T044, T046 |
| FR-070 | T031, T032, T033, T036, T037, T039, T044, T046, T121, T130 |
| FR-071 | T030, T031, T032, T036, T037, T044, T046 |
| FR-072 | T072, T076, T077, T082, T083 |
| FR-073 | T086, T092, T099, T100, T102 |

## Resumen y validación de generación

| Fase | Cantidad |
|---|---|
| Preparación | 7 |
| Fundamentos | 12 |
| US1 | 10 |
| US2 | 17 |
| US3 | 12 |
| US4 | 12 |
| US5 | 13 |
| US6 | 19 |
| US7 | 17 |
| US8 | 14 |
| Cierre | 5 |
| **Total** | **138** |

Formato previsto: 138 tareas pendientes, IDs T001–T138 únicos/consecutivos, 114 tareas con etiqueta US1–US8 y 24 compartidas; 35 marcas [P]. Cobertura: 73/73 FR y 17/17 SC. Las comprobaciones de formato/dependencias se ejecutan al generar este archivo; no acreditan código implementado.

Hooks previos y posteriores: .specify/extensions.yml ausente; no hay hooks que ejecutar. No se implementa aplicación, se despliega infraestructura ni se crean issues/commits con este comando.



## Phase 12: Convergence

Revisión del 2026-10-25 con `speckit-converge`. Alcance: 73 FR, 17 SC, 67 escenarios de aceptación, 12 decisiones técnicas y seis principios constitucionales. Se agregan únicamente las brechas detectadas; las tareas anteriores se conservan literalmente. Las comprobaciones institucionales ya abiertas (T102, T119, T131, T133) no se duplican ni se consideran aceptadas por pruebas locales. El objetivo es preparar una entrega configurable para conectar el clúster cuando esté disponible, conservando sus gates reales.

- [X] T139 CRITICAL [US1] Cerrar la habilitación de consola por existencia de archivo o evidencia genérica en `backend/app/routers/servicios.py:152` y `backend/app/services/verificacion_acceso_service.py:51`: retirar la dependencia de `/home/mauro/.../gate-revocacion-consola-t101.json`; exigir referencia institucional íntegra, real y aplicable a la instalación/clúster vigente, identidad nativa individual inventariada y alcance del servicio/cátedra, manteniendo bloqueo ante datos desconocidos o trámites pendientes. Añadir regresiones para archivo presente sin prueba válida, prueba de otra instalación/simulación, usuario sin identidad y servicio sin propiedad acreditada; no abrir consola por un flag. Reproducción aislada: actualmente devuelve URL a un usuario `sin_identidad` y servicio sin identidad infra porque existe el archivo del laboratorio. Fuente: Constitución I/IV y restricciones de seguridad; FR-001/FR-052; T026/T101 (contradicts).

- [X] T140 CRITICAL [US3] Retirar o convertir en una fachada segura `backend/app/services/pedido_service.py:274` (`cambiar_estado`): ninguna llamada interna debe aprobar sin admisión/evaluación/reserva ni permitir cancelación docente o estados operativos mediante flags de bypass; conservar el 405 del endpoint retirado. Añadir pruebas directas de capa de servicios con actor/pertenencia actuales, rechazo sin efectos de aprobación aislada y rutas nombradas que sí crean compromiso e historia indivisibles. Reproducción en SQLite en memoria: `cambiar_estado(..., "aprobado", admin)` termina APROBADO con cero filas en `compromisos_capacidad`. Fuente: Constitución IV y restricciones de seguridad; FR-001/FR-003/FR-010/FR-012; T025/T028/T053 (contradicts).

- [X] T141 CRITICAL [US4] Completar los ejecutores de la máquina de estados declarada en `backend/app/services/pedido_service.py:46` e integrarlos con confirmación/reconciliación de `backend/app/services/orquestacion_service.py:_confirmed`: una pausa automática confirmada debe reflejar SUSPENDIDO y la reactivación confirmada debe reflejar ACTIVO mediante `transicionar`, conservando autor/motivo/operación e idempotencia. Auditar también la transición declarada ERROR→RECHAZADO y proporcionar su resolución segura tras reconciliación, sin liberar un recurso incierto. Añadir regresiones de pausa fallida/tardía, reactivación, repetición y alcanzabilidad de las transiciones declaradas; no cambiar estado por la mera admisión 202. Reproducción aislada de pausa de sistema: servicio `paused` con pedido todavía `activo`. Fuente: Constitución II; FR-019/FR-020/FR-022; US4/AC1/AC2/AC6; T019/T066–T068 (partial).

- [X] T142 HIGH [US6] Cerrar la preparación cotidiana de red/TLS por instancia entre `backend/app/services/identidad_infra_service.py:61`, `preparacion_service.py`, `probes_servicio.py:35` e `infra/runner/node_executor.py:215`: el UUID se genera al reclamar, pero ambos perfiles exigen `instances[resource_uuid]` y certificados preparados para ese UUID. Implementar una asignación persistida/idempotente desde recursos de red/TLS previamente autorizados por infraestructura, coherente en portal y runner, para desplegar instancias nuevas sin editar código ni reconstruir manualmente los perfiles por cada despliegue; no introducir administración general de DNS/IPAM/CA fuera de alcance. Probar dos UUID nuevos por producto, independencia, agotamiento/falta de preparación y recuperación sin cambiar identidad/secretos; documentar el contrato de configuración que recibirá el clúster universitario. Las pruebas con dobles pueden cerrarse ahora; la aceptación desde red real sigue en T102/T133. Fuente: FR-061/FR-062/FR-063/FR-067; US6/AC8; SC-013; plan: preparación inicial frente a despliegue cotidiano; T094/T095/T100 (partial).

- [X] T143 HIGH [US7] Completar los avisos previos de vencimiento en `backend/app/services/vencimiento_service.py:42` mediante outbox transaccional de `notificacion_service.py` y presentación en el portal, con fecha/plazo efectivos, destinatarios vigentes y clave deduplicada por período. El job hoy añade historia y devuelve `avisados` sin crear avisos portal/email; la reproducción aislada obtuvo un servicio avisado y cero notificaciones. Añadir pruebas de siete días, período corto, evaluación repetida/concurrente, cambio de titular, SMTP fallido y visibilidad del resultado administrativo; un fallo de correo no revierte vigencia ni negocio. Fuente: FR-032/FR-040; US7/AC6; T077/T110 (partial).

- [X] T144 HIGH [US6] Sustituir o retirar de la ruta operativa `backend/scripts/publicar_catalogo.py`: eliminar resultados de ensayos predefinidos con `{check: True ...}` y entorno real fijo; consumir documentos de ensayo/registro explícitos con identidad, integridad, origen y operador contrastables, sin completar checks ausentes. Parametrizar configuración privada mediante el mecanismo existente, exigir verificación TLS y retirar rutas/UUID/DB del laboratorio; no seleccionar silenciosamente el primer administrador ni asignar/sobrescribir `identidad_consola` de `mauro_catedra` al publicar. Las identidades se inventarían mediante el importador institucional y su trámite de revocación. Probar ausencia/evidencia incompleta, otro clúster/digest, repetición sin mutar cuentas y ejecución parametrizada fuera de esta PC, sin PVE real. Fuente: FR-035/FR-051/FR-052/FR-058/FR-063; plan: evidencias reales y configuración externa; T087/T100/T101 (contradicts).

- [ ] T145 HIGH [US8] Corregir `docs/manual-administrador.md` y `docs/manual-docente.md` contra CLI/API/UI existentes, contrastándolos con `DOCKER.md`, `backend/app/config.py`, `backend/scripts/{bootstrap_admin,preflight,recuperar_2fa}.py` y contratos de la spec: documentar SECRET_KEYRING/SECRET_ACTIVE_KEY/CSRF_SECRET, opciones reales de los CLI, cookies/CSRF/Idempotency-Key, rutas de calendario/definiciones, pasos de login/onboarding y recuperación restringida con diez códigos. Retirar ENCRYPTION_KEY, `--modo`, `--json`, `--force-reset`, endpoints/roles/acciones no implementados y la promesa de SSH guest; describir la consola propia condicionada a su gate y el catálogo compatible/provisional. Verificar ejemplos sin mutaciones contra datos reales ni compartir secretos, y recorrer la guía con una persona ajena al desarrollo antes del cierre. Fuente: FR-004/FR-006/FR-051/FR-059/FR-067/FR-069/FR-070; US8/AC6; T132/T135/T137 (partial).

- [X] T146 MEDIUM [US8] Reconciliar `docs/evidencia/009/cierre.md`, `matriz-trazabilidad.md`, `preparacion-servicios.md`, `regresion-cierre.md`, `docs/operacion-respaldos.md` y enlaces de `DOCKER.md` con los archivos/resultados realmente disponibles: faltan los destinos `dependencias-seguridad.md`, `migracion-respaldo.md` y `rendimiento-api.json`; el acta cuenta 133 tareas y cinco pendientes aunque tasks.md tiene 134 originales marcadas y cuatro originales abiertas, y mezcla resultados de distintas ejecuciones de SC-008. Usar enlaces relativos portables, vincular evidencia existente o ejecutar/registrar la comprobación que falte y distinguir laboratorio local, simulación e integración universitaria. No inventar respaldos/restauraciones ni aceptar gates institucionales por ausencia de entorno; mantener T102/T119/T131/T133 como aceptación pendiente y actualizar los totales solo tras ejecutar las nuevas tareas. Fuente: FR-058/FR-059/FR-060; SC-011/SC-012; T136–T138 (partial).

Validación de esta revisión: backend con SQLite/dobles 666 aprobadas; PostgreSQL 16 aislado 99 aprobadas; infraestructura 130 aprobadas y cuatro omitidas optativas; Vitest 41 aprobadas; dos JSON Schemas y trece ejemplos válidos; lint sin errores y con ocho advertencias. Cuatro reproducciones adicionales en memoria confirmaron las brechas de aprobación aislada, consola sin identidad verificada, aviso sin outbox y pausa sin transición de pedido. No se ejecutó Proxmox/SMTP real ni se repitió la aceptación E2E/rendimiento externa. Esta sección no declara corregidas las brechas ni cerrada la entrega.

### Estado de ejecución de convergencia — 2026-10-25

T139–T144 y T146 implementadas y comprobadas mediante regresiones aisladas. T145 tiene manuales corregidos, CLI/contratos/enlaces contrastados y guía de conexión preparada; permanece abierta únicamente por el recorrido de una persona ajena al desarrollo, coordinable con T119. No se presenta una comprobación automatizada como esa lectura humana. Las tareas externas T102/T119/T131/T133 siguen abiertas por falta de aceptación sobre el entorno requerido. Ver [evidencia de convergencia](../../docs/evidencia/009/convergencia.md) y [contrato de conexión](../../docs/conexion-infraestructura.md).
