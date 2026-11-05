# Feature Specification: Terminal web de la consola dentro del portal

**Feature Branch**: `022-terminal-web-portal`

**Created**: 2026-11-04

**Status**: Implementada (pendiente de revisión del PR)

**Input**: User description: "Terminal web de la consola dentro del portal, sin que la persona entre a Proxmox. Hoy, para abrir la consola de su Linux IaaS, la persona debe iniciar sesión en la interfaz de Proxmox del nodo con su identidad individual y recién entonces abrir la consola; además un operador crea esas identidades y sus permisos a mano. Se quiere que la persona abra una terminal dentro del propio portal (botón de consola en «Ver acceso») y trabaje en su contenedor sin ver nunca Proxmox, sin necesitar red al puerto de los nodos ni certificados de los nodos, y sin credenciales de Proxmox. El portal abre la consola del contenedor por detrás con la identidad individual de la persona y se la muestra en una terminal web propia; sólo ella ve esa terminal. Las identidades individuales (una por persona, nunca compartidas, con permisos sólo de consola sobre el pool de cada cátedra) deben crearse y retirarse automáticamente cuando la persona se asigna o se retira de una cátedra, con una contraseña aleatoria que guarda el portal cifrada y que la persona nunca ve, mediante acciones cerradas del runner del nodo (no un token de Proxmox con permisos amplios). El retiro conserva la prueba de revocación de la feature 020. Debe funcionar sin importar el nodo que aloja el contenedor, con tiempo máximo de inactividad, límite de sesiones simultáneas por persona, cierre inmediato al retirar el acceso o dar de baja el servicio, y auditoría de aperturas y cierres sin guardar el contenido de la terminal. Se entra al contenedor con el usuario nap de la feature 021. Fuera de alcance: transferencia de archivos, grabación o reproducción de sesiones, compartir una terminal entre personas, otros usuarios del contenedor, Docker/OCI, SSH desde el navegador. Decisión pendiente del equipo, no de esta feature: si al cumplirse se retira la excepción de consola de la constitución."

<!-- Principio I: esta feature es la forma de dejar de derivar a Proxmox. Mientras el equipo no decida retirar la excepción de consola,
     se conserva como respaldo; ver «Impacto en la constitución». Principio VII: la persona no aporta datos nuevos y no ve nada de
     infraestructura. Principio IV: el aislamiento por cátedra se mantiene por identidad individual y pool, y además se verifica en el portal. -->

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Abrir mi terminal dentro del portal (Priority: P1)

Una persona de cátedra tiene un servicio Linux encendido y vigente. En «Ver acceso» pulsa el botón de consola y se abre, dentro del propio portal, una terminal con el contenedor. Inicia sesión con el usuario `nap` y la contraseña de «Revelar acceso inicial», trabaja con `sudo` y cierra la pestaña cuando termina. En ningún momento ve una pantalla de Proxmox, ni necesita iniciar sesión en otro sistema, ni tiene alcance de red a los nodos: sólo al portal.

**Why this priority**: Es el resultado pedido. Hoy abrir la consola exige una segunda autenticación en una interfaz de infraestructura que la persona no debería conocer.

**Independent Test**: Con la persona conectada sólo al portal (sin acceso a los nodos), abrir la terminal de un Linux de cada nodo, iniciar sesión como `nap` y ejecutar un comando con `sudo`.

**Acceptance Scenarios**:

1. **Given** una persona con acceso a su servicio, encendido y con vigencia, **When** pulsa el botón de consola, **Then** se abre una terminal en el portal con el prompt de inicio de sesión del contenedor, sin pedir ninguna credencial de infraestructura.
2. **Given** una persona sin conectividad hacia los nodos ni confianza en sus certificados, **When** abre la terminal, **Then** funciona igual.
3. **Given** servicios alojados en nodos distintos, **When** la persona abre la terminal de cada uno, **Then** el recorrido es idéntico y no depende de qué nodo lo aloja.
4. **Given** la terminal abierta, **When** la persona redimensiona la ventana, copia y pega texto o usa las teclas habituales de una terminal, **Then** el comportamiento es el esperado de una terminal real.
5. **Given** otra persona (de la misma o de otra cátedra) sin acceso a ese servicio, **When** intenta abrir su terminal, **Then** es rechazada y nunca recibe ni ve contenido de esa terminal.
6. **Given** un servicio detenido o sin vigencia, **When** se pulsa el botón de consola, **Then** se explica el motivo en lenguaje llano y no se abre nada.

