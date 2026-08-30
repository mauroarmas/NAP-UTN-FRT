---

description: "Task list for 004-unificar-usuario-catedra"
---

# Tasks: Unificación usuario–cátedra y control de recursos por aprobación

**Input**: Design documents from `/specs/004-unificar-usuario-catedra/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md)

**Tests**: **OBLIGATORIOS**, no opcionales. La constitución v2.0.0 exige pruebas automatizadas para
todo código que toque orquestación, máquina de estados o control de capacidad —lo que describe a
esta feature entera—, con al menos un camino de fallo de infraestructura simulado y un escenario de
concurrencia. Las tareas de prueba son compuertas, no adornos.

**Organization**: Agrupadas por historia de usuario para permitir implementación y validación
independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: A qué historia pertenece (US1–US6)
- Cada tarea incluye la ruta exacta del archivo

## Path Conventions

Aplicación web: `backend/app/`, `backend/tests/`, `frontend/src/`. Rutas relativas a la raíz del
repositorio, según la estructura fijada en [plan.md](./plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencias e infraestructura de pruebas que el resto necesita

- [X] T001 Agregar `APScheduler` a `backend/requirements.txt` (planificador de trabajos periódicos, decisión R1)
- [X] T002 [P] Actualizar `backend/tests/factories.py`: crear `Usuario` sin `catedra_id` y `Catedra` con `titular_id`
- [X] T003 [P] Agregar fixture `usuario_multicatedra` (dos cátedras propias más una ajena poblada) en `backend/tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Esquema, modelos y servicios compartidos. Toda historia los necesita.

**⚠️ CRITICAL**: Ninguna historia de usuario puede empezar hasta terminar esta fase.

### Modelos

- [X] T004 [P] Quitar `cuota_vcpus`, `cuota_ram_mb`, `cuota_storage_gb`; agregar `titular_id` y relación `titular` en `backend/app/models/catedra.py`
- [X] T005 [P] Quitar `catedra_id`; agregar relación `catedras` (uno a muchos) en `backend/app/models/usuario.py`
- [X] T006 [P] Agregar `tipo`, `servicio_id`, `reserva_vcpus`, `reserva_ram_mb`, `reserva_disk_gb`, `reserva_expira_at`, `justificacion_capacidad` a `Pedido`; volver `usuario_id` nullable en `PedidoHistorial`, ambos en `backend/app/models/pedido.py`
- [X] T007 [P] Agregar `vence_at`, `aviso_vencimiento_at`, `exento_pausado`, `pausa_programada_at`, `aviso_pausa_at`, `pausado_auto_at` en `backend/app/models/servicio.py`
- [X] T008 [P] Crear modelo `ServicioHistorial` (de solo agregado, `usuario_id` nullable) en `backend/app/models/servicio_historial.py`
- [X] T009 [P] Crear modelo `JobLock` en `backend/app/models/job_lock.py`
- [X] T010 [P] Crear modelo `MigracionAccesoPerdido` en `backend/app/models/migracion.py`
- [X] T011 [P] Agregar `justificacion_disco` (text nullable) al modelo `RecursoTemplate` en `backend/app/models/recurso_template.py`
- [X] T012 Registrar los modelos nuevos en `backend/app/models/__init__.py` (depende de T008, T009, T010)

### Migraciones

- [X] T013 Migración 1 `titular_catedra`: agrega `catedras.titular_id`, lo puebla con el menor `usuarios.id` asignado, crea y llena `migracion_004_accesos_perdidos`, en `backend/alembic/versions/`
- [X] T014 Migración 2 `capacidad_y_vencimiento`: columnas nuevas de `pedidos` y `servicios`, `recurso_templates.justificacion_disco`, `pedidos_historial.usuario_id` nullable, tablas `servicios_historial` y `job_locks`, en `backend/alembic/versions/`
- [X] T015 Migración 3 `quitar_cuotas`: elimina las tres columnas de cuota y cambia la unicidad de `catedras.nombre` a `(titular_id, nombre)`, en `backend/alembic/versions/`
- [X] T016 Migración 4 `quitar_usuario_catedra`: elimina `usuarios.catedra_id`, en `backend/alembic/versions/`
- [X] T017 Prueba de la migración de titularidad: elección determinista y bitácora de desplazados, en `backend/tests/test_migracion_titular.py`

