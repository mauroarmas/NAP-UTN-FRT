---

description: "Task list for 005-revertir-aprobacion"
---

# Tasks: Revertir una aprobación antes del despliegue

**Input**: Design documents from `/specs/005-revertir-aprobacion/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: **OBLIGATORIOS**, no opcionales. La constitución v3.0.0 exige pruebas automatizadas para
todo código que toque máquina de estados o control de capacidad, con al menos un camino de fallo, y
—para el código que **decide** sobre capacidad— un escenario de concurrencia. Esta feature cae en las
dos categorías: revertir libera capacidad, o sea que decide sobre ella. Las tareas de prueba son
compuertas, no adornos.

**Organization**: Agrupadas por historia de usuario para permitir implementación y validación
independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: A qué historia pertenece (US1–US3)
- Cada tarea incluye la ruta exacta del archivo

## Path Conventions

Aplicación web: `backend/app/`, `backend/tests/`, `frontend/src/`. Rutas relativas a la raíz del
repositorio, según la estructura fijada en [plan.md](./plan.md).

> **Sin migraciones, sin estados nuevos, sin transiciones nuevas.** La reserva no es una tabla sino un
> estado derivado del pedido, y `APROBADO → RECHAZADO` ya es una transición válida. Si alguna tarea
> parece necesitar una migración o un estado `REVERTIDO`, es señal de que se desvió del diseño
> (ver [research.md](./research.md) R2 y R4).

---

## Phase 1: Setup

**Purpose**: No hay setup que hacer. La feature trabaja sobre archivos y dependencias que ya existen.

*(Fase vacía a propósito: no se agregan dependencias, ni carpetas, ni configuración. Se documenta
para dejar constancia de que se evaluó y no hizo falta.)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extraer la liberación de reserva para que exista **una sola definición** de qué
significa liberar, compartida por el vencimiento automático y la reversión humana.

**⚠️ CRITICAL**: T001–T002 bloquean la US1. Duplicar la lógica de liberación en la reversión crearía
dos definiciones que pueden divergir, y divergir acá significa capacidad fantasma (R2).

- [x] T001 Prueba de `liberar_reserva`: pone en cero `reserva_vcpus`, `reserva_ram_mb` y `reserva_disk_gb`, limpia `reserva_expira_at`, es idempotente sobre una reserva ya en cero (caso renovación, R7), y tras aplicarla el pedido deja de contar en `reservas_vigentes_where`, en `backend/tests/test_liberar_reserva.py`
- [x] T002 Extraer `liberar_reserva(pedido)` desde el cuerpo de `expirar_reservas` y hacer que ambos caminos la usen, en `backend/app/services/capacidad_service.py` (regla R2)

**Checkpoint**: Existe una única definición de "liberar una reserva". Recién ahora se puede construir
la reversión encima.

---

## Phase 3: User Story 1 - Deshacer una aprobación que comprometió de más (Priority: P1) 🎯 MVP

**Goal**: El administrador libera en el acto la capacidad de una aprobación equivocada, dejando el
motivo registrado.

**Independent Test**: Aprobar un pedido, verificar que la capacidad libre bajó, revertir con un
motivo, y comprobar que volvió al valor previo sin esperar ningún proceso automático.

### Tests for User Story 1 ⚠️ (compuerta constitucional)

- [x] T003 [P] [US1] Pruebas del camino feliz: revertir un pedido aprobado lo deja en `rechazado`, pone la reserva en cero, y la capacidad libre vuelve **exactamente** al valor previo a la aprobación (FR-001, FR-003, SC-002), en `backend/tests/test_reversion_aprobacion.py`
- [x] T004 [P] [US1] Pruebas del motivo obligatorio: sin `motivo` y con `motivo` en blanco devuelven 400, y en ambos casos el pedido **sigue aprobado** y la capacidad **sigue comprometida** (FR-002, P2), en `backend/tests/test_reversion_aprobacion.py`
- [x] T005 [P] [US1] Pruebas de los cuatro conflictos, cada uno con su código propio: `pedido_no_aprobado` desde `solicitado` (FR-007), `despliegue_en_curso` desde `en_despliegue`/`activo` (FR-006, R5), `reserva_ya_vencida` tras correr `expirar_reservas` (FR-014, R6), y 403 para el rol cátedra (FR-012), en `backend/tests/test_reversion_aprobacion.py`
- [x] T006 [P] [US1] Prueba de que revertir una renovación no toca el servicio renovado: conserva su `vence_at` y su estado (FR-013, R7, P5), en `backend/tests/test_reversion_aprobacion.py`
- [x] T007 [US1] **Prueba de concurrencia**: dos reversiones simultáneas sobre el mismo pedido; exactamente una devuelve 200 y la otra `ya_revertido`, y la capacidad libre sube **una sola vez** (FR-004, FR-005, SC-006, I1), en `backend/tests/test_reversion_concurrencia.py`
- [x] T008 [US1] **Prueba del camino de fallo**: si la operación falla después de liberar la reserva y antes de confirmar el cambio de estado, la transacción revierte entera — el pedido sigue en `aprobado` y la capacidad **sigue comprometida**, sin quedar nada a medias (FR-004, P3, I3), en `backend/tests/test_reversion_concurrencia.py`

### Implementation for User Story 1

- [x] T009 [US1] Crear el schema `PedidoRevertir` con `motivo` obligatorio y no vacío tras recortar espacios, en `backend/app/schemas/pedido.py`
- [x] T010 [US1] Agregar `capacidad_liberada` al schema de respuesta del detalle, opcional, para que la interfaz muestre cuánto volvió sin reconsultar, en `backend/app/schemas/pedido.py`
- [x] T011 [US1] Implementar `revertir_aprobacion(db, pedido_id, admin, motivo)` en `backend/app/services/pedido_service.py`: todo dentro de `bloqueo_capacidad`, releer el pedido bajo el lock, verificar que siga en `APROBADO`, llamar a `liberar_reserva` y transicionar con `cambiar_estado` con autor humano (depende de T002) — reglas P1, P3, R1, R3
- [x] T012 [US1] Distinguir los cuatro conflictos con el código y el mensaje que fija [contracts/api.md](./contracts/api.md), incluida la separación entre `reserva_ya_vencida` y `ya_revertido` mirando el autor de la última transición, en `backend/app/services/pedido_service.py` (depende de T011, regla R6)
- [x] T013 [US1] Completar `motivo_rechazo` con un texto que nombre la reversión —para que la cátedra no lea "rechazado" a secas— sin tocar `justificacion_capacidad`, que pertenece al registro de la aprobación que se deshace, en `backend/app/services/pedido_service.py` (depende de T011)
- [x] T014 [US1] Implementar `POST /pedidos/{pedido_id}/revertir-aprobacion` tras `require_admin`, siguiendo la forma de `aprobar` y `rechazar`, en `backend/app/routers/pedidos.py` (depende de T009, T011)
- [x] T015 [P] [US1] Agregar `revertirAprobacion(id, motivo)` al cliente de API en `frontend/src/services/api.js`
- [x] T016 [US1] Agregar la acción de revertir a la bandeja del administrador, visible **solo** sobre pedidos aprobados sin desplegar, con el motivo como campo obligatorio del diálogo, en `frontend/src/pages/Pedidos.jsx` (depende de T015)
- [x] T017 [US1] Mostrar la capacidad liberada al confirmar, y traducir los cuatro conflictos a su mensaje en lugar de volcar el error crudo, en `frontend/src/pages/Pedidos.jsx` (depende de T016)

**Checkpoint**: US1 entregable de forma independiente. Una aprobación equivocada deja de costar 24 h
de capacidad bloqueada para todo el clúster.

---

## Phase 4: User Story 2 - La cátedra entiende qué pasó con su pedido (Priority: P1)

**Goal**: La cátedra ve que su pedido volvió atrás, por qué, y que puede volver a pedirlo.

**Independent Test**: Con una cuenta de cátedra, mirar un pedido propio antes y después de que un
administrador revierta su aprobación, y comprobar que el cambio y su motivo son visibles y
comprensibles sin conocimientos técnicos.

### Tests for User Story 2

- [x] T018 [P] [US2] Prueba de que la cátedra ve el pedido revertido con su motivo, y que el motivo es el que escribió el administrador (FR-010), en `backend/tests/test_reversion_visible_catedra.py`
- [x] T019 [P] [US2] Prueba de que la cátedra puede crear un pedido nuevo por el mismo recurso tras la reversión, sin restricción ni demora (FR-011, P6), en `backend/tests/test_reversion_visible_catedra.py`

### Implementation for User Story 2

- [x] T020 [US2] Presentar el pedido revertido como tal —no como un rechazo a secas— en la vista de la cátedra, apoyándose en `motivo_rechazo` y en el historial, en `frontend/src/pages/Pedidos.jsx`
- [x] T021 [US2] Verificar que el texto que ve la cátedra es entendible sin formación técnica (Principio VI): sin códigos, sin nombres de estado crudos, y diciendo qué puede hacer a continuación, en `frontend/src/pages/Pedidos.jsx` (depende de T020)

**Checkpoint**: US2 entregable de forma independiente. Un pedido que deja de estar aprobado ya no es
indistinguible de una falla del portal.

---

## Phase 5: User Story 3 - La reversión no se confunde con nada más en la auditoría (Priority: P2)

**Goal**: El historial permite distinguir un rechazo original, una reversión humana y un vencimiento
automático.

**Independent Test**: Producir los tres casos sobre pedidos distintos y verificar que el historial
los distingue sin ambigüedad, incluyendo quién fue el autor de cada uno.

### Tests for User Story 3

- [x] T022 [P] [US3] Prueba de los tres casos juntos: el rechazo original tiene `estado_anterior` `solicitado`; la reversión, `aprobado` y autor persona; el vencimiento, `aprobado` y autor sistema (`usuario_id` nulo) — sin campos ni estados nuevos (FR-009, R4, SC-004), en `backend/tests/test_historial_reversion.py`
- [x] T023 [P] [US3] Prueba de que la entrada de la aprobación original **sobrevive** a la reversión, sin sobrescribirse, y que las dos leídas en orden cuentan la historia completa; y de que **el comentario de la entrada de la reversión contiene el motivo que escribió el administrador**, no un texto genérico (FR-008, H1, H3, I4), en `backend/tests/test_historial_reversion.py`

### Implementation for User Story 3

- [x] T024 [US3] Verificar que la entrada de historial de la reversión registra al administrador como autor y **nunca** al sistema, aunque la operación se parezca al vencimiento (H2, FR-008), en `backend/app/services/pedido_service.py`
- [x] T025 [US3] Mostrar el historial de forma que las tres situaciones se lean distinto, nombrando al sistema como autor donde corresponde, en `frontend/src/pages/Pedidos.jsx`

**Checkpoint**: Las tres historias funcionan de forma independiente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T026 [P] Verificar que `PATCH /pedidos/{id}/estado` **sigue rechazando** `aprobado → rechazado`: la reversión es una operación con nombre propio y esa puerta debe seguir cerrada (R1), en `backend/tests/test_reversion_aprobacion.py`
- [x] T027 [P] Actualizar `backend/README.md` con la reversión de aprobaciones y con la regla de que liberar una reserva tiene una sola definición compartida
- [x] T028 Anotar en `specs/004-unificar-usuario-catedra/quickstart.md` que el hueco detectado en su validación T091 —una aprobación sobrecomprometida que no se podía deshacer y bloqueaba a otras cátedras— quedó resuelto por esta feature
- [~] T029 Ejecutar la validación completa de [quickstart.md](./quickstart.md), con E1, E3, E4 y E8 como bloqueantes — **parcial**: E4 y E8 completos, E1 y E3 en su mitad verificable por API; E5, E7 y E10 exigen estados que no se pueden crear sin editar la base a mano ([resultados](./quickstart.md#resultado-de-la-validación-2026-08-30))

---

## Dependencies

```text
Phase 2 (T001-T002) ─── BLOQUEA ───▶ US1 (Phase 3)
  liberar_reserva                     la reversión la usa

