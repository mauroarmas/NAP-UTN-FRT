# Tasks: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS

**Feature**: `007-solicitud-aprovisionamiento-servicios`  
**Input**: Design documents from `/specs/007-solicitud-aprovisionamiento-servicios/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [data-model.md](data-model.md), [research.md](research.md), [contracts/](contracts/)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verificación de entorno, dependencias y preparación de herramientas de validación.

- [X] T001 Verify backend dependencies (FastAPI, SQLAlchemy 2, Alembic, Proxmoxer) in backend/pyproject.toml or backend/requirements.txt
- [X] T002 [P] Verify frontend dependencies and build tools in frontend/package.json
- [X] T003 [P] Create initial contract test suite skeleton in backend/tests/test_solicitudes_recursos.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modificaciones de base de datos, enums y núcleo de máquina de estados que desbloquean todas las historias de usuario.

**⚠️ CRITICAL**: Ninguna historia de usuario puede avanzar hasta completar esta fase.

- [X] T004 Update EstadoPedido enum with REQUIERE_AJUSTE and CANCELADO in backend/app/models/pedido.py
- [X] T005 Update Pedido model with modelo_servicio, descripcion_requerimientos, vigencia_tipo, vigencia_desde, vigencia_hasta and opciones_avanzadas in backend/app/models/pedido.py
- [X] T006 [P] Update RecursoTemplate model with modelo_servicio and justificacion_disco in backend/app/models/recurso_template.py
- [X] T007 [P] Update Servicio model with url_acceso and credenciales_acceso in backend/app/models/servicio.py
- [X] T008 Generate and execute Alembic migration for new columns and enums in backend/alembic/versions/
- [X] T009 Update state transition matrix and validation rules in backend/app/services/pedido_service.py

**Checkpoint**: Base de datos y máquina de estados centralizada listas y consistentes.

---

## Phase 3: User Story 1 - Solicitud de Recursos por Cátedra (Priority: P1) 🎯 MVP

**Goal**: Permitir que un docente de cátedra cree solicitudes indicando modelo de servicio (IaaS, PaaS o SaaS), especificaciones o template sugerido y vigencia temporal (cuatrimestre/anual).

**Independent Test**: El docente envía una solicitud mediante el modal en el portal; el sistema valida los datos y registra el pedido en estado `SOLICITADO` con su identificador de seguimiento.

- [X] T010 [P] [US1] Create Pydantic request/response schemas for IaaS/PaaS/SaaS creation and validation in backend/app/schemas/pedido.py
- [X] T011 [US1] Implement crear_pedido logic with service model and validity support in backend/app/services/pedido_service.py
- [X] T012 [US1] Update POST /api/v1/pedidos endpoint with authentication and tenant checks in backend/app/routers/pedidos.py
- [X] T013 [P] [US1] Add unit tests for order creation validation (IaaS template check, SaaS description check, validity check) in backend/tests/test_pedido_creation.py
- [X] T014 [US1] Update NuevoPedidoModal component with service model selector, dynamic templates loading via GET /api/v1/templates?solo_activos=true and validity inputs in frontend/src/components/NuevoPedidoModal.jsx
- [X] T015 [US1] Update PedidosPage table to display service model badge, requested validity and status in frontend/src/pages/PedidosPage.jsx

**Checkpoint**: La cátedra puede solicitar recursos IaaS, PaaS y SaaS con vigencia completa de forma autónoma.

---

## Phase 4: User Story 2 - Evaluación y Aprobación con Despliegue Automático (Priority: P1)

**Goal**: Permitir que el Administrador evalúe solicitudes, configure opciones avanzadas si es necesario, reserve capacidad atómicamente y dispare el aprovisionamiento automatizado en Proxmox VE.

**Independent Test**: El Administrador aprueba un pedido pendiente seleccionando template y opciones avanzadas; el sistema orquesta la creación del contenedor/VM, actualiza el estado a `ACTIVO` (Disponible) y emite los accesos.

- [X] T016 [P] [US2] Create Pydantic schemas for approval payload and advanced options in backend/app/schemas/pedido.py
- [X] T017 [US2] Update orquestacion_service to support automated provisioning with advanced options (node, vlan, storage) in backend/app/services/orquestacion_service.py
- [X] T018 [US2] Integrate atomic capacity check and reservation in backend/app/services/capacidad_service.py
- [X] T019 [US2] Update POST /api/v1/pedidos/{id}/aprobar endpoint handling advanced options and transition to EN_DESPLIEGUE in backend/app/routers/pedidos.py
- [X] T020 [P] [US2] Add integration test for automated deployment and capacity reservation in backend/tests/test_aprobacion_despliegue.py
- [X] T021 [US2] Create or update AprobarPedidoModal component with template selector and collapsible Advanced Options in frontend/src/components/AprobarPedidoModal.jsx
- [X] T022 [US2] Connect approval action and feedback toasts in frontend/src/pages/PedidosPage.jsx

**Checkpoint**: El Happy Path completo (solicitud -> aprobación -> orquestación -> servicio activo) es 100% operativo.

---

## Phase 5: User Story 3 - Flujo de Rechazo y Negociación de Ajustes (Priority: P2)

**Goal**: Permitir el rechazo con motivo escrito obligatorio y el ciclo colaborativo de ajustes (`REQUIERE_AJUSTE`) entre el Administrador y la Cátedra.

**Independent Test**: El Administrador devuelve un pedido con observaciones; el pedido pasa a `REQUIERE_AJUSTE`; la Cátedra visualiza las notas, modifica la solicitud y la reenvía a `SOLICITADO` (o la cancela voluntariamente).

- [X] T023 [P] [US3] Create Pydantic schemas for reject and adjust payloads in backend/app/schemas/pedido.py
- [X] T024 [US3] Implement solicitar_ajuste, reenviar_pedido and cancelar_pedido transition methods in backend/app/services/pedido_service.py
- [X] T025 [US3] Implement endpoints POST /pedidos/{id}/solicitar-ajuste, POST /pedidos/{id}/reenviar and POST /pedidos/{id}/cancelar in backend/app/routers/pedidos.py
- [X] T026 [US3] Enforce mandatory reject motive validation in POST /pedidos/{id}/rechazar in backend/app/routers/pedidos.py
- [X] T027 [P] [US3] Add unit tests for adjustment transitions and reject motive validation in backend/tests/test_ajustes_rechazos.py
- [X] T028 [US3] Create AjustePedidoModal component for Admin to submit adjustment suggestions in frontend/src/components/AjustePedidoModal.jsx
- [X] T029 [US3] Add adjustment view and resubmit/cancel actions for Cátedra users in frontend/src/pages/PedidosPage.jsx

**Checkpoint**: El flujo de negociación colaborativa y rechazos fundados está operativo y probado.

---

## Phase 6: User Story 4 - Visualización y Autogestión de Servicios por Cátedra (Priority: P2)

**Goal**: Brindar a la Cátedra visibilidad de los datos de conexión (IP, URL, credenciales), vigencia y controles de ciclo de vida (iniciar, detener, reiniciar y métricas).

**Independent Test**: La Cátedra accede a "Mis Servicios", visualiza los parámetros de acceso para compartir con sus alumnos y envía comandos de reinicio y detención al contenedor.

- [X] T030 [P] [US4] Create Pydantic schemas for service detail and connection credentials in backend/app/schemas/servicio.py
- [X] T031 [US4] Update GET /api/v1/servicios and GET /api/v1/servicios/{id} to expose access URLs and credentials in backend/app/routers/servicios.py
- [X] T032 [US4] Verify and ensure robust error handling for POST /servicios/{id}/start, /stop and /reboot in backend/app/routers/servicios.py
- [X] T033 [US4] Ensure real-time metrics proxy in GET /api/v1/servicios/{id}/metricas in backend/app/routers/servicios.py
- [X] T034 [P] [US4] Add tests for service lifecycle controls and tenant boundary isolation in backend/tests/test_servicios_autogestion.py
- [X] T035 [US4] Update ServiciosPage cards with connection credentials copy buttons, expiration countdown and control buttons in frontend/src/pages/ServiciosPage.jsx

**Checkpoint**: La Cátedra autogestiona sus servicios desplegados y cuenta con los accesos para sus alumnos.

---

## Phase 7: User Story 5 - Módulo ABM de Plantillas de Recursos (Priority: P3)

**Goal**: Proveer al Administrador un panel para crear, editar, listar y desactivar plantillas homologadas con validación constitucional de disco ($\le 8$ GB).

**Independent Test**: El Administrador crea una nueva plantilla con nombre, vCPU, RAM, disco y justificación; verifica que la plantilla aparezca activa en el catálogo de nuevas solicitudes.

- [X] T036 [P] [US5] Create Pydantic schemas for Template CRUD with disk validation in backend/app/schemas/template.py
- [X] T037 [US5] Implement CRUD operations (create, update, soft-delete) and service model filters in backend/app/routers/templates.py
- [X] T038 [P] [US5] Add unit tests verifying 8 GB disk limit requires justification in backend/tests/test_templates_admin.py
- [X] T039 [US5] Create TemplatesAdmin view/modal for managing resource templates in frontend/src/components/TemplatesAdmin.jsx
- [X] T040 [US5] Add TemplatesAdmin access in the admin navigation panel in frontend/src/App.jsx

**Checkpoint**: El Administrador administra el catálogo de templates homologados de forma dinámica.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Verificación integral, auditoría, documentación y pruebas de punta a punta.

- [X] T041 Run quickstart.md validation scenarios against local test environment in backend/tests/test_quickstart_e2e.py
- [X] T042 [P] Verify audit logging immutability and history entries for all order transitions in backend/app/services/historial_service.py
- [X] T043 [P] Code cleanup, typing verification with mypy and formatting with ruff/black in backend/
- [X] T044 Update project documentation in docs/nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias, arranca inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1. **Bloquea todas las historias de usuario**.
- **User Story 1 (Phase 3)**: Depende de Phase 2. Puede entregarse como MVP independiente.
- **User Story 2 (Phase 4)**: Depende de Phase 2 y se integra con las solicitudes de US1.
- **User Story 3 (Phase 5)**: Depende de Phase 2 y de la gestión de pedidos de US1/US2.
- **User Story 4 (Phase 6)**: Depende de Phase 2 y de los servicios creados en US2.
- **User Story 5 (Phase 7)**: Depende de Phase 2. Puede desarrollarse en paralelo con US3 o US4.
- **Polish (Phase 8)**: Depende de completar las historias prioritarias.

### Parallel Opportunities

- T002, T003 pueden ejecutarse en paralelo con T001 en Phase 1.
- T006, T007 pueden ejecutarse en paralelo con T005 en Phase 2.
- En Phase 3: T010 (schemas backend) y T014 (modal frontend) pueden desarrollarse en paralelo.
- En Phase 4: T016 (schemas) y T021 (modal de aprobación frontend) pueden desarrollarse en paralelo.
- US4 (Autogestión de servicios) y US5 (ABM de templates) son altamente independientes y pueden ejecutarse en paralelo una vez completada la fase Foundational.

---

## Implementation Strategy

### MVP Scope (Recomendado)
- **Fase 1 + Fase 2 + Fase 3 (US1) + Fase 4 (US2)**:
  - Permite a una cátedra solicitar recursos IaaS/PaaS/SaaS con vigencia.
  - Permite al Administrador evaluar y aprobar con despliegue automático en Proxmox.
  - Genera valor inmediato y demuestra el Happy Path completo.

### Incrementos Siguientes
- **Incremento 2 (Fase 5 - US3)**: Agrega robustez operativa con el rechazo justificado y el ciclo de ajuste colaborativo.
- **Incremento 3 (Fase 6 - US4)**: Otorga autonomía a los docentes para operar sus servicios activos y compartir accesos con alumnos.
- **Incremento 4 (Fase 7 - US5)**: Brinda flexibilidad al administrador para autogestionar el catálogo de templates.