### Servicios compartidos

- [X] T018 Crear `catedras_visibles(db, usuario)` y `requiere_acceso_catedra(db, usuario, catedra_id)` en `backend/app/services/acceso_service.py`
- [X] T019 [P] Crear ayudantes de historial con autor sistema (`usuario_id = NULL`) para pedidos y servicios en `backend/app/services/historial_service.py`
- [X] T020 Crear el planificador `AsyncIOScheduler` y el ayudante de toma/liberación de `JobLock` en `backend/app/services/scheduler.py` (depende de T009)
- [X] T021 Crear el router `POST /admin/jobs/{nombre}` (admin-only, 409 si el lock está tomado) en `backend/app/routers/admin_jobs.py`
- [X] T022 Arrancar y detener el planificador en el `lifespan`, y registrar el router nuevo, en `backend/app/main.py` (depende de T020, T021)

### Límite de disco por contenedor (Principio IV)

> Hasta ahora el disco quedaba acotado **de hecho** por `cuota_storage_gb` (valor por defecto 8). Al
> eliminar las cuotas desaparece esa protección accidental y el tope constitucional queda sin nada
> que lo haga cumplir. Estas tres tareas lo convierten en una regla explícita.

- [X] T023 Implementar `validar_disco_template(template)`: rechaza `default_disk_gb > 8` salvo que el template tenga `justificacion_disco` registrada, en `backend/app/services/limites_service.py`
- [X] T024 Aplicar la validación al alta y edición de templates, y exponer `justificacion_disco` en el schema, en `backend/app/routers/templates.py` y `backend/app/schemas/template.py` (depende de T023)
- [X] T025 Prueba del tope: 8 GB pasa, 16 GB sin justificación falla, 16 GB con justificación registrada pasa y la justificación queda consultable, en `backend/tests/test_limite_disco.py`

**Checkpoint**: Esquema migrado y servicios compartidos disponibles. Las historias pueden empezar.

---

## Phase 3: User Story 1 - Una sola cuenta para todas mis cátedras (Priority: P1) 🎯 MVP

**Goal**: Una persona opera todas sus cátedras desde una sesión, sin ver nada ajeno.

**Independent Test**: Con un usuario de dos cátedras y una tercera ajena poblada, iniciar sesión una
vez y comprobar que ve las dos propias correctamente rotuladas y ninguna de la tercera.

### Tests for User Story 1 ⚠️ (compuerta constitucional)

- [X] T026 [P] [US1] Prueba de regresión de aislamiento que recorre **todos** los endpoints de listado (pedidos, servicios, métricas, cátedras) con un usuario de dos cátedras, en `backend/tests/test_aislamiento_multicatedra.py`

### Implementation for User Story 1

- [X] T027 [US1] Reemplazar el filtro `== current_user.catedra_id` por `in_(catedras_visibles(...))` en las consultas de listado y la verificación de detalle de `backend/app/routers/pedidos.py`
- [X] T028 [P] [US1] Ídem en `backend/app/routers/servicios.py`
- [X] T029 [P] [US1] Ídem en las dos verificaciones de `backend/app/routers/metricas.py`
- [X] T030 [P] [US1] Actualizar `requiere_propio_o_admin` para aceptar el conjunto de cátedras en `backend/app/services/orquestacion_service.py`
- [X] T031 [US1] Reemplazar `GET /catedras/mi-catedra` por `GET /catedras/mias` (devuelve la lista) en `backend/app/routers/catedras.py`
- [X] T032 [P] [US1] Agregar la cátedra anidada (`id`, `nombre`) a las respuestas de pedido y servicio en `backend/app/schemas/pedido.py` y `backend/app/schemas/servicio.py`
- [X] T033 [US1] Reemplazar la llamada a `mi-catedra` por `getCatedrasMias` y agregar los endpoints nuevos en `frontend/src/services/api.js`
- [X] T034 [US1] Agregar el estado de cátedra activa (con opción "todas") al contexto de sesión y su selector, **oculto cuando la persona tiene una sola cátedra**, en `frontend/src/components/Sidebar.jsx`
- [X] T035 [US1] Rotular cada fila con su cátedra en `frontend/src/pages/Pedidos.jsx` y `frontend/src/pages/Servicios.jsx`
- [X] T036 [US1] Mostrar el mensaje de "sin cátedras asignadas" en lugar de pantallas vacías en `frontend/src/components/PanelCatedra.jsx`
- [X] T037 [US1] Reemplazar el indicador de consumo contra cuota (`cuotaItems`, que lee `catedra.cuota_*` y quedaría en `undefined`) por el consumo vigente de los servicios, sin denominador ni barra de porcentaje, en `frontend/src/components/PanelCatedra.jsx` (depende de T036)

