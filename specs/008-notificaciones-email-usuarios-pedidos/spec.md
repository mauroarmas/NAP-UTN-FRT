# Feature Specification: Notificaciones por Email y Gestión de Contraseñas Provisorias

**Feature Branch**: `008-notificaciones-email-usuarios-pedidos`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description: "Vamos a trabajar en los emails y la gestión de usuarios por parte del administrador: 1. primero un admin creará al usuario con el botón 'Nuevo usuario' y le asignará cátedras; el sistema genera una contraseña provisoria que llega por correo. 2. El usuario ingresará con esa contraseña provisoria y el sistema le pedirá cambiarla obligatoriamente si es la primera vez. 3. Gestión de correos en el flujo de pedidos (solicitud, aprobación/activo, ajustes, rechazo, errores técnicos)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Alta de Usuario con Contraseña Provisoria Automática por Correo (Priority: P1)

Como administrador del sistema,
quiero dar de alta a un nuevo docente o responsable de cátedra ingresando sus datos personales y asignándole cátedras sin tener que inventar ni tipear manualmente una contraseña,
para que el sistema genere automáticamente una credencial provisoria segura y se la envíe directamente por correo electrónico institucional.

**Why this priority**: Es el punto de entrada para la incorporación de docentes al portal. Garantiza que las cuentas se inicialicen de manera segura y automática, eliminando la necesidad de compartir contraseñas en texto plano por canales inseguros.

**Independent Test**: Puede probarse creando una cuenta de usuario desde el panel de administración; el sistema almacena el usuario con estado de cambio de clave pendiente y despacha un correo de bienvenida con la contraseña provisoria generada.

**Acceptance Scenarios**:

1. **Given** un administrador autenticado en el panel de gestión de usuarios, **When** presiona el botón "Nuevo usuario", completa nombre, nombre de usuario, correo electrónico válido, rol y cátedra(s) asignada(s), y confirma la creación, **Then** el sistema da de alta al usuario, marca la cuenta con cambio de contraseña obligatorio y envía un correo electrónico de bienvenida que contiene el nombre de usuario, la contraseña provisoria y el enlace de acceso al portal.
2. **Given** un administrador creando un usuario con rol de responsable de cátedra, **When** intenta guardarlo sin proporcionar un correo electrónico o sin asignarle al menos una cátedra, **Then** el sistema rechaza la operación informando los campos obligatorios faltantes y no crea el usuario.
3. **Given** un administrador creando un usuario, **When** el correo o nombre de usuario ya pertenecen a otra cuenta existente, **Then** el sistema rechaza la operación por conflicto y no emite correos.

---

### User Story 2 - Primer Ingreso y Cambio Obligatorio de Contraseña (Priority: P1)

Como nuevo responsable de cátedra que recibió una contraseña provisoria por correo,
quiero iniciar sesión en el portal y que el sistema me obligue a definir mi contraseña personal definitiva antes de permitirme operar,
para asegurar la confidencialidad de mi cuenta y garantizar que la credencial provisoria no vuelva a utilizarse.

**Why this priority**: Es el complemento de seguridad indispensable del alta de usuario. Sin este paso forzado, las cuentas quedarían expuestas indefinidamente con credenciales provisorias.

**Independent Test**: Iniciar sesión con un usuario recién creado y verificar que la interfaz bloquea el acceso a todas las secciones operativas hasta que se ingrese y confirme una contraseña nueva válida.

**Acceptance Scenarios**:

1. **Given** un usuario que posee una contraseña provisoria y el flag de cambio obligatorio activo, **When** inicia sesión con su nombre de usuario y contraseña provisoria, **Then** el sistema valida las credenciales y le presenta inmediatamente una pantalla modal obligatoria de cambio de contraseña sin permitirle navegar a otras secciones.
2. **Given** un usuario en la pantalla obligatoria de cambio de contraseña, **When** ingresa su nueva contraseña y su confirmación cumpliendo los requisitos mínimos de seguridad (mínimo 8 caracteres) y confirma, **Then** el sistema actualiza su contraseña definitiva, desactiva la condición de cambio obligatorio, desbloquea el portal y le permite operar normalmente.
3. **Given** un usuario en la pantalla obligatoria de cambio de contraseña, **When** ingresa contraseñas que no coinciden o no cumplen la longitud mínima, **Then** el sistema rechaza el cambio, muestra un mensaje descriptivo de validación y mantiene el bloqueo.

---

### User Story 3 - Notificaciones por Correo en el Flujo de Pedidos (Priority: P2)

