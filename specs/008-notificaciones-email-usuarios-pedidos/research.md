# Research & Technical Decisions: Notificaciones por Email y Gestión de Contraseñas Provisorias

**Feature Branch**: `008-notificaciones-email-usuarios-pedidos`  
**Date**: 2026-10-11  
**Spec**: [spec.md](./spec.md)

---

## 1. Transporte y Mecanismo de Envío de Correos Electrónicos

### Decisión
Utilizar la librería estándar de Python (`smtplib` y `email.message.EmailMessage`) empaquetada en un servicio modular (`app/services/email_service.py`), despachando los envíos a través de `BackgroundTasks` de FastAPI.

### Razón y Contexto
- **Sin dependencias externas pesadas**: La biblioteca estándar de Python maneja TLS (`starttls`), autenticación SMTP (`login`), codificación UTF-8 y armado de mensajes multiparte (`multipart/alternative` HTML + texto plano).
- **Despacho no bloqueante**: Los endpoints de FastAPI reciben `BackgroundTasks: BackgroundTasks` y encolan las tareas de envío (`background_tasks.add_task(email_service.enviar_..., ...)`). La respuesta HTTP se envía inmediatamente al cliente (cumpliendo SC-003 < 500 ms) mientras el hilo de fondo realiza la conexión SMTP y el envío.
- **Manejo de errores resiliente**: Si el servidor SMTP falla, la excepción se captura y se registra en logs con detalle sin voltear la transacción de base de datos ni provocar un error 500 al usuario.

### Alternativas Consideradas
- **Broker externo (Celery + Redis / RabbitMQ)**: Descartado por complejidad operativa innecesaria. La infraestructura actual no requiere un clúster de colas distribuidas para el volumen de pedidos de cátedras de la facultad.
- **Envío síncrono en el hilo de la petición**: Descartado porque las conexiones SMTP y handshakes TLS agregan entre 500 ms y 3 segundos de latencia a cada guardado en el portal.
- **Proveedores SaaS (Resend, SendGrid, AWS SES)**: Descartado por requisito explícito del proyecto institucional UTN FRT, que utiliza servidor de correo corporativo/académico propio vía SMTP.

---

## 2. Generación de Contraseña Provisoria y Flujo de Primer Ingreso

### Decisión
1. **Generación segura**: Emplear el módulo `secrets` de Python para generar una cadena pseudoaleatoria de 10 caracteres con letras mayúsculas, minúsculas, dígitos y símbolos legibles (evitando caracteres ambiguos como `0`, `O`, `l`, `I`).
2. **Persistencia y Hash**: La contraseña provisoria se hashea de inmediato con bcrypt (`get_password_hash`) y se almacena en `Usuario.password_hash`. El texto plano existe únicamente en memoria para el envío del correo de bienvenida y nunca se persiste.
3. **Control de Primer Ingreso**:
   - Nueva columna en tabla `usuarios`: `debe_cambiar_password: bool = True` para nuevos usuarios creados por el administrador.
   - Endpoint dedicado: `POST /api/v1/auth/cambiar-password-inicial` que requiere usuario autenticado, valida longitud mínima (8 caracteres), actualiza el hash y establece `debe_cambiar_password = False`.
4. **Bloqueo en Frontend**:
   - En `App.jsx` y sesión autenticada, si `user.debe_cambiar_password === true`, se renderiza un overlay modal bloqueante (`CambiarPasswordInicialModal`) que impide la navegación y el uso del portal hasta completar el cambio.

### Razón y Contexto
- Cumple con la mejor práctica de no almacenar ni exponer contraseñas en texto plano en la base de datos ni en respuestas JSON.
- Asegura que el usuario no pueda saltear el cambio cerrando pestañas o recargando la página.

### Alternativas Consideradas
- **Ingreso de contraseña manual por el administrador**: Descartado en el proceso de refinamiento (`/grill-me`), ya que exponía la credencial provisoria a la persona que daba el alta y generaba fricción.
- **Magic link / Token de reseteo temporal**: Descartado para alinearse con el flujo institucional donde el profesor recibe su usuario y contraseña provisoria y realiza el login formal en `/login`.

---

## 3. Preferencias de Notificación de Administradores

### Decisión
Agregar la columna `recibir_notificaciones_email: bool = True` en la tabla `usuarios`.
- Al listar administradores destinatarios para alertas (nuevo pedido, reenvío, fallos de infraestructura), se seleccionan los usuarios con `rol == 'admin'`, `activo == True`, `recibir_notificaciones_email == True` y `email IS NOT NULL`.
- En el frontend, el administrador puede editar esta opción desde su perfil o pantalla de edición de usuarios.

### Razón y Contexto
- Permite que administradores que no estén cumpliendo rol de guardia o atención de solicitudes puedan silenciar las notificaciones directas a su casilla personal.
- Mantiene la configuración ligada directamente al usuario sin necesidad de tablas complejas adicionales.

---

## 4. Matriz de Eventos y Plantillas de Correo para el Flujo de Pedidos

### Decisión
Se definen 6 tipos de correo con plantillas HTML institucionales y texto plano:

| Evento del Pedido | Disparador | Destinatarios | Contenido Clave |
|-------------------|------------|---------------|-----------------|
| **Bienvenida / Alta de usuario** | Admin crea usuario | Nuevo usuario | Username, contraseña provisoria, enlace al portal |
| **Nuevo Pedido / Reenviado** | Docente crea o reenvía pedido | Administradores suscritos | Cátedra, docente, modelo de servicio, vigencia, enlace al pedido |
| **Solicitud de Ajuste** | Admin cambia a `requiere_ajuste` | Docente solicitante | Observaciones del admin, enlace para editar pedido |
| **Aprobación / Despliegue Activo** | Despliegue exitoso a `activo` | Docente solicitante | Confirmación de servicio disponible, detalles de acceso |
| **Pedido Rechazado** | Admin rechaza pedido | Docente solicitante | Motivo formal de rechazo, enlace al historial |
| **Fallo de Despliegue** | Error técnico en Proxmox | Docente y Administradores | Detalle del error técnico, aviso de intervención |

### Razón y Contexto
- Acompaña fielmente las transiciones de la máquina de estados definida en `pedido_service.py` y `orquestacion_service.py` sin alterar el Principio II (la máquina de estados sigue siendo la única fuente de verdad; los correos son efectos secundarios no bloqueantes de las transiciones).