**Checkpoint**: US1 funcional y verificable de forma independiente.

---

## Phase 4: User Story 2 - Pedir un servicio sin toparse con una cuota (Priority: P1)

**Goal**: Los pedidos se registran siempre; ninguno se rechaza por consumo acumulado.

**Independent Test**: Con una cátedra que bajo el modelo viejo habría excedido cualquier cuota,
crear un pedido y verificar que queda en `solicitado` y llega a la bandeja del administrador.

### Tests for User Story 2 ⚠️

- [X] T038 [P] [US2] Prueba de que crear un pedido con consumo acumulado alto no devuelve 409, y de que a nombre de una cátedra ajena devuelve 403, en `backend/tests/test_pedido_sin_cuota.py`

### Implementation for User Story 2

- [X] T039 [US2] Eliminar `verificar_cuota` y su llamada desde `crear_pedido` en `backend/app/services/pedido_service.py`
- [X] T040 [US2] Aceptar `catedra_id` explícito en `crear_pedido`, validado contra `catedras_visibles`, en `backend/app/services/pedido_service.py` (depende de T039)
- [X] T041 [US2] Agregar `catedra_id` a `PedidoCreate` y propagarlo en `backend/app/schemas/pedido.py` y `backend/app/routers/pedidos.py`
- [X] T042 [US2] Agregar el selector de cátedra al formulario de pedido, omitido cuando la persona tiene una sola, en `frontend/src/pages/Pedidos.jsx`
- [X] T043 [US2] Reescribir la prueba para verificar contra capacidad en vez de cuota, incluyendo que el consumo histórico de una cátedra sigue siendo reconstruible tras dar de baja servicios, en `backend/tests/test_soft_delete_cuota.py`

**Checkpoint**: US1 y US2 funcionan de forma independiente.

---

## Phase 5: User Story 3 - Aprobar es comprometer capacidad, no opinar (Priority: P1)

**Goal**: Aprobar reserva capacidad en el acto, de modo que dos aprobaciones consecutivas no puedan
comprometer la misma capacidad dos veces.

**Independent Test**: Con capacidad para un solo pedido y dos pendientes, aprobar el primero y
comprobar que la evaluación del segundo ya descuenta el compromiso, sin haber desplegado nada.

### Tests for User Story 3 ⚠️ (compuerta constitucional — incluye concurrencia)

- [X] T044 [P] [US3] Prueba de que la capacidad comprometida incluye las reservas vigentes y de que "RAM en riesgo" suma los pausados, en `backend/tests/test_capacidad_reserva.py`
- [X] T045 [P] [US3] Prueba de concurrencia: dos aprobaciones simultáneas sobre la misma capacidad libre no pueden comprometerla dos veces, en `backend/tests/test_capacidad_concurrencia.py`
- [X] T046 [P] [US3] Prueba de que confirmar con `capacidad_token` desactualizado devuelve 409 con los números nuevos y no aprueba, en `backend/tests/test_capacidad_token.py`
- [X] T047 [P] [US3] Prueba de que la reserva vencida libera capacidad y registra la transición con autor sistema, y de que un despliegue que falla por falta de capacidad real deja el pedido en estado explícito y reintentable, en `backend/tests/test_reserva_expiracion.py`

### Implementation for User Story 3