---

### User Story 2 - Las identidades de consola se crean y se retiran solas (Priority: P1)

Cuando administración asigna a una persona a una cátedra, el portal le prepara automáticamente su identidad individual de consola en la infraestructura, limitada a lo que necesita para abrir terminales de los servicios de esa cátedra. Cuando la persona se retira de la cátedra o se da de baja, el acceso se retira de verdad: las terminales abiertas se cortan, ningún acceso guardado sirve y lo que tenga en otras cátedras se conserva. Nadie ve ni maneja la contraseña de esa identidad.

**Why this priority**: Sin aprovisionamiento automático, la terminal del portal seguiría dependiendo de que un operador cree identidades a mano. Es condición del resultado de la historia 1 y evita errores de seguridad por tareas manuales.

**Independent Test**: Asignar a una persona nueva a una cátedra y abrir su terminal sin ninguna intervención manual; retirarla y comprobar que una terminal abierta se corta, que no puede abrir otra, y que su otra cátedra sigue funcionando.

**Acceptance Scenarios**:

1. **Given** una persona nueva asignada a una cátedra, **When** administración confirma la asignación, **Then** la identidad queda lista sin pasos manuales y la persona puede abrir terminales de los servicios de esa cátedra.
2. **Given** una persona con dos cátedras, **When** se retira de una, **Then** puede seguir abriendo terminales de la otra y ninguna de la retirada.
3. **Given** una persona con una terminal abierta, **When** se le retira el acceso al servicio o a la cátedra, **Then** esa terminal se corta de inmediato con un aviso comprensible y no puede reabrirse.
4. **Given** la identidad de una persona, **When** administración consulta su estado, **Then** ve si está lista, en preparación, con error o retirada, sin ver credenciales.
5. **Given** un fallo al preparar o retirar una identidad, **When** se reintenta, **Then** el resultado converge sin duplicar identidades ni dejar permisos a medias, y mientras no se confirma el retiro no se entrega acceso nuevo a quien lo reemplaza.
6. **Given** dos personas distintas, **When** se les prepara acceso, **Then** nunca comparten identidad ni contraseña.

---

### User Story 3 - Sesiones acotadas y auditables (Priority: P1)

Las terminales son un acceso de alto privilegio sobre un contenedor, así que están acotadas: se cierran solas tras un tiempo de inactividad, cada persona tiene un máximo de terminales simultáneas, se cortan al dar de baja el servicio y cada apertura y cierre queda registrado sin guardar nunca lo que se escribe ni lo que se ve.

**Why this priority**: Es lo que vuelve aceptable ofrecer una terminal web con credenciales intermediadas por el portal; sin límites ni auditoría el riesgo supera al beneficio.

**Independent Test**: Dejar una terminal inactiva hasta que se cierre; abrir terminales hasta el límite y comprobar el rechazo de la siguiente; dar de baja el servicio con una terminal abierta; revisar la auditoría y buscar en ella el texto escrito en la terminal.

**Acceptance Scenarios**:

1. **Given** una terminal sin actividad durante el tiempo máximo, **When** transcurre, **Then** se cierra con un aviso y la persona puede abrir otra.
2. **Given** una persona con el máximo de terminales abiertas, **When** pide otra, **Then** se le explica el límite y se le ofrece cerrar una existente.
3. **Given** una terminal abierta, **When** se da de baja o se detiene el servicio, **Then** la terminal se cierra de inmediato con un aviso.
4. **Given** cualquier apertura o cierre, **When** se consulta la auditoría, **Then** constan quién, qué servicio, cuándo, cuánto duró y por qué se cerró, y no consta nada de lo escrito ni mostrado en la terminal.
5. **Given** la pérdida momentánea de conexión del navegador, **When** se restablece, **Then** la persona recibe un aviso claro y, si la terminal se cerró, puede abrir otra sin consecuencias.

