---

description: "Task list for feature implementation"
---

# Tasks: Recuperación de Errores y Eliminación Lógica de Pedidos/Servicios

**Input**: Design documents from `/specs/001-pedido-soft-delete-retry/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md)

**Tests**: SÍ se incluyen. El objetivo de este feature es el manejo de fallos de infraestructura, imposible de validar a mano de forma repetible; ver [research.md](./research.md) R6.

**Organization**: Tareas agrupadas por historia de usuario para poder implementar y validar cada una de forma independiente.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivo distinto, sin dependencias pendientes)
- **[Story]**: US1 = reintento de despliegue, US2 = baja lógica
- Todas las rutas son relativas a la raíz del repositorio

## Path Conventions

Aplicación web: backend en `backend/app/`, pruebas nuevas en `backend/tests/`. El frontend no se toca en este hito.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Andamiaje de pruebas, que hoy no existe en el repositorio

- [ ] T001 Agregar `pytest`, `pytest-asyncio`, `httpx` y `aiosqlite` a `backend/requirements.txt` e instalar con `pip install -r requirements.txt`
- [ ] T002 Crear `backend/pytest.ini` con `asyncio_mode = auto`, `testpaths = tests` y `pythonpath = .`
- [ ] T003 Crear `backend/tests/conftest.py` con fixtures: engine SQLite async en memoria, creación de tablas desde `Base.metadata`, sesión por prueba, override de la dependencia `get_db`, y cliente HTTP async sobre `app`
- [ ] T004 [P] Crear `backend/tests/fakes.py` con `FakeProxmoxClient` configurable (permite forzar excepción en `create_lxc`, definir `get_next_vmid`, y devolver contenidos arbitrarios en `get_cluster_resources`) y el override de `get_proxmox_client`
- [ ] T005 [P] Crear `backend/tests/factories.py` con helpers para dar de alta en la base de pruebas: cátedra con cuota, usuario admin, usuario de cátedra, template LXC y pedido en un estado dado
- [ ] T006 Agregar fixtures de autenticación en `backend/tests/conftest.py` que emitan JWT válidos para el usuario admin y el usuario de cátedra (reutilizando `app.utils.security.create_access_token`)

**Checkpoint**: `pytest` corre en verde con cero pruebas y las fixtures importan sin error

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cambios de esquema compartidos por ambas historias

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase

- [ ] T007 Agregar columnas `deleted_at` (`DateTime`, nullable) y `vmid_reservado` (`String(10)`, nullable) al modelo `Pedido` en `backend/app/models/pedido.py`
- [ ] T008 [P] Agregar columna `deleted_at` (`DateTime`, nullable) al modelo `Servicio` en `backend/app/models/servicio.py`
- [ ] T009 Crear la revisión Alembic en `backend/alembic/versions/` con `down_revision = 'ce2e9b4b4077'`, que agregue las tres columnas y los índices parciales `WHERE deleted_at IS NULL` sobre `pedidos` y `servicios` (depende de T007, T008)
- [ ] T010 Aplicar con `cd backend && alembic upgrade head` y verificar que las tres columnas existen; probar además que `alembic downgrade -1` revierte limpio

**Checkpoint**: Esquema migrado; el comportamiento observable de la API sigue idéntico (todas las filas quedan con `deleted_at = NULL`)

---

## Phase 3: User Story 1 - Reintentar un despliegue fallido (Priority: P1) 🎯 MVP

**Goal**: Un administrador recupera un pedido atascado en ERROR con una sola llamada, sin duplicar contenedores en Proxmox.

**Independent Test**: Llevar un pedido a ERROR simulando un fallo de infraestructura, disparar el reintento y verificar que termina en ACTIVO con un único contenedor — sin depender en absoluto de la baja lógica.

### Tests for User Story 1 ⚠️

> **Escribir estas pruebas PRIMERO y confirmar que fallan antes de implementar**

- [ ] T011 [P] [US1] Pruebas de máquina de estados del reintento en `backend/tests/test_reintento_despliegue.py`: reintento exitoso desde ERROR deja el pedido en ACTIVO (US1 esc. 1); reintento que vuelve a fallar deja el pedido en ERROR con una entrada de historial adicional sin borrar la anterior (US1 esc. 2, FR-005); reintento sobre un pedido que no está en ERROR responde 409 (US1 esc. 3, FR-002)
- [ ] T012 [P] [US1] Pruebas de resolución de VMID en `backend/tests/test_reintento_vmid.py`: reserva libre se reutiliza (US1 esc. 4, FR-004); reserva ocupada por hostname ajeno fuerza pedir un VMID nuevo (US1 esc. 5); reserva ocupada con el hostname `cat{catedra}-svc{pedido}` propio se adopta sin crear un segundo contenedor ([research.md](./research.md) R2); sin reserva previa se pide uno nuevo
- [ ] T013 [P] [US1] Prueba de autorización en `backend/tests/test_reintento_permisos.py`: un usuario con rol de cátedra que invoca el reintento recibe 403 (FR-006)
- [ ] T014 [P] [US1] Prueba de persistencia de la reserva en `backend/tests/test_reserva_vmid.py`: tras un despliegue fallido, el `Pedido` conserva `vmid_reservado` poblado en la base ([research.md](./research.md) R1)

### Implementation for User Story 1

- [ ] T015 [US1] Refactor sin cambio de comportamiento en `backend/app/services/orquestacion_service.py`: extraer el cuerpo de aprovisionamiento de `desplegar_pedido()` (elección de nodo, VMID, construcción de config, `create_lxc`, alta del `Servicio`, transición a ACTIVO, manejo de error) a una función interna `_ejecutar_despliegue(db, pedido, admin, node, storage)`; dejar `desplegar_pedido()` validando solo el estado APROBADO y delegando ([research.md](./research.md) R5)
- [ ] T016 [US1] En `backend/app/services/orquestacion_service.py`, persistir la reserva: escribir `pedido.vmid_reservado` con `commit` propio inmediatamente después de obtener el VMID y **antes** de llamar a `create_lxc`, de modo que sobreviva al fallo
- [ ] T017 [US1] Implementar `_resolver_vmid(pve, pedido, hostname)` en `backend/app/services/orquestacion_service.py` que devuelva `(vmid, contenedor_existente)` según la matriz de [contracts/api.md](./contracts/api.md): sin reserva → `get_next_vmid()`; reserva libre en `get_cluster_resources()` → reutilizar; reserva ocupada con hostname coincidente → señalar adopción; reserva ocupada con hostname distinto → `get_next_vmid()`
- [ ] T018 [US1] En `_ejecutar_despliegue()` de `backend/app/services/orquestacion_service.py`, manejar la rama de adopción: cuando `_resolver_vmid` detecta un contenedor huérfano propio, registrar el `Servicio` apuntando a ese contenedor y saltear `create_lxc`, dejando constancia en el comentario del historial
- [ ] T019 [US1] Implementar `reintentar_despliegue(db, pedido_id, admin, node, storage)` en `backend/app/services/orquestacion_service.py`: validar que el pedido existe y no está dado de baja (404), que su estado es ERROR (409 con el estado actual en el mensaje), transicionar ERROR → EN_DESPLIEGUE vía `cambiar_estado` y delegar en `_ejecutar_despliegue()`
- [ ] T020 [P] [US1] Exponer `vmid_reservado` en `PedidoResponse` dentro de `backend/app/schemas/pedido.py`
- [ ] T021 [US1] Agregar el endpoint `POST /pedidos/{pedido_id}/reintentar` en `backend/app/routers/pedidos.py`, protegido con `require_admin`, con body opcional `DesplegarRequest` y `response_model=ServicioResponse` (depende de T019)
- [ ] T022 [US1] Correr `pytest backend/tests/test_reintento_despliegue.py backend/tests/test_reintento_vmid.py backend/tests/test_reintento_permisos.py backend/tests/test_reserva_vmid.py` y dejar todo en verde

**Checkpoint**: US1 completa y verificable de forma aislada. El bug del pedido "colgado" queda cerrado y el sistema es entregable en este punto (MVP).

---

## Phase 4: User Story 2 - Preservar el historial académico (Priority: P2)

**Goal**: Dar de baja pedidos y servicios sin perder el registro de consumo por cátedra, y sin que esos registros sigan ocupando cuota.

**Independent Test**: Dar de baja un servicio y verificar que desaparece de los listados, que su fila sigue en la base con `deleted_at`, y que la cuota de su cátedra se liberó — sin usar el reintento en ningún momento.

### Tests for User Story 2 ⚠️

> **Escribir estas pruebas PRIMERO y confirmar que fallan antes de implementar**

- [ ] T023 [P] [US2] Pruebas de baja de servicio en `backend/tests/test_soft_delete_servicio.py`: la baja libera el contenedor y marca `deleted_at` conservando la fila (US2 esc. 1, FR-007/FR-008); el servicio desaparece de `GET /servicios/` y su detalle responde 404 (US2 esc. 2, FR-009); si Proxmox falla al liberar, se propaga 502 y `deleted_at` queda en `NULL` (FR-010); la doble baja es idempotente (US2 esc. 5); un servicio sin `proxmox_vmid` se da de baja sin llamar a Proxmox
- [ ] T024 [P] [US2] Pruebas de baja de pedido en `backend/tests/test_soft_delete_pedido.py`: un pedido rechazado sin servicio se da de baja sin tocar Proxmox (US2 esc. 6, FR-013); un pedido con servicio vigente responde 409 (US2 esc. 7, FR-014); un usuario no admin recibe 403 (FR-015); el pedido dado de baja sale de los listados y su detalle responde 404 (FR-009)
- [ ] T025 [P] [US2] Pruebas de cuota e historial en `backend/tests/test_soft_delete_cuota.py`: un servicio dado de baja no cuenta en `verificar_cuota`, permitiendo crear un pedido que antes excedía la cuota (FR-012, SC-005); el uso informado en `GET /catedras/{id}` lo excluye; el `PedidoHistorial` de un pedido dado de baja sigue siendo consultable en la base (FR-011, SC-003)

### Implementation for User Story 2

- [ ] T026 [P] [US2] Crear `backend/app/utils/soft_delete.py` con helpers reutilizables: `excluir_dados_de_baja(query, modelo)` que agrega `.where(modelo.deleted_at.is_(None))`, y `esta_dado_de_baja(obj)` para los accesos por ID ([research.md](./research.md) R3)
- [ ] T027 [US2] Convertir `eliminar_servicio()` en `backend/app/services/orquestacion_service.py` de borrado físico a baja lógica: mantener la liberación en Proxmox **antes** del marcado, reemplazar `db.delete(servicio)` por `servicio.deleted_at = datetime.utcnow()`, retornar el mensaje e `deleted_at` según [contracts/api.md](./contracts/api.md), y salir temprano de forma idempotente si ya estaba dado de baja (FR-010, [research.md](./research.md) R7)
- [ ] T028 [US2] Implementar `dar_de_baja_pedido(db, pedido_id, admin)` en `backend/app/services/pedido_service.py`: 404 si no existe, idempotente si ya estaba dado de baja, y 409 si tiene un `Servicio` asociado con `deleted_at IS NULL` (FR-013, FR-014)
- [ ] T029 [US2] Agregar el filtro `deleted_at IS NULL` a la subconsulta de uso de recursos en `verificar_cuota()` dentro de `backend/app/services/pedido_service.py` (FR-012)
- [ ] T030 [US2] En `backend/app/routers/pedidos.py`: excluir los dados de baja del listado `listar_pedidos` y responder 404 en `obtener_pedido` y `cambiar_estado_pedido` cuando el pedido esté dado de baja (FR-009)
- [ ] T031 [US2] Agregar el endpoint `DELETE /pedidos/{pedido_id}` en `backend/app/routers/pedidos.py`, protegido con `require_admin`, delegando en `dar_de_baja_pedido` (depende de T028, T030)
- [ ] T032 [P] [US2] En `backend/app/routers/servicios.py`: excluir los dados de baja de `listar_servicios` y responder 404 en `obtener_servicio` y `estado_en_proxmox` (FR-009)
- [ ] T033 [P] [US2] En `backend/app/routers/catedras.py`: excluir los servicios dados de baja del cálculo de uso de recursos de la cátedra (FR-012)
- [ ] T034 [P] [US2] En `backend/app/routers/metricas.py`: excluir los servicios dados de baja de las cuatro consultas de servicios (listado con métricas y accesos por ID)
- [ ] T035 [P] [US2] En `backend/app/services/metricas_service.py`: excluir los servicios dados de baja de la captura periódica de snapshots, para no seguir midiendo recursos ya liberados
- [ ] T036 [P] [US2] Exponer `deleted_at` en `PedidoResponse` (`backend/app/schemas/pedido.py`) y en `ServicioResponse` (`backend/app/schemas/servicio.py`)
- [ ] T037 [US2] Correr `pytest backend/tests/test_soft_delete_servicio.py backend/tests/test_soft_delete_pedido.py backend/tests/test_soft_delete_cuota.py` y dejar todo en verde

**Checkpoint**: US1 y US2 funcionan de forma independiente. Los ocho sitios de consulta del inventario de [research.md](./research.md) R4 quedan cubiertos.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T038 Correr la suite completa con `cd backend && pytest -v` y confirmar que no hay regresiones en los endpoints preexistentes
- [ ] T039 [P] Revisar los `docstring` de los endpoints nuevos y modificados para que `/api/docs` refleje los códigos de estado documentados en [contracts/api.md](./contracts/api.md)
- [ ] T040 [P] Actualizar `PLAN_TRABAJO.md`: marcar como completos los ítems "Soft Delete" y "Recuperación de Errores" del Hito 3 (backend), dejando constancia de que la parte de frontend del hito sigue pendiente
- [ ] T041 Ejecutar la validación manual del apartado "Validación manual contra Proxmox real" de [quickstart.md](./quickstart.md) contra el clúster, y tildar los criterios de aceptación finales
- [ ] T042 [P] Verificar que la lista de sitios de consulta de [research.md](./research.md) R4 no quedó incompleta: `grep -rn "select(Servicio)\|select(Pedido)\|db.get(Servicio\|db.get(Pedido" backend/app` y confirmar que cada resultado tiene su filtro o su 404

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias, arranca de inmediato
- **Foundational (Phase 2)**: depende de Setup; **bloquea ambas historias** (las dos necesitan las columnas nuevas y la migración aplicada)
- **US1 (Phase 3)**: depende de Foundational; sin dependencias sobre US2
- **US2 (Phase 4)**: depende de Foundational; sin dependencias sobre US1
- **Polish (Phase 5)**: depende de las historias que se quieran entregar

### User Story Dependencies

- **US1 (P1)**: independiente. Usa `vmid_reservado`; no usa `deleted_at`.
- **US2 (P2)**: independiente. Usa `deleted_at`; no usa el reintento.
- Único punto de contacto: ambas tocan `orquestacion_service.py` (T015–T019 vs T027) y `routers/pedidos.py` (T021 vs T030–T031). Si se trabajan en paralelo, coordinar esos dos archivos o serializar las historias.

### Within Each User Story

- Las pruebas se escriben primero y deben fallar antes de implementar
- Servicios antes que endpoints
- El refactor T015 va antes que todo lo demás de US1: los pasos siguientes construyen sobre la función extraída

### Parallel Opportunities

- T004 y T005 en paralelo (archivos distintos, después de T001–T003)
- T007 y T008 en paralelo (modelos distintos)
- T011–T014 en paralelo (cuatro archivos de prueba distintos)
- T023–T025 en paralelo (tres archivos de prueba distintos)
- T032–T036 en paralelo (cinco archivos distintos, todos consumen el helper de T026)
- Con dos personas: una toma US1 completa y la otra US2, coordinando los dos archivos compartidos

---

## Parallel Example: User Story 1

```bash
# Escribir las cuatro suites de prueba en paralelo (fallan al inicio):
Task: "Pruebas de máquina de estados en backend/tests/test_reintento_despliegue.py"
Task: "Pruebas de resolución de VMID en backend/tests/test_reintento_vmid.py"
Task: "Prueba de autorización en backend/tests/test_reintento_permisos.py"
Task: "Prueba de persistencia de reserva en backend/tests/test_reserva_vmid.py"
```

## Parallel Example: User Story 2

```bash
# Una vez creado el helper de T026, los sitios de consulta van en paralelo:
Task: "Filtros en backend/app/routers/servicios.py"
Task: "Filtros en backend/app/routers/catedras.py"
Task: "Filtros en backend/app/routers/metricas.py"
Task: "Filtro en backend/app/services/metricas_service.py"
Task: "Exponer deleted_at en los schemas"
```

---

## Implementation Strategy

### MVP First (solo US1)

1. Completar Phase 1 (Setup) — habilita poder probar cualquier cosa
2. Completar Phase 2 (Foundational) — bloquea todo lo demás
3. Completar Phase 3 (US1)
4. **PARAR Y VALIDAR**: recuperar un pedido en ERROR de punta a punta
5. Entregable: el bug operativo más urgente queda cerrado

### Incremental Delivery

1. Setup + Foundational → base lista
2. US1 → validar → entregar (MVP: reintento funcionando)
3. US2 → validar → entregar (historial académico preservado)
4. Polish → validación contra Proxmox real y actualización del plan de trabajo

---

## Notes

- Las tareas [P] tocan archivos distintos y no dependen entre sí
- Confirmar que cada prueba falla antes de escribir la implementación que la satisface
- Commitear por tarea o por grupo lógico; los checkpoints son buenos puntos de corte
- T015 es un refactor puro: si alguna prueba existente cambia de comportamiento ahí, es una regresión, no un avance
- Riesgo a vigilar: `Pedido.parametros_extra` usa el tipo `JSON`; si SQLite diera problemas en las fixtures, la alternativa es levantar PostgreSQL en contenedor para las pruebas ([research.md](./research.md) R6)