- [X] T048 [US3] Crear el cálculo de capacidad (física, desplegado, reservado, comprometido, libre, RAM en riesgo), el `capacidad_token` y el ayudante `bloqueo_capacidad` con advisory lock en PostgreSQL y no-op en SQLite, en `backend/app/services/capacidad_service.py`
- [X] T049 [US3] Agregar la transición `APROBADO → RECHAZADO` a `TRANSICIONES_VALIDAS` y a `TRANSICIONES_SISTEMA`, con su ejecutor real, en `backend/app/services/pedido_service.py` — **hoy no existe y sin ella la expiración de reservas viola el Principio II**
- [X] T050 [US3] Implementar `aprobar_pedido` con verificación y reserva dentro de una sola transacción bajo bloqueo, fijando `reserva_*` y `reserva_expira_at`, en `backend/app/services/pedido_service.py` (depende de T048, T049)
- [X] T051 [US3] Implementar `rechazar_pedido` con motivo obligatorio en `backend/app/services/pedido_service.py`
- [X] T052 [US3] Implementar el trabajo `expirar_reservas` que libera reservas vencidas y registra la transición con autor sistema, en `backend/app/services/capacidad_service.py` (depende de T049, T019)
- [X] T053 [US3] Crear `GET /capacidad` (admin-only, 502 si Proxmox no responde) en `backend/app/routers/capacidad.py`
- [X] T054 [US3] Agregar `GET /pedidos/{id}/evaluacion`, `POST /pedidos/{id}/aprobar` y `POST /pedidos/{id}/rechazar` en `backend/app/routers/pedidos.py` (depende de T050, T051)
- [X] T055 [US3] Registrar el trabajo `expirar_reservas` en el planificador y en `admin_jobs` (depende de T052, T020, T021)
- [X] T056 [US3] Crear el panel con los números de capacidad y el resultado proyectado en `frontend/src/components/PanelCapacidad.jsx`
- [X] T057 [US3] Integrar la pantalla de aprobación: envío del token, reconfirmación ante 409 y campo de justificación cuando excede, en `frontend/src/pages/Pedidos.jsx` (depende de T056)

**Checkpoint**: Las tres historias P1 completas. Es el corte natural de MVP.

---

## Phase 6: User Story 6 - Cada servicio tiene fecha de fin, y renovarlo es pedirlo de nuevo (Priority: P2)

**Goal**: Vencimiento visible desde el primer día, con renovación por el mismo circuito de
aprobación y sin recrear el servicio.

**Independent Test**: Aprobar un pedido, verificar que el servicio nace con `vence_at` visible;
adelantar la fecha, comprobar el aviso, renovar y verificar que el servicio conserva su id y datos.

### Tests for User Story 6 ⚠️

- [X] T058 [P] [US6] Prueba de que la renovación aprobada conserva id y datos del servicio y solo corre `vence_at`, de que no reserva capacidad nueva, y de que vencer un servicio **ya pausado** no vuelve a contabilizar la capacidad que la pausa liberó, en `backend/tests/test_vencimiento_renovacion.py`
- [X] T059 [P] [US6] Prueba de que un servicio con renovación pendiente no se apaga al llegar el vencimiento, en `backend/tests/test_vencimiento_renovacion_pendiente.py`

### Implementation for User Story 6

- [X] T060 [US6] Implementar el trabajo `aplicar_vencimientos` (libera cómputo y memoria, respeta renovaciones pendientes, no destruye datos, registra con autor sistema) y hacer que sobre un servicio ya pausado solo marque el vencimiento sin volver a descontar capacidad, en `backend/app/services/vencimiento_service.py`
- [X] T061 [US6] Seleccionar el ejecutor de `EN_DESPLIEGUE → ACTIVO` según `Pedido.tipo`: alta despliega, renovación solo corre `vence_at`, en `backend/app/services/orquestacion_service.py`
- [X] T062 [US6] Agregar `POST /servicios/{id}/renovar` (crea el pedido de renovación; 409 si ya hay una pendiente) en `backend/app/routers/servicios.py`
- [X] T063 [US6] Permitir al administrador ajustar `vence_at` vía `PATCH /servicios/{id}` en `backend/app/routers/servicios.py`
- [X] T064 [US6] Fijar `vence_at` al desplegar, con el valor por defecto propuesto y ajustable al aprobar, en `backend/app/services/orquestacion_service.py` (depende de T061)
- [X] T065 [US6] Registrar el trabajo `aplicar_vencimientos` en el planificador y en `admin_jobs` (depende de T060)
- [X] T066 [US6] Mostrar el vencimiento y el aviso previo, y agregar la acción de renovar, en `frontend/src/pages/Servicios.jsx` y `frontend/src/components/PanelCatedra.jsx`