Como docente o administrador del sistema,
quiero recibir notificaciones oportunas por correo electrónico ante cada evento relevante del ciclo de vida de un pedido de recursos,
para estar informado de solicitudes pendientes, observaciones de ajuste, aprobaciones, disponibilidad efectiva del servicio o fallos técnicos sin tener que monitorear el portal constantemente.

**Why this priority**: Conecta la comunicación entre la cátedra y el centro de cómputos en tiempo real, agilizando los tiempos de respuesta y reduciendo la incertidumbre sobre el estado de las solicitudes.

**Independent Test**: Ejecutar cada transición del ciclo de vida de un pedido (creación, solicitud de ajuste, reenvío, aprobación, despliegue completado, rechazo y fallo) y comprobar que el destinatario correspondiente recibe el correo con la información contextual requerida.

**Acceptance Scenarios**:

1. **Given** un docente que envía un nuevo pedido o reenvía un pedido corregido, **When** se confirma la solicitud, **Then** el sistema envía un correo a los administradores activos informando que hay una solicitud pendiente de revisión, detallando cátedra, solicitante y recursos requeridos.
2. **Given** un administrador que solicita ajustes sobre un pedido, **When** registra las observaciones requeridas, **Then** el sistema envía un correo al docente solicitante con el detalle de las observaciones y un enlace directo para revisar y ajustar su pedido.
3. **Given** un administrador que aprueba un pedido y el servicio se despliega exitosamente a estado activo, **When** el servicio queda operativo, **Then** el sistema envía un correo al docente informando que su servicio se encuentra disponible junto con los datos de acceso pertinentes.
4. **Given** un administrador que rechaza un pedido, **When** ingresa el motivo del rechazo y confirma, **Then** el sistema envía un correo al docente con la notificación del rechazo y la justificación administrativa brindada.
5. **Given** un pedido en proceso de despliegue que sufre un fallo técnico irrecuperable en la infraestructura, **When** el pedido pasa a estado de error, **Then** el sistema despacha una alerta por correo a los administradores y al solicitante indicando el incidente.

---

### User Story 4 - Preferencias de Notificación de Administradores (Priority: P3)

Como administrador del sistema,
quiero poder activar o desactivar la recepción de correos de notificación operativa desde mi perfil o configuración de usuario,
para gestionar mi bandeja de entrada según mi asignación de guardia o responsabilidades actuales sin afectar a otros administradores.

**Why this priority**: Evita la saturación de correos para administradores que no estén a cargo directo de la atención de pedidos y permite que la distribución de alertas sea flexible.

**Independent Test**: Desactivar las notificaciones en el perfil de un administrador, crear un pedido con un docente y verificar que dicho administrador no recibe el correo, mientras que los administradores con la opción activa sí lo reciben.

**Acceptance Scenarios**:

1. **Given** un administrador con notificaciones activadas, **When** modifica su preferencia en su perfil a "desactivadas" y guarda los cambios, **Then** el sistema deja de enviarle correos ante nuevos pedidos o eventos del sistema.
2. **Given** un nuevo pedido creado por una cátedra, **When** el sistema resuelve la lista de destinatarios administrativos, **Then** envía el correo únicamente a aquellos administradores que tengan la cuenta activa y la preferencia de recepción de notificaciones habilitada.

---

### Edge Cases

