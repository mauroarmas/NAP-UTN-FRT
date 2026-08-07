# Plan de Trabajo y Pendientes - Proxmox Orchestration Workflow

El proyecto ha alcanzado un núcleo operativo sólido, incluyendo orquestación real con Proxmox, máquina de estados para pedidos, gestión de usuarios (CRUD/Roles), y observabilidad con captura de métricas y gráficos. 

A continuación se detalla el plan de trabajo para llevar el sistema a un nivel de producción "Enterprise", desglosado por tareas de **Frontend** y **Backend**.

---

## 1. Hitos y Tareas Pendientes (Especificaciones)

### Hito 1: Seguridad y Autenticación Fuerte (2FA)
Actualmente el backend soporta la generación y verificación de 2FA (TOTP), pero falta la integración completa en el flujo de usuario.

*   **Frontend:**
    *   **Pantalla de Perfil / Configuración:** Crear una vista o modal donde el usuario pueda solicitar habilitar 2FA. Mostrar el código QR generado por el backend usando una librería como `qrcode.react`.
    *   **Flujo de Login:** Modificar `Login.jsx` para soportar un proceso de dos pasos. Si el backend indica que el usuario tiene 2FA habilitado, mostrar un input para ingresar el token de Google Authenticator antes de conceder acceso al dashboard.
*   **Backend:**
    *   **Adaptación de Login:** Ajustar el endpoint `/api/v1/auth/login` para que, si el usuario requiere 2FA, emita un token temporal o un código de estado específico (ej. `206 Partial Content` o un flag en el JSON) en lugar del JWT final, hasta que se verifique el código.

### Hito 2: Trazabilidad y Logs de Auditoría
Para entornos académicos y multi-usuario, es crítico saber *quién* hizo *qué* y *cuándo*, especialmente con acciones destructivas.

*   **Backend:**
    *   **Modelo de Datos:** Crear la tabla y modelo `AuditLog` (ID, usuario_id, accion, recurso_tipo, recurso_id, detalle, timestamp).
    *   **Inyección de Logs:** Agregar registros de auditoría en los endpoints críticos: creación de usuarios, aprobación/rechazo de pedidos, y controles de ciclo de vida de contenedores (start, stop, delete).
    *   **API de Auditoría:** Crear un endpoint `GET /api/v1/auditoria/` para consultar el historial (con filtros por fecha o usuario).
*   **Frontend:**
    *   **Vista de Auditoría:** Crear una nueva página "Registro de Actividad" (exclusiva para rol Admin) que consuma el endpoint y muestre una tabla paginada y filtrable con los eventos del sistema.

### Hito 3: Refinamiento de la Máquina de Estados y UX
Mejorar el manejo de estados de error y el feedback visual que recibe el usuario al interactuar con el sistema.

*   **Frontend:**
    *   **Sistema de Notificaciones (Toasts):** Reemplazar los `alert()` nativos por una librería moderna de notificaciones (ej. `react-toastify` o `sonner`) para dar feedback asíncrono y no bloqueante tras despliegues, encendidos o errores.
    *   **Feedback de Carga Granular:** Implementar *spinners* o indicadores de carga específicos por fila en las tablas cuando una acción (como desplegar un contenedor) está en progreso, en lugar de bloquear toda la pantalla.
*   **Backend:**
    *   **Soft Delete:** Implementar eliminación lógica (flag `deleted_at`) en pedidos y servicios para mantener el historial académico de recursos consumidos por cátedras en años anteriores, aunque el CT se elimine en Proxmox.
    *   **Recuperación de Errores:** Añadir rutinas o endpoints para reintentar despliegues que quedaron atrapados en estado `ERROR`.

---

## 2. Sugerencias de Mejoras (Arquitectura y Escalabilidad)

Si se desea agregar valor técnico destacado (ideal para presentaciones académicas):

1.  **WebSockets para Tiempo Real (Backend & Frontend):** 
    *   Reemplazar el *polling* (peticiones HTTP cada 30s) en el dashboard de métricas por conexiones WebSocket en FastAPI. Esto permite empujar actualizaciones de estado de contenedores y métricas al instante, optimizando el tráfico de red.
2.  **Integración de Backups / Snapshots (Backend & Frontend):** 
    *   Exponer la API de VZDump de Proxmox. Agregar un botón "Solicitar Backup" en el Frontend para que una cátedra guarde el estado de su contenedor antes de una evaluación o entrega importante.
3.  **Límites de Uso Inteligentes (Backend):** 
    *   Implementar validaciones de *Overprovisioning*. Si la suma de cuotas de las cátedras excede la capacidad física real del nodo Proxmox, enviar alertas al administrador.

---

## 3. Plan de Pruebas (Testing Strategy)

Antes de un despliegue a producción, se recomienda ejecutar la siguiente batería de pruebas:

1.  **Pruebas Unitarias del Orquestador (Backend):**
    *   Usar `pytest` para hacer *mock* del cliente `proxmoxer`.
    *   Simular escenarios de fallo (ej. Proxmox devuelve error 500, o falla la clonación del template) y verificar que el sistema de estados cambie a `ERROR` de forma segura sin corromper la DB.
2.  **Pruebas de Seguridad y RBAC (Backend):**
    *   Escribir tests que intenten acceder a endpoints protegidos (ej. `/api/v1/servicios/desplegar`) usando tokens de usuarios con rol "Cátedra" para asegurar que el middleware rechaza la petición con un `403 Forbidden`.
3.  **Pruebas End-to-End (E2E):**
    *   Simular el ciclo de vida completo: Crear cátedra -> Asignar usuario -> Hacer pedido -> Aprobar pedido (despliegue) -> Verificar métricas -> Eliminar servicio.
    *   Validar rigurosamente que las cuotas de RAM/CPU/Disco se descuenten y restauren correctamente al crear y eliminar servicios.
4.  **Prueba de Estrés Ligera:**
    *   Aprobar múltiples pedidos simultáneamente para evaluar el manejo asíncrono y los timeouts entre FastAPI y el demonio de Proxmox.