**Checkpoint**: La vía garantizada de recuperación de capacidad está operativa.

---

## Phase 7: User Story 5 - El administrador gestiona las cátedras de cada persona (Priority: P2)

**Goal**: Alta de usuario con sus cátedras en una sola operación atómica, más reasignación y baja.

**Independent Test**: Crear un usuario con tres cátedras desde el buscador, verificar que las ve en
su sesión; reasignar una a otra persona y comprobar que los servicios siguen a la cátedra.

### Tests for User Story 5 ⚠️

- [X] T067 [P] [US5] Pruebas del alta: atomicidad ante cátedra tomada (409 y usuario no creado), rechazo con `catedra_ids` vacío, y resumen devuelto, en `backend/tests/test_alta_usuario_catedras.py`
- [X] T068 [P] [US5] Prueba de que desactivar un usuario con cátedras a cargo devuelve 409 con la lista, en `backend/tests/test_baja_usuario_con_catedras.py`

### Implementation for User Story 5

- [X] T069 [US5] Reemplazar `catedra_id` por `catedra_ids` y crear usuario más asignaciones en una sola transacción, con 409 detallado, en `backend/app/routers/usuarios.py` y `backend/app/schemas/usuario.py`
- [X] T070 [US5] Rechazar la desactivación de un usuario con cátedras a cargo hasta reasignarlas o darlas de baja, en `backend/app/routers/usuarios.py`
- [X] T071 [US5] Aceptar `titular_id` en `PATCH /catedras/{id}` y eliminar toda la validación de cuotas (`_cuotas_comprometidas`, `_validar_cuota_cubre_lo_usado`, `_validar_cuota_o_advertir`) en `backend/app/routers/catedras.py`
- [X] T072 [US5] Eliminar `cuota_vcpus`, `cuota_ram_mb` y `cuota_storage_gb` de `CatedraBase`, `CatedraUpdate` y `CatedraConUso`, y agregar el filtro `?sin_titular=true` más el titular anidado en las respuestas, en `backend/app/schemas/catedra.py` y `backend/app/routers/catedras.py`
- [X] T073 [US5] Exigir confirmación explícita, con el conteo de servicios afectados, para dar de baja una cátedra con servicios vigentes, en `backend/app/routers/catedras.py`
- [X] T074 [US5] Crear `GET /admin/migracion/accesos-perdidos` (admin-only) en `backend/app/routers/admin_jobs.py`
- [X] T075 [US5] Crear el componente de búsqueda con marcado múltiple, fichas removibles y filas deshabilitadas con su titular, en `frontend/src/components/SelectorCatedras.jsx`
- [X] T076 [US5] Integrar el selector en el alta y edición de usuario en `frontend/src/pages/Usuarios.jsx` (depende de T075)
- [X] T077 [US5] Quitar los campos de cuota y mostrar el titular en `frontend/src/pages/Catedras.jsx`

**Checkpoint**: La gestión de identidad del modelo nuevo es operable end-to-end.

---

## Phase 8: User Story 4 - Los servicios sin uso se pausan y liberan capacidad (Priority: P3)

**Goal**: Recuperación oportunista de capacidad, con aviso previo, período de gracia y reactivación
autónoma por la cátedra.

**Independent Test**: Con un servicio sin actividad durante la ventana, verificar que primero queda
avisado y programado, que la actividad cancela el aviso, y que vencida la gracia queda pausado con
el contenedor detenido.

### Tests for User Story 4 ⚠️ (incluye el caso que más importa)

