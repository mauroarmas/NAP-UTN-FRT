# Tasks: Notificaciones por Email y Gestión de Contraseñas Provisorias

**Input**: Design documents from `specs/008-notificaciones-email-usuarios-pedidos/`  
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Format: `- [ ] [ID] [P?] [Story?] Description with exact file path`

- **[P]**: Ejecutable en paralelo (archivos independientes, sin dependencias bloqueantes)
- **[Story]**: Mapeo a historia de usuario de `spec.md` ([US1], [US2], [US3], [US4])

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuración base de transporte de correos y variables de entorno

- [x] T001 Configurar variables de entorno SMTP y URL de frontend en `backend/app/config.py`
- [x] T002 [P] Implementar módulo base de despacho de correos `app/services/email_service.py` con soporte SMTP y fallback de logs

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Esquema de datos, migraciones y dependencias compartidas necesarias para todas las historias

**⚠️ CRITICAL**: Completar esta fase antes de iniciar las fases de historias de usuario

- [x] T003 Agregar columnas `debe_cambiar_password` y `recibir_notificaciones_email` al modelo en `backend/app/models/usuario.py`
- [x] T004 Generar y aplicar migración de Alembic para nuevas columnas en `backend/alembic/versions/`
- [x] T005 [P] Actualizar esquemas Pydantic `UsuarioBase`, `UsuarioCreate`, `UsuarioUpdate` y `UsuarioResponse` en `backend/app/schemas/usuario.py`
- [x] T006 [P] Crear fixtures y mocks de prueba de correo en `backend/tests/conftest.py`

**Checkpoint**: Base de datos y configuración listas para implementar las historias de usuario.

---

## Phase 3: User Story 1 - Alta de Usuario con Contraseña Provisoria por Correo (Priority: P1) 🎯 MVP

**Goal**: Permitir al administrador crear nuevos usuarios sin ingresar contraseña manual, generando una clave provisoria aleatoria que se envía automáticamente por correo.

**Independent Test**: Crear un usuario con el botón "Nuevo usuario" desde el frontend; verificar que se guarda con `debe_cambiar_password = True` y que se despacha el correo de bienvenida con la contraseña provisoria.

### Tests for User Story 1
- [x] T007 [P] [US1] Crear pruebas unitarias y de integración para alta de usuario con clave provisoria y despacho de correo en `backend/tests/test_alta_usuario_password.py`

### Implementation for User Story 1
- [x] T008 [US1] Implementar generador criptográfico de contraseñas provisorias seguras en `backend/app/services/usuario_service.py`
- [x] T009 [US1] Modificar endpoint `POST /usuarios/` en `backend/app/routers/usuarios.py` para requerir email, generar clave provisoria, asignar `debe_cambiar_password=True` y despachar correo en `BackgroundTasks`
- [x] T010 [P] [US1] Actualizar función cliente `crearUsuario` en `frontend/src/services/api.js` para enviar datos de alta sin campo manual de contraseña
- [x] T011 [US1] Actualizar componente `frontend/src/pages/Usuarios.jsx` renombrando botón a "Nuevo usuario" (ícono `UserPlus`), quitando input de contraseña y haciendo email obligatorio

**Checkpoint**: User Story 1 completamente funcional de forma independiente (MVP alcanzado).

---

## Phase 4: User Story 2 - Primer Ingreso y Cambio Obligatorio de Contraseña (Priority: P1)

**Goal**: Exigir al usuario que ingrese por primera vez con su contraseña provisoria cambiarla de forma obligatoria antes de permitirle navegar o usar el portal.

**Independent Test**: Iniciar sesión con un usuario con `debe_cambiar_password = True`; verificar que la pantalla queda bloqueada por el modal obligatorio y que solo se desbloquea tras establecer una nueva clave válida.

### Tests for User Story 2
- [x] T012 [P] [US2] Crear pruebas automatizadas para el endpoint de cambio de clave inicial en `backend/tests/test_primer_login.py`

### Implementation for User Story 2
- [x] T013 [US2] Implementar esquema `CambiarPasswordInicialRequest` en `backend/app/schemas/auth.py` y endpoint `POST /api/v1/auth/cambiar-password-inicial` en `backend/app/routers/auth.py`
- [x] T014 [P] [US2] Crear componente modal bloqueante `frontend/src/components/CambiarPasswordInicialModal.jsx` con validaciones de contraseña y confirmación
- [x] T015 [US2] Integrar `CambiarPasswordInicialModal` en `frontend/src/App.jsx` para interceptar la sesión cuando `user.debe_cambiar_password === true`

**Checkpoint**: User Story 2 operativa e integrada con User Story 1.

---