- **Fallo temporal en el servidor de correo**: Si el servidor SMTP no responde o rechaza la conexión, la operación principal del usuario (alta de cuenta, aprobación de pedido, etc.) debe completarse con éxito en el sistema sin cancelarse por el fallo del transporte de correo, registrando el error en los registros de auditoría del sistema para permitir reenvíos o diagnóstico técnico.
- **Acceso concurrente o recarga durante primer ingreso**: Si el usuario recarga la página o abre una nueva pestaña antes de cambiar su clave provisoria, el sistema mantiene el bloqueo en pantalla de manera persistente impidiendo cualquier acción hasta que se concrete el cambio.
- **Usuario dado de baja**: Si una cuenta con rol docente o administrador es dada de baja, queda excluida automáticamente del envío de cualquier notificación por correo posterior.
- **Correos con caracteres especiales o tildes**: Todos los nombres de cátedras, docentes y motivos de rechazo/ajuste deben codificarse adecuadamente en formato UTF-8 para garantizar legibilidad en clientes de correo web y de escritorio.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE proporcionar en el panel de usuarios un botón claramente rotulado "Nuevo usuario" que abra el formulario de alta.
- **FR-002**: El formulario de alta DEBE requerir obligatoriamente: nombre completo, nombre de usuario y correo electrónico válido.
- **FR-003**: Al crear un usuario con rol de responsable de cátedra, el sistema DEBE exigir la asignación de al menos una cátedra académica.
- **FR-004**: Al crear un nuevo usuario, el sistema DEBE generar de manera autónoma una contraseña provisoria aleatoria de alta entropía y almacenarla de forma segura mediante funciones de hashing criptográfico.
- **FR-005**: Al crearse un usuario, el sistema DEBE marcar la cuenta con la condición de cambio obligatorio de contraseña (`debe_cambiar_password = True`).
- **FR-006**: El sistema DEBE despachar un correo de bienvenida al destinatario recién creado que contenga su nombre de usuario, la contraseña provisoria asignada y el enlace al portal.
- **FR-007**: Tras un inicio de sesión exitoso con una contraseña provisoria, el sistema DEBE bloquear la navegación ordinaria y presentar una pantalla modal obligatoria de cambio de contraseña.
- **FR-008**: La pantalla de cambio de contraseña DEBE requerir el ingreso de una nueva contraseña y su confirmación idéntica, con una longitud mínima de 8 caracteres.
- **FR-009**: Al procesar satisfactoriamente el cambio de contraseña, el sistema DEBE actualizar la credencial permanente, desactivar el indicador de cambio obligatorio y habilitar el acceso regular al portal.
- **FR-010**: El sistema DEBE enviar un correo a los administradores suscritos cuando se crea un nuevo pedido o se reenvía un pedido tras ajustes.
- **FR-011**: El sistema DEBE enviar un correo al solicitante cuando su pedido requiera ajustes, incluyendo el texto de las observaciones ingresadas por el administrador.
- **FR-012**: El sistema DEBE enviar un correo al solicitante cuando su pedido haya sido aprobado y el servicio resultante esté desplegado y disponible.
- **FR-013**: El sistema DEBE enviar un correo al solicitante cuando su pedido sea rechazado, incorporando el motivo formal de rechazo.
- **FR-014**: El sistema DEBE enviar una alerta por correo a administradores y al solicitante si ocurre un error irrecuperable en el despliegue del pedido.
- **FR-015**: Los correos electrónicos DEBEN emitirse en formato dual (HTML con identidad institucional de la UTN FRT y versión alternativa en texto plano).
- **FR-016**: El sistema DEBE permitir a los usuarios administradores activar o desactivar la recepción de correos de notificación en sus preferencias de perfil.
- **FR-017**: Las tareas de envío de correos DEBEN ejecutarse de forma no bloqueante respecto de las respuestas directas de la interfaz de usuario.

---

### Key Entities *(include if feature involves data)*

- **Usuario**: Representa la cuenta de acceso al portal. Incorpora el atributo de cambio obligatorio de contraseña (`debe_cambiar_password`) y el atributo de preferencia para recibir notificaciones por correo (`recibir_notificaciones_email`).
- **Pedido**: Representa la solicitud de infraestructura de una cátedra. Su ciclo de vida dispara eventos de notificación vinculados a su solicitante y a los administradores del centro de cómputos.
- **PlantillaCorreo**: Estructura de contenido que define el asunto, mensaje en texto plano y versión visual en HTML institucional para cada tipo de evento del sistema (Bienvenida/Clave provisoria, Pedido solicitado, Ajustes requeridos, Pedido aprobado/activo, Pedido rechazado y Error de despliegue).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las altas de usuarios generan y envían una contraseña provisoria aleatoria sin intervención manual de tipado de credenciales por parte del administrador.
- **SC-002**: Ningún usuario con contraseña provisoria puede navegar ni ejecutar acciones operativas en el portal antes de establecer exitosamente su clave definitiva (0% de accesos permitidos sin cambio de clave).
- **SC-003**: El tiempo percibido de respuesta en la interfaz de usuario al dar de alta un usuario o cambiar el estado de un pedido no se incrementa por el envío de correos, manteniéndose por debajo de 500 ms en condiciones normales.
- **SC-004**: Los destinatarios correspondientes reciben la notificación por correo de cada evento del flujo de pedidos dentro de los 60 segundos posteriores a la acción en el portal, siempre que el servicio de correo se encuentre operativo.
- **SC-005**: Los administradores que desactiven sus notificaciones de correo en su perfil dejan de recibir el 100% de los correos operativos de nuevos pedidos.

---

## Assumptions

- Se dispone de un servidor o agente de retransmisión de correo (SMTP institucional) accesible por el backend con credenciales válidas provistas mediante configuración del entorno.
- Las direcciones de correo electrónico ingresadas para los docentes son válidas y pueden recibir correos externos o institucionales.
- La identidad visual de los correos utiliza el encabezado y estilos institucionales estándar de la Facultad Regional Tucumán (UTN FRT).
- El portal web cuenta con una URL pública o accesible institucionalmente configurada para componer los enlaces de acceso directo incluidos en los correos.

