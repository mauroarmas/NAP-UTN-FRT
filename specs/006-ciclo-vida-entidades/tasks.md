---

description: "Task list for 006-ciclo-vida-entidades"
---

# Tasks: Retirar y corregir usuarios, cátedras y plantillas

**Input**: Design documents from `/specs/006-ciclo-vida-entidades/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: **OBLIGATORIOS**, no opcionales. La constitución v2.0.0 exige pruebas automatizadas para
todo código que toque control de capacidad, con al menos un camino de fallo simulado. La corrección
del despliegue (R2) cae de lleno ahí. El resto de la feature lleva pruebas por la regla de "cubrir al
tocar". Las tareas de prueba son compuertas, no adornos.

**Organization**: Agrupadas por historia de usuario para permitir implementación y validación
independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: A qué historia pertenece (US1–US3)
- Cada tarea incluye la ruta exacta del archivo

## Path Conventions

Aplicación web: `backend/app/`, `backend/tests/`, `frontend/src/`. Rutas relativas a la raíz del
repositorio, según la estructura fijada en [plan.md](./plan.md).

> **Sin migraciones.** Esta feature no agrega ni modifica columnas: todos los campos que usa ya
> existen (ver [data-model.md](./data-model.md)). Si alguna tarea parece necesitar una migración,
> es señal de que se desvió del diseño.

---

## Phase 1: Setup

**Purpose**: No hay setup que hacer. La feature trabaja sobre archivos y dependencias que ya existen.

*(Fase vacía a propósito: no se agregan dependencias, ni carpetas, ni configuración. Se documenta
para dejar constancia de que se evaluó y no hizo falta.)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: La corrección que vuelve seguro habilitar la edición de plantillas.

**⚠️ CRITICAL**: T001–T003 bloquean la US1. Habilitar la edición de plantillas **antes** de corregir
el origen de los valores del despliegue introduce una fuga de capacidad silenciosa (R2): un pedido
aprobado por 1 vCPU se desplegaría con 4 si la plantilla cambió en el medio, sobrecomprometiendo el
clúster sin que nadie lo aprobara y sin dejar rastro.

- [X] T001 Prueba de la compuerta de capacidad: aprobar un pedido, editar la plantilla a valores mayores **sin desplegar**, desplegar, y verificar que el contenedor se crea con `pedido.reserva_*` y no con `template.default_*`; incluir el caso de fallo de infraestructura durante ese despliegue, en `backend/tests/test_despliegue_usa_reserva.py`
- [X] T002 Hacer que la creación del contenedor use `pedido.reserva_vcpus`, `pedido.reserva_ram_mb` y `pedido.reserva_disk_gb` en lugar de `template.default_*`, en `backend/app/services/orquestacion_service.py` (líneas 203-205) — regla P1
- [X] T003 Hacer que el registro del `Servicio` use esos mismos valores reservados, en `backend/app/services/orquestacion_service.py` (líneas 362-364) — regla P2, para que lo reservado, lo desplegado y lo registrado coincidan

**Checkpoint**: El despliegue es inmune a que la plantilla cambie después de aprobar. Recién ahora se
puede habilitar la edición.

---

## Phase 3: User Story 1 - Corregir una plantilla mal cargada (Priority: P1) 🎯 MVP

**Goal**: El administrador puede corregir y retirar plantillas desde el portal, sin tocar la base.

**Independent Test**: Crear una plantilla con una imagen inexistente, corregirla desde la interfaz y
comprobar que un pedido nuevo con ella se despliega bien; después retirarla y verificar que deja de
ofrecerse sin romper lo ya desplegado.

### Tests for User Story 1 ⚠️ (compuerta constitucional)

- [X] T004 [P] [US1] Pruebas de edición de plantilla: campos editables se aplican; `tipo` rechazado con 400 (T4); nombre duplicado rechazado con 409 excluyendo la propia plantilla (T6); tope de disco sin justificación rechazado y con justificación aceptado (T3/FR-007); no administrador recibe 403, en `backend/tests/test_templates_edicion.py`
- [X] T005 [P] [US1] Pruebas de que editar no altera lo ya entregado: un servicio desplegado conserva `vcpus_asignados`, `ram_asignada_mb` y `disk_asignado_gb` tras editar su plantilla (T1/FR-002), en `backend/tests/test_templates_edicion.py`
- [X] T006 [P] [US1] Pruebas de retiro de plantilla: desaparece de `GET /templates/`; `crear_pedido` con ella devuelve 404 (FR-005); `GET /templates/{id}` la sigue resolviendo (T5/FR-006); reactivarla la devuelve al catálogo, en `backend/tests/test_templates_retiro.py`

### Implementation for User Story 1

- [X] T007 [US1] Crear el schema `TemplateUpdate` con todos los campos opcionales y **sin** `tipo`, en `backend/app/schemas/template.py`
- [X] T008 [US1] Agregar `alcance_del_cambio` (conteo de servicios desplegados y de pedidos aprobados pendientes) a `TemplateResponse`, como campo informativo y opcional, en `backend/app/schemas/template.py`
- [X] T009 [US1] Implementar `PATCH /templates/{template_id}` en `backend/app/routers/templates.py`: aplica solo los campos enviados, rechaza `tipo` con 400, valida unicidad de nombre excluyendo la propia plantilla, y reutiliza `limites_service.validar_disco` para el tope de disco (depende de T007)
- [X] T010 [US1] Calcular y devolver `alcance_del_cambio` en la respuesta del PATCH, contando servicios vigentes y pedidos aprobados sin desplegar de esa plantilla, en `backend/app/routers/templates.py` (depende de T008, T009)
- [X] T011 [P] [US1] Agregar `updateTemplate(id, data)` al cliente de API en `frontend/src/services/api.js`
- [X] T012 [US1] Agregar la acción de editar a la tabla de plantillas, reutilizando el formulario de alta en modo edición, en `frontend/src/pages/Templates.jsx` (depende de T011)
- [X] T013 [US1] Mostrar el aviso de alcance al editar —qué servicios no se ven afectados y cuántos pedidos aprobados se desplegarán con lo que ya reservaron— como información y no como bloqueo (FR-003), en `frontend/src/pages/Templates.jsx` (depende de T012)
- [X] T014 [US1] Agregar la acción de retirar y reactivar plantillas, y mostrar su estado en la tabla, en `frontend/src/pages/Templates.jsx` (depende de T011)

**Checkpoint**: US1 entregable de forma independiente. Una plantilla mal cargada ya se puede
arreglar sin tocar la base — el defecto que motivó la feature queda cerrado.

---

## Phase 4: User Story 2 - Retirar a una persona que ya no está (Priority: P1)

**Goal**: Retirar a un docente que se fue funciona en un solo intento, sin errores técnicos, y su
autoría sobre los pedidos sobrevive.

**Independent Test**: Con una persona que creó pedidos, retirarla desde el portal y comprobar que la
operación se completa con un mensaje claro, que no puede volver a iniciar sesión, y que sus pedidos
siguen consultables con su autoría.

### Tests for User Story 2 ⚠️ (compuerta constitucional)

- [X] T015 [P] [US2] Prueba de regresión del defecto: retirar a una persona **con pedidos** se completa sin error y **no** devuelve 500; los pedidos conservan su `solicitante_id` (U1, U3, FR-009, FR-010, FR-015), en `backend/tests/test_usuarios_retiro.py`
- [X] T016 [P] [US2] Pruebas del criterio baja lógica vs. borrado real: con historial queda `activo=false` y la fila permanece; sin historial la fila se elimina; en ambos casos la respuesta dice cuál de las dos cosas pasó (U1, U2), en `backend/tests/test_usuarios_retiro.py`
- [X] T017 [P] [US2] Pruebas de los guards: retirarse a uno mismo → 400; último administrador activo → 409 `ultimo_administrador`; con cátedras a cargo → 409 `catedras_sin_responsable` (U6, U7, U8, FR-013), en `backend/tests/test_usuarios_retiro.py`
- [X] T018 [P] [US2] Pruebas de visibilidad: una persona retirada no puede iniciar sesión (U4), queda fuera de `GET /usuarios/` por defecto, aparece con `?incluir_bajas=true`, y `GET /usuarios/{id}` la sigue resolviendo (U5, FR-011, FR-012), en `backend/tests/test_usuarios_retiro.py`

### Implementation for User Story 2

- [X] T019 [P] [US2] Crear `tiene_historial(db, usuario_id)` —¿tiene pedidos o cátedras a cargo?— y `es_ultimo_admin_activo(db, usuario_id)` en `backend/app/services/usuario_service.py`
- [X] T020 [P] [US2] Declarar explícitamente la relación `Usuario.pedidos` para que ningún camino intente anular `solicitante_id` al borrar (R3), en `backend/app/models/usuario.py`
- [X] T021 [US2] Reescribir `DELETE /usuarios/{usuario_id}`: aplicar los guards en el orden fijado en data-model.md, y elegir entre baja lógica y borrado real según haya historial, en `backend/app/routers/usuarios.py` (depende de T019, T020)
- [X] T022 [US2] Cambiar la respuesta del DELETE de `204 No Content` a `200` con `{id, username, resultado, mensaje}`, en `backend/app/routers/usuarios.py` y `backend/app/schemas/usuario.py` (depende de T021)
- [X] T023 [US2] Agregar el guard del último administrador activo también al `PATCH /usuarios/{id}` cuando desactiva, para que las dos puertas queden custodiadas igual (R4), en `backend/app/routers/usuarios.py` (depende de T019)
- [X] T024 [US2] Filtrar `GET /usuarios/` por `activo` por defecto y aceptar `?incluir_bajas=true` (R6, FR-012), en `backend/app/routers/usuarios.py`
- [X] T025 [US2] Adaptar `deleteUsuario` al nuevo código de respuesta y cuerpo en `frontend/src/services/api.js`
- [X] T026 [US2] Mostrar el resultado del retiro con el mensaje que devuelve el backend, y ajustar el texto de la confirmación para que diga lo que ahora ocurre de verdad, en `frontend/src/pages/Usuarios.jsx` (depende de T025)

**Checkpoint**: US2 entregable de forma independiente. La rotación normal de docentes deja de
terminar en un 500.

---

## Phase 5: User Story 3 - Un bloqueo que dice cómo salir de él (Priority: P2)

**Goal**: Todo bloqueo indica una acción que, ejecutada literalmente, destraba la operación.

**Independent Test**: Intentar desactivar a un titular, seguir literalmente el consejo del mensaje, y
comprobar que la acción se destraba.

### Tests for User Story 3

- [X] T027 [P] [US3] Prueba de que el consejo funciona: bloqueado por cátedras a cargo, reasignar el titular destraba la operación; y el mensaje **no** menciona dar la cátedra de baja (FR-016), en `backend/tests/test_mensajes_bloqueo.py`
- [X] T028 [P] [US3] Prueba de que el guard sigue aplicando con la cátedra dada de baja, porque puede conservar servicios vigentes (FR-017, R5) —protege contra "optimizar" `catedras_de` filtrando por `activa`—, en `backend/tests/test_mensajes_bloqueo.py`

### Implementation for User Story 3

- [X] T029 [US3] Corregir el texto del 409 `catedras_sin_responsable` para que nombre solo la salida que funciona (reasignar), en `backend/app/routers/usuarios.py`
- [X] T030 [US3] Documentar en `catedras_de` por qué **no** debe filtrar por `activa` —una cátedra inactiva puede conservar servicios corriendo—, en `backend/app/services/usuario_service.py`

**Checkpoint**: Las tres historias funcionan de forma independiente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T031 [P] Revisar que ningún camino de retiro, edición o bloqueo devuelva un error sin traducir, recorriendo los códigos de `contracts/api.md` (FR-015, SC-006)
- [X] T032 [P] Actualizar `backend/README.md` con el ciclo de vida de plantillas y personas, y con la regla de que el despliegue usa lo reservado
- [X] T033 Anotar en `specs/004-unificar-usuario-catedra/quickstart.md` que los tres defectos que dejó abiertos quedaron resueltos por esta feature
- [X] T034 Ejecutar la validación completa de [quickstart.md](./quickstart.md), con E2, E3, E5 y E8 como bloqueantes

---

## Dependencies

```text
Phase 2 (T001-T003)  ─── BLOQUEA ───▶  US1 (Phase 3)
   corrección R2                        edición de plantillas