---

### User Story 4 - Pasar a las personas ya existentes y operar el cambio (Priority: P2)

Las personas que hoy ya tienen una identidad creada a mano pasan al modelo automático sin perder acceso, y el equipo de infraestructura de la universidad dispone de un procedimiento claro para habilitar la terminal en su instalación, con la misma prueba de revocación exigida por la feature 020.

**Why this priority**: Cierra la transición y permite replicarlo; depende de las historias anteriores.

**Independent Test**: Con una persona que tiene una identidad manual, ejecutar el paso de adopción y comprobar que abre la terminal sin intervenir, y que la identidad manual anterior deja de existir; seguir el procedimiento en un clúster de prueba.

**Acceptance Scenarios**:

1. **Given** una persona con identidad creada a mano, **When** se aplica el cambio, **Then** conserva su acceso a la terminal y la identidad queda administrada por el portal.
2. **Given** la instalación sin haber demostrado la revocación, **When** se intenta habilitar la terminal, **Then** permanece cerrada (como en la feature 020).
3. **Given** el procedimiento de habilitación, **When** lo sigue alguien que no participó, **Then** puede completarlo sin valores del laboratorio ni ayuda de quien lo escribió.

---

### Edge Cases

- El nodo por el que el portal intenta abrir la consola no responde: se prueba con otro nodo del clúster; si ninguno responde se explica que no está disponible ahora y se permite reintentar.
- La primera apertura tras iniciar un contenedor se corta una vez (intermitencia ya observada): el portal reintenta una vez de forma transparente antes de avisar a la persona.
- La persona cierra el navegador sin cerrar la terminal: la sesión termina por inactividad o al detectar la desconexión; no queda una sesión huérfana consumiendo cupo.
- La persona abre varias pestañas: cada una cuenta como sesión para el límite.
- Se reinicia el portal con terminales abiertas: se cortan con aviso; no hay sesiones fantasma ni recursos retenidos.
- Se retira el acceso mientras la persona pega un texto largo: el corte es inmediato y no se escribe más en el contenedor.
- Se desactiva o retira la cuenta de la persona con terminales abiertas: se cortan y no puede abrir otras.
- Una persona sin identidad lista (en preparación o con error): se le informa «todavía no está habilitado» sin detalles de infraestructura y no se ofrece otra vía.
- Contenedor de cátedra con muchas personas: el límite de sesiones es por persona y la capacidad total del portal queda acotada.
- Texto muy extenso o binario en la terminal: no degrada al portal ni a otras sesiones.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El portal MUST ofrecer una terminal web de la consola de un Linux IaaS dentro de sus propias pantallas; la persona MUST NO ver, ni ser redirigida a, ninguna interfaz de la infraestructura.
- **FR-002**: La terminal MUST funcionar con una persona que sólo tiene alcance de red al portal: sin conectividad a los nodos, sin confianza en sus certificados y sin credenciales de infraestructura.
- **FR-003**: El portal MUST verificar la pertenencia del servicio a la cátedra de la persona antes de abrir la terminal y MUST NOT delegar esa comprobación en la infraestructura; sólo quien abre la terminal puede ver su contenido.
- **FR-004**: La terminal MUST abrirse con el mismo recorrido para servicios alojados en cualquier nodo del clúster, y MUST probar otro nodo del clúster si el habitual no responde, fallando con un mensaje claro si ninguno responde.
- **FR-005**: La terminal MUST sólo ofrecerse para servicios encendidos, con vigencia y con identidad de infraestructura confirmada; en otro caso MUST explicar el motivo en lenguaje llano.
- **FR-006**: La terminal MUST comportarse como una terminal real (entrada y salida interactivas, redimensionado, copiar y pegar, caracteres de control y codificación de texto habituales).
- **FR-007**: La sesión dentro del contenedor MUST seguir siendo con el usuario `nap` y la contraseña de «Revelar acceso inicial» (feature 021); esta feature no crea otros usuarios ni inicia sesión por la persona.
- **FR-008**: Cada persona MUST tener una identidad individual de consola, nunca compartida, con permisos sólo de consola (y la lectura mínima necesaria) sobre los servicios de las cátedras a las que pertenece, y ningún otro permiso en la infraestructura.
- **FR-009**: La identidad MUST crearse automáticamente al asignar a la persona a una cátedra y retirarse al retirarla o darla de baja, con las acciones cerradas y verificadas del nodo; el portal MUST NOT usar credenciales de infraestructura con permisos amplios para esto.
- **FR-010**: La contraseña de cada identidad MUST ser aleatoria, guardarse cifrada, y MUST NOT mostrarse a persona alguna ni aparecer en registros, errores ni auditoría.
- **FR-011**: Crear y retirar identidades MUST ser idempotente y recuperable: un resultado incierto se reintenta sin duplicar identidades ni dejar permisos a medias; un fallo deja el estado anterior consistente y visible para administración.
- **FR-012**: Al retirar el acceso, el portal y la infraestructura MUST cortar de inmediato las terminales abiertas, invalidar cualquier acceso guardado y conservar los accesos de otras cátedras de la persona, conforme a la prueba de revocación de la feature 020 (sesiones terminadas en todos los nodos, acceso guardado rechazado, otros pools conservados).
- **FR-013**: Mientras el retiro de un acceso no esté confirmado, MUST NOT entregarse ese acceso a otra persona.
- **FR-014**: Las terminales MUST cerrarse por inactividad tras un tiempo máximo configurable, avisando a la persona, y al desconectarse el navegador.
- **FR-015**: Cada persona MUST tener un límite configurable de terminales simultáneas; al superarlo se explica y se ofrece cerrar una.
- **FR-016**: Las terminales MUST cerrarse de inmediato, con aviso, al retirar el acceso, dar de baja o detener el servicio, o desactivar la cuenta.
- **FR-017**: Cada apertura y cierre MUST auditarse (quién, servicio, nodo, instante, duración, motivo de cierre) sin guardar nunca el contenido de la terminal, lo tecleado ni las contraseñas.
- **FR-018**: La habilitación de la terminal en una instalación MUST seguir exigiendo la evidencia real de revocación de la feature 020; sin ella la terminal permanece cerrada para toda persona, administración incluida.
- **FR-019**: Las personas con identidad creada a mano MUST poder pasar al modelo automático sin perder acceso y sin intervención de la persona.
- **FR-020**: Administración MUST poder ver el estado de la identidad de consola de cada persona (lista, en preparación, con error, retirada) sin ver credenciales, y reintentar un fallo.
- **FR-021**: La primera apertura de una terminal que falle por la intermitencia de la consola de la infraestructura MUST reintentarse una vez de forma transparente antes de avisar.
- **FR-022**: Debe existir un procedimiento reutilizable para la universidad (habilitación, prueba de revocación, operación y retiro) sin valores del laboratorio.
- **FR-023**: Las terminales MUST no degradar a otras personas ni al portal: el uso de recursos por sesión y en total está acotado.