US1 (Phase 3) ─── BLOQUEA ───▶ US2 (Phase 4)  y  US3 (Phase 5)
                                no hay qué mostrar sin la operación

Phase 6 ◀── requiere las tres historias
```

**Por qué acá US2 y US3 sí dependen de US1** (a diferencia de la feature 006, donde las historias eran
independientes): las dos describen **cómo se ve el resultado de revertir**. Sin la operación no hay
pedido revertido que mostrar ni entrada de historial que distinguir. La dependencia es real, no de
conveniencia.

**US2 y US3 son independientes entre sí**, aunque ambas tocan `Pedidos.jsx`: US2 trabaja la vista de
la cátedra y US3 la presentación del historial. Conviene no hacerlas en paralelo por dos personas
distintas para evitar conflictos en el archivo, pero no hay dependencia lógica.

## Parallel Execution

**Dentro de la Phase 2**: T001 se escribe primero y debe fallar antes de T002.

**Dentro de la US1**: T003 a T006 comparten archivo de pruebas → escribirlas de a una o coordinar.
T007 y T008 van en archivo propio, pero comparten ese archivo entre sí → escribirlas de a una;
paralelizables contra T003–T006. T015 es frontend puro → paralelo con cualquier tarea de backend.
T009 y T010 tocan el mismo schema; hacerlas juntas.

**Dentro de la US2 y la US3**: T018/T019 y T022/T023 son pruebas en archivos distintos entre historias
→ paralelizables entre sí.

**Entre historias**: US2 y US3 pueden avanzar a la vez una vez terminada la US1, con la salvedad del
archivo compartido en frontend.

## Implementation Strategy

**MVP sugerido**: **Phase 2 + User Story 1** (T001–T017, 17 tareas).

Es el corte que cierra el problema que originó la spec: el administrador recupera la capacidad de una
aprobación equivocada sin esperar 24 h, y deja de arrastrar a otras cátedras mientras tanto. Incluye
obligatoriamente la Phase 2, porque sin `liberar_reserva` compartida la reversión duplicaría la
definición de liberar.

**Entrega incremental**:

1. **Phase 2 + US1** → la aprobación deja de ser irreversible. Validar con E1, E2, E4, E5, E6, E7, E10 y E11.
2. **US2** → la cátedra deja de ver un cambio inexplicado. Validar con E8 y E9.
3. **US3** → la auditoría distingue las tres formas de llegar a rechazado. Validar con E3.
4. **Phase 6** → validación completa y documentación.

**Sobre el orden de las dos P1**: la US1 va primero porque la US2 no tiene nada que mostrar sin ella.
No es una preferencia sino una dependencia.

**Sobre T007 y T008**: son las dos tareas que cubren la compuerta de capacidad por sus dos lados —liberar dos veces (T007) y liberar a medias (T008)—. T007 es la única que puede dejar el sistema **peor** que antes. Una
capacidad libre inflada hace que el administrador apruebe sobre recursos inexistentes — el defecto
que la feature 004 vino a cerrar, entrando por una operación nueva. Conviene escribirla temprano y no
dejarla para el final del bloque de pruebas.

## Total

**29 tareas**: 0 de setup, 2 foundational, 15 en US1, 4 en US2, 4 en US3, 4 de cierre.

De ellas **12 escriben pruebas** (T001, T003–T008, T018, T019, T022, T023, T026) y una más las ejecuta
contra el entorno real (T029). Casi el 40 % del trabajo es la compuerta constitucional, que es lo
esperable en una feature que decide sobre capacidad y toca la máquina de estados.
