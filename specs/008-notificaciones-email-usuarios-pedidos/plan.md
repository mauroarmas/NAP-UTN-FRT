# Implementation Plan: Notificaciones por Email y Gestión de Contraseñas Provisorias

**Branch**: `008-notificaciones-email-usuarios-pedidos` | **Date**: 2026-10-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-notificaciones-email-usuarios-pedidos/spec.md`

## Summary

Implementar un servicio de notificaciones por correo electrónico institucional (SMTP) y un flujo de aprovisionamiento de credenciales provisorias para nuevos usuarios. Al dar de alta un usuario desde el panel de administración, el sistema genera automáticamente una contraseña provisoria segura y la envía por correo. Durante el primer inicio de sesión, el usuario es bloqueado obligatoriamente por una pantalla modal hasta que establezca su nueva contraseña definitiva. Adicionalmente, el ciclo de vida de los pedidos dispara notificaciones automáticas por correo (solicitud, solicitud de ajustes, reenvío, aprobación/activo, rechazo y errores técnicos de despliegue) a los docentes y a los administradores suscritos.

---

## Technical Context

**Language/Version**: Python 3.12 (Backend) / JavaScript ES2022 + React 18 (Frontend)  
**Primary Dependencies**:
- Backend: FastAPI 0.115, SQLAlchemy 2.0 (asyncpg), Alembic, Pydantic-settings, passlib (bcrypt), python `smtplib` (std lib), `email.message` (std lib).
- Frontend: React 18, Vite, React Router 6, Lucide React, Axios.  
**Storage**: PostgreSQL (asyncpg) con migración de Alembic para columnas `debe_cambiar_password` y `recibir_notificaciones_email` en tabla `usuarios`.  
**Testing**: `pytest` con `pytest-asyncio` y fixtures de mock para el servicio de correo SMTP.  
**Target Platform**: Linux (Ubuntu 22.04 / 24.04), navegadores web modernos (Chrome, Firefox, Edge).  
**Project Type**: Aplicación web completa (Backend API REST + Frontend SPA).  
**Performance Goals**: Despacho asíncrono no bloqueante vía FastAPI `BackgroundTasks` manteniendo tiempos de respuesta HTTP de alta de usuario y transición de estados por debajo de 500 ms (SC-003).  
**Constraints**: Entorno institucional UTN FRT; soporte para servidor SMTP con TLS; formato dual (HTML con identidad institucional + texto plano).  
**Scale/Scope**: ~100 cátedras y docentes, 5-10 administradores de sistemas, decenas de pedidos por ciclo lectivo.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento | Justificación |
|---|---|---|
| **I. Proxmox es el back-end, nunca la interfaz** | ✅ PASS | Las notificaciones y la gestión de usuarios operan exclusivamente en la capa de servicios de la aplicación (`app/services/`). No hay interacción directa con Proxmox en los routers. |
| **II. La máquina de estados es la única fuente de verdad** | ✅ PASS | Todo envío de correo sobre pedidos responde a transiciones ejecutadas por `cambiar_estado` o el orquestador. Las notificaciones no alteran los estados ni crean transiciones ficticias. |
| **III. Operación recuperable** | ✅ PASS | Los fallos en el transporte SMTP no cancelan transacciones de base de datos ni crean estados inconsistentes; los errores se atrapan y registran en logs. |
| **IV. Aislamiento por cátedra y control de capacidad** | ✅ PASS | Se mantiene la regla estricta de que los docentes deben pertenecer a sus cátedras asignadas para ver u operar recursos. La capacidad sigue controlándose indivisiblemente al aprobar. |
| **V. El historial académico no se destruye** | ✅ PASS | Ningún dato histórico ni registro de transiciones se altera o destruye. Los usuarios dados de baja no reciben correos. |

---

## Project Structure

### Documentation (this feature)

```text
specs/008-notificaciones-email-usuarios-pedidos/
├── plan.md              # Plan de implementación y contexto técnico
├── research.md          # Decisiones técnicas y análisis de alternativas
├── data-model.md        # Entidades, configuración y diagrama de flujo
├── quickstart.md        # Guía de verificación paso a paso
├── contracts/           # Contratos OpenAPI de endpoints involucrados
│   ├── auth-cambio-password.json
│   └── usuarios-api.json
└── checklists/
    └── requirements.md  # Checklist de validación de calidad de requisitos
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── <timestamp>_notificaciones_y_password_provisoria.py
├── app/
│   ├── config.py                 # Variables SMTP y URL del frontend
│   ├── models/
│   │   └── usuario.py            # Columnas debe_cambiar_password y recibir_notificaciones_email
│   ├── schemas/
│   │   ├── auth.py               # Schema CambiarPasswordInicialRequest
│   │   └── usuario.py            # Actualización de UsuarioCreate y UsuarioUpdate
│   ├── services/
│   │   ├── email_service.py      # Servicio de armado de plantillas y despacho SMTP
│   │   ├── usuario_service.py    # Generación segura de clave provisoria
│   │   ├── pedido_service.py     # Integración de envíos en transiciones
│   │   └── orquestacion_service.py # Integración de envíos en activo/error
│   └── routers/
│       ├── auth.py               # Endpoint POST /auth/cambiar-password-inicial
│       ├── usuarios.py           # Endpoint POST /usuarios (nuevo usuario con email)
│       └── pedidos.py            # Despacho de notificaciones en endpoints de pedidos
└── tests/
    ├── test_email_service.py
    └── test_alta_usuario_password.py

frontend/
├── src/
│   ├── services/
│   │   └── api.js                # Funciones cambiarPasswordInicial y crearUsuario
│   ├── components/
│   │   └── CambiarPasswordInicialModal.jsx # Modal obligatorio de primer ingreso
│   ├── pages/
│   │   └── Usuarios.jsx          # Botón "Nuevo usuario", formulario sin clave manual
│   └── App.jsx                   # Renderizado condicional del modal de primer ingreso
```

---

## Complexity Tracking

*No se detectan violaciones a la constitución ni desviaciones arquitectónicas innecesarias.*