- [X] T078 [P] [US4] Prueba de que sin cobertura suficiente de métricas **no se pausa ningún servicio**, en `backend/tests/test_inactividad_sin_metricas.py`
- [X] T079 [P] [US4] Pruebas del ciclo completo: aviso, cancelación por actividad, pausa vencida la gracia, exención por "siempre encendido", y que un servicio con una operación del portal en curso no se pausa, en `backend/tests/test_inactividad_pausado.py`
- [X] T080 [P] [US4] Prueba de que una reactivación sin capacidad deja el servicio en `paused` y nunca en error, en `backend/tests/test_reactivacion_sin_capacidad.py`

### Implementation for User Story 4

- [X] T081 [US4] Implementar la evaluación de inactividad con regla de cobertura mínima y umbral combinado de CPU y red, excluyendo los servicios con una operación del portal en curso (despliegue, reinicio, reactivación), en `backend/app/services/inactividad_service.py`
- [X] T082 [US4] Implementar la pausa (vía `stop_lxc`) y la reactivación, con registro en el historial y autor sistema, en `backend/app/services/inactividad_service.py` (depende de T081, T019)
- [X] T083 [US4] Respetar `pausado_auto_at` en `sincronizar_estados` para que el `stopped` de Proxmox no borre el estado `PAUSED` del portal, en `backend/app/services/orquestacion_service.py`
- [X] T084 [US4] Convertir la recolección de métricas en trabajo periódico reutilizando `capturar_todos_los_servicios`, en `backend/app/services/metricas_service.py`
- [X] T085 [US4] Agregar `POST /servicios/{id}/reactivar`, `PATCH` de `exento_pausado`, `GET /servicios/pausados` y `GET /servicios/exentos-inactivos` en `backend/app/routers/servicios.py`
- [X] T086 [US4] Registrar los trabajos `evaluar_inactividad` y `recolectar_metricas` en el planificador y en `admin_jobs` (depende de T081, T084)
- [X] T087 [US4] Mostrar el aviso de pausa programada, la advertencia de que los procesos no vuelven solos, el almacenamiento que el servicio sigue reteniendo, y las acciones de reactivar y marcar "siempre encendido", en `frontend/src/pages/Servicios.jsx`