## Phase 5: User Story 3 - Notificaciones por Correo en el Flujo de Pedidos (Priority: P2)

**Goal**: Despachar correos institucionales automáticos en cada hito del ciclo de vida de los pedidos (solicitud, solicitud de ajuste, reenvío, aprobación/activo, rechazo y fallo técnico).

**Independent Test**: Realizar transiciones en un pedido y comprobar que el solicitante y/o administradores reciben los correos con la información contextual correspondiente.

### Tests for User Story 3
- [x] T016 [P] [US3] Crear pruebas automatizadas de despacho de correos en transiciones de pedidos en `backend/tests/test_pedidos_notificaciones.py`

### Implementation for User Story 3
- [x] T017 [US3] Diseñar plantillas HTML institucionales UTN FRT y versión texto plano para eventos de pedidos en `backend/app/services/email_service.py`
- [x] T018 [US3] Conectar despacho de correo a administradores en creación y reenvío de pedidos en `backend/app/routers/pedidos.py`
- [x] T019 [US3] Conectar despacho de correo al solicitante en `solicitar_ajuste` y `rechazar_pedido` en `backend/app/routers/pedidos.py`
- [x] T020 [US3] Conectar despacho de correo al solicitante y admins en finalización de despliegue (`activo`) y fallos técnicos (`error`) en `backend/app/services/orquestacion_service.py`

**Checkpoint**: Notificaciones de pedidos funcionando en todas las transiciones del ciclo de vida.

---

## Phase 6: User Story 4 - Preferencias de Notificación de Administradores (Priority: P3)

**Goal**: Permitir a los administradores activar o desactivar la recepción de correos operativos desde su configuración.

**Independent Test**: Desactivar notificaciones para un administrador y verificar que no recibe correos ante un nuevo pedido.

### Tests for User Story 4
- [x] T021 [P] [US4] Crear pruebas unitarias para filtrado de administradores por preferencia de correo en `backend/tests/test_notificaciones_preferencias.py`

### Implementation for User Story 4
- [x] T022 [US4] Actualizar `actualizar_usuario` en `backend/app/routers/usuarios.py` para admitir actualización de `recibir_notificaciones_email`
- [x] T023 [US4] Actualizar función selectora de administradores en `backend/app/services/email_service.py` filtrando por `recibir_notificaciones_email.is_(True)`
- [x] T024 [P] [US4] Incorporar interruptor de activación/desactivación de notificaciones de correo en formulario de edición de `frontend/src/pages/Usuarios.jsx`

**Checkpoint**: Todas las historias de usuario implementadas y configurables.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verificación integral, pruebas de regresión y validación end-to-end

- [x] T025 [P] Ejecutar la suite completa de tests de backend con `backend/venv/bin/pytest backend/tests/`
- [x] T026 Ejecutar validación manual end-to-end siguiendo los escenarios de `quickstart.md`
- [x] T027 [P] Actualizar documentación de configuración de correo en `backend/README.md`

---

## Dependencies & Execution Order

### Phase Dependencies
1. **Setup (Phase 1)**: Sin dependencias, arranca inmediatamente.
2. **Foundational (Phase 2)**: Depende de Phase 1; bloquea todas las historias de usuario.
3. **User Story 1 (Phase 3)**: Depende de Phase 2. MVP inicial.
4. **User Story 2 (Phase 4)**: Depende de Phase 2 y se integra con US1.
5. **User Story 3 (Phase 5)**: Depende de Phase 2 y servicio de email de Phase 1.
6. **User Story 4 (Phase 6)**: Depende de Phase 2 y Phase 5.
7. **Polish (Phase 7)**: Depende de la finalización de las fases deseadas.

### Parallel Opportunities
- **En Phase 1**: T001 y T002 pueden correr en paralelo.
- **En Phase 2**: T005 y T006 pueden desarrollarse en paralelo tras T003/T004.
- **En Phase 3 (US1)**: Pruebas (T007) y llamadas frontend (T010) en paralelo con backend (T008/T009).
- **En Phase 4 (US2)**: Pruebas backend (T012) y componente modal (T014) en paralelo con endpoint (T013).
- **En Phase 5 (US3)**: Pruebas (T016) en paralelo con diseño de plantillas (T017).

---

## Implementation Strategy

### MVP First (User Story 1 & 2)
1. Ejecutar Phase 1 (Setup SMTP) y Phase 2 (Modelo y migraciones).
2. Implementar Phase 3 (Alta de usuario y envío de clave provisoria).
3. Implementar Phase 4 (Primer login y cambio forzado de clave).
4. Validar flujo completo de credenciales provisorias.
5. Continuar incrementalmente con Phase 5 (Notificaciones de pedidos) y Phase 6 (Preferencias de admin).