US1 (Phase 3) ──┐
US2 (Phase 4) ──┼──▶ independientes entre sí
US3 (Phase 5) ──┘

Phase 6 ◀── requiere las tres historias
```

**Por qué la Phase 2 bloquea solo a la US1**: la corrección del despliegue protege contra que una
plantilla cambie entre aprobar y desplegar. Sin edición de plantillas ese escenario es inalcanzable,
así que US2 y US3 no dependen de ella. Pero **entregar la US1 sin la Phase 2 deja el sistema peor que
antes**, y por eso la dependencia es dura y no una recomendación.

**US2 y US3 pueden hacerse en cualquier orden**, incluso antes que la US1. Tocan archivos que se
solapan (`routers/usuarios.py`, `services/usuario_service.py`), así que conviene no hacerlas en
paralelo por dos personas distintas, pero no hay dependencia lógica: T029 no necesita nada de T021.

## Parallel Execution

**Dentro de la Phase 2**: T002 y T003 tocan el mismo archivo; hacerlas juntas en un solo paso.
T001 se escribe primero (es la compuerta) y debe fallar antes de T002.

**Dentro de la US1**: T004, T005 y T006 son pruebas en archivos distintos → paralelizables. T011 es
frontend puro → paralelo con cualquier tarea de backend.

**Dentro de la US2**: T015 a T018 comparten archivo de pruebas; escribirlas de a una o coordinar.
T019 y T020 tocan archivos distintos → paralelizables.

**Entre historias**: la US1 (backend) y la US2 (backend) tocan routers distintos (`templates.py` vs
`usuarios.py`), así que dos personas pueden avanzarlas a la vez sin conflicto.

## Implementation Strategy

**MVP sugerido**: **Phase 2 + User Story 1** (T001–T014, 14 tareas).

Es el corte que cierra el defecto que motivó la feature: una plantilla mal cargada deja de ser
permanente, y se corrige desde el portal en vez de por SQL. Incluye obligatoriamente la Phase 2,
porque entregar la edición sin ella introduce la fuga de capacidad de R2.

**Entrega incremental**:

1. **Phase 2 + US1** → el catálogo deja de ser inmutable. Validar con E1, E2, E3 y E4 del quickstart.
2. **US2** → la rotación de docentes deja de romper. Validar con E5, E6 y E7.
3. **US3** → los mensajes dejan de mandar a callejones sin salida. Validar con E8 y E9.
4. **Phase 6** → validación completa y documentación.

**Sobre el orden de las dos P1**: la US1 va primero pese a que ambas son P1, porque su defecto rompe
el flujo principal del sistema (una plantilla rota falla *después* de que la cátedra pidió y el
administrador comprometió capacidad), mientras que el de la US2 se manifiesta en una tarea
administrativa aislada.

## Total

**34 tareas**: 0 de setup, 3 foundational, 11 en US1, 12 en US2, 4 en US3, 4 de cierre.

De ellas **10 escriben pruebas** (T001, T004–T006, T015–T018, T027–T028) y una más las ejecuta contra
el entorno real (T034). Casi un tercio del trabajo es la compuerta constitucional, que es lo esperable
en una feature que toca control de capacidad.