**Checkpoint**: Las seis historias funcionan de forma independiente.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T088 [P] Eliminar las etiquetas y referencias a cuota que queden en `frontend/src/constants/estados.js` y unificar el rótulo de `paused` (hoy dice "Apagado" en un archivo y "Pausado" en otro)
- [X] T089 [P] Actualizar `backend/README.md` con el planificador, los trabajos periódicos y el modelo de capacidad
- [X] T090 Marcar como superadas las referencias a cuota en `specs/002-panel-catedra-simple/` y `specs/003-gestion-servicios-catedra/`
- [X] T091 Ejecutar la validación completa de [quickstart.md](./quickstart.md), con E4, E8, E9 y E10 como bloqueantes

  Ejecutada el 2026-08-29 contra Proxmox VE 9.2.2 y PostgreSQL 16 reales. Los diez
  escenarios y la sección 4 pasan; ver [quickstart.md](./quickstart.md#estado-de-la-validación).
  Encontró y corrigió un defecto que solo se manifiesta contra PostgreSQL: el enum
  `tipopedido` se creaba en minúscula y tumbaba `GET /capacidad` con un 502.
  El recorrido visual de E2 se ejecutó con Playwright sobre el frontend real: los cinco pasos pasan.
- [X] T092 Verificar que con más de un worker los trabajos periódicos no se ejecutan por duplicado

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup — **bloquea todas las historias**
- **User Stories (Phase 3–8)**: dependen de Foundational
- **Polish (Phase 9)**: depende de las historias que se quieran entregar

### User Story Dependencies

- **US1 (P1)**: solo depende de Foundational. Es la base del aislamiento que las demás asumen
- **US2 (P1)**: solo depende de Foundational. Independiente de US1
- **US3 (P1)**: solo depende de Foundational. **US2 y US3 se complementan** (US2 deja entrar los pedidos, US3 los resuelve), pero cada una es verificable por separado
- **US6 (P2)**: depende de Foundational; se apoya en el circuito de aprobación de US3 para la renovación. Sin US3, el vencimiento funciona pero la renovación no tiene dónde resolverse
- **US5 (P2)**: solo depende de Foundational. Totalmente independiente
- **US4 (P3)**: solo depende de Foundational. Independiente

### Within Each User Story

- Las pruebas se escriben **primero** y deben fallar antes de implementar
- Modelos → servicios → endpoints → frontend
- Historia completa antes de pasar a la siguiente prioridad

### Parallel Opportunities

- T002 y T003 en paralelo (Setup)
- T004 a T011 en paralelo (modelos, archivos distintos); T012 después
- T013 a T016 son secuenciales entre sí (cadena de revisiones de Alembic)
- El bloque de límite de disco (T023–T025) es independiente del resto de la Fase 2
- Todas las tareas de prueba de una misma historia, en paralelo
- T028, T029 y T030 en paralelo dentro de US1
- Terminada la Fase 2, US1, US2, US3, US4 y US5 pueden avanzar en paralelo con equipo suficiente

---

## Parallel Example: User Story 3

```bash
# Las cuatro pruebas de US3 juntas (archivos distintos):
Task: "Cálculo de capacidad con reservas en backend/tests/test_capacidad_reserva.py"
Task: "Concurrencia de aprobaciones en backend/tests/test_capacidad_concurrencia.py"
Task: "Token desactualizado devuelve 409 en backend/tests/test_capacidad_token.py"
Task: "Expiración de reserva libera capacidad en backend/tests/test_reserva_expiracion.py"
```

```bash
# Los modelos de la Fase 2 juntos:
Task: "Catedra sin cuotas con titular_id en backend/app/models/catedra.py"
Task: "Usuario sin catedra_id en backend/app/models/usuario.py"
Task: "Pedido con reserva y tipo en backend/app/models/pedido.py"
Task: "Servicio con vencimiento y pausa en backend/app/models/servicio.py"
Task: "RecursoTemplate con justificacion_disco en backend/app/models/recurso_template.py"
```

---

## Implementation Strategy

### MVP (las tres historias P1)

1. Fase 1: Setup
2. Fase 2: Foundational — **crítica, bloquea todo**
3. Fases 3, 4 y 5: US1, US2 y US3
4. **PARAR Y VALIDAR**: escenarios E1, E3, E4 y E10 de [quickstart.md](./quickstart.md)

Es el corte correcto de MVP porque entrega el modelo nuevo completo y coherente: identidad
unificada, pedidos sin techo y aprobación con reserva. Cortar antes de US3 dejaría el sistema **peor
que hoy** —sin cuota y sin control de capacidad—, así que US3 no es negociable dentro del MVP.

### Entrega incremental

1. Setup + Foundational → base lista
2. US1 → validar → desplegar
3. US2 + US3 → validar → desplegar (**MVP**)
4. US6 (vencimiento) → validar → desplegar
5. US5 (gestión de identidad) → validar → desplegar
6. US4 (pausado) → validar → desplegar

US6 va antes que US4 a propósito: es la vía determinista de recuperación de capacidad, mientras que
el pausado es heurística. Si el proyecto se quedara sin tiempo, es preferible tener el vencimiento
solo que el pausado solo.

### Equipo en paralelo

Terminada la Fase 2:

- Persona A: US1 y US3 (el núcleo de capacidad)
- Persona B: US2 y US5
- Persona C: US6 y US4

---

## Notes

- `[P]` = archivos distintos, sin dependencias pendientes
- Verificar que las pruebas fallan antes de implementar
- Confirmar cada tarea o grupo lógico por separado
- **T049 es fácil de pasar por alto**: la transición `APROBADO → RECHAZADO` no existe hoy en la tabla
  de transiciones. Sin ella, el trabajo de expiración de reservas no tiene forma legítima de cambiar
  el estado y el Principio II queda incumplido
- **T023–T025 no son opcionales**: el tope de 8 GB de disco es un MUST del Principio IV que hasta
  ahora se cumplía por accidente, porque la cuota por defecto era justamente 8 GB. Al quitar las
  cuotas, sin estas tareas el sistema queda sin ningún límite de disco
- **T078 es la prueba más importante de la feature**: un falso positivo del pausado apaga trabajo en
  uso, que es más caro que no pausar nunca nada