### Key Entities

- **Identidad de consola**: cuenta individual de infraestructura de una persona; estado (en preparación, lista, con error, retirada); credencial guardada cifrada, no visible; alcance = cátedras a las que pertenece.
- **Sesión de terminal**: terminal abierta por una persona sobre un servicio; instante de apertura, última actividad, motivo de cierre; sin contenido.
- **Evento de auditoría de terminal**: apertura o cierre con persona, servicio, nodo, instante, duración y motivo; sin contenido.
- **Asignación persona–cátedra**: hecho que dispara el alta o el retiro de acceso de la identidad.
- **Evidencia de revocación**: prueba real, ya existente (feature 020), que habilita la terminal en la instalación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona conectada sólo al portal abre la terminal de su Linux y llega al prompt de inicio de sesión del contenedor en menos de 5 segundos, sin ver una sola pantalla de la infraestructura (0 pantallas de Proxmox en el recorrido).
- **SC-002**: La terminal abre con el mismo procedimiento y resultado para servicios alojados en cada nodo del clúster (verificado con al menos un servicio por nodo).
- **SC-003**: Tras asignar a una persona a una cátedra, puede abrir su primera terminal sin ninguna intervención manual de infraestructura, en el 100 % de los casos probados.
- **SC-004**: Al retirar el acceso, el 100 % de las terminales abiertas de esa persona sobre lo retirado se cortan en menos de 5 segundos y el 100 % de los intentos de reabrir son rechazados; los accesos que conserva en otras cátedras siguen funcionando.
- **SC-005**: El 100 % de los intentos de abrir la terminal de un servicio ajeno, de uno detenido o sin vigencia, o sin identidad lista se rechazan con un mensaje comprensible (al menos 3 casos por categoría).
- **SC-006**: Una terminal inactiva se cierra dentro del tiempo máximo configurado, y el intento de superar el límite de sesiones simultáneas es rechazado el 100 % de las veces.
- **SC-007**: Una búsqueda en registros, errores y auditoría de sesiones, incluidas las que fallaron a propósito, no encuentra ninguna contraseña ni texto escrito o mostrado en la terminal.
- **SC-008**: Una persona de infraestructura que no participó completa el procedimiento en un clúster de prueba y obtiene la terminal habilitada sin consultar a quien lo escribió.
- **SC-009**: Una persona que antes usaba la identidad manual abre su terminal tras el pase a automático sin intervenir, y la identidad manual anterior deja de existir.

## Assumptions

### Impacto en la constitución (decisión pendiente del equipo)

La constitución (Principio I) admite como **única excepción** derivar la persona a la consola de Proxmox, justificada porque un proxy propio con tokens de API no llegaba a transmitir. Esta feature demuestra otra vía: el portal usa un **ticket de sesión de una identidad individual**, que sí funciona. Hay dos escenarios y la feature se entrega igual en ambos:

- **Si el equipo retira la excepción**: la enmienda sería **MAJOR** (se redefine el Principio I) y pasa a «Proxmox nunca es la interfaz, sin excepciones». Cambia: el texto de la excepción y su motivación, la cláusula «Identidad en Proxmox para la consola», `GET /servicios/{id}/consola` (que devolvía un destino de Proxmox) y el botón «Abrir consola de esta instancia», y las specs 003/009/020 que describen la derivación. Se conserva: la identidad individual por persona, el pool por cátedra como frontera (Principio IV), la prueba real de revocación y la compuerta de instalación de la 020, y el aislamiento por cátedra verificado en el portal.
- **Si el equipo no la retira**: la derivación a la consola de Proxmox queda disponible como **respaldo** (por ejemplo, si el portal no puede abrir la terminal) pero deja de ser el camino normal; no hay cambios de texto en la constitución y esta feature se limita a agregar la terminal del portal como ruta principal. Se conserva todo lo anterior, incluida la excepción.

En ambos casos el Plan evalúa la «Constitution Check» contra el escenario vigente al momento de planificar y registra la decisión tomada.

### Otros supuestos

- La persona ya inicia sesión en el portal; la terminal no agrega una autenticación nueva y reutiliza esa sesión.
- La persona sigue escribiendo `nap` y la contraseña revelada dentro de la terminal; iniciar sesión automáticamente por ella queda fuera de alcance.
- La compuerta de instalación y la prueba real de revocación de la feature 020 siguen siendo condición de habilitación; esta feature no las relaja.
- Las identidades de consola viven en el dominio de autenticación propio de la instalación (en el laboratorio, `pve`), que es de todo el clúster: crear una identidad en un nodo la deja disponible en todos.
- Los valores por omisión (inactividad 15 minutos, 3 terminales simultáneas por persona) son configurables por instalación; se confirman en el plan.
- El portal escala a decenas de terminales simultáneas en el laboratorio y a cientos en una instalación universitaria; el plan debe acotar el consumo por sesión.
- Sólo servicios Linux IaaS (contenedores); Docker/OCI queda fuera.
- Fuera de alcance: transferencia de archivos, grabación o reproducción de sesiones, compartir una terminal entre personas, otros usuarios del contenedor, SSH desde el navegador, rotación periódica de contraseñas.
