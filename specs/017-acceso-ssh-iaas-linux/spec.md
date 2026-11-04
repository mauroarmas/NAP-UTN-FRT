# Feature Specification: Acceso SSH a servicios IaaS Linux

**Feature Branch**: `017-acceso-ssh-iaas-linux`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Acceso SSH a servicios IaaS Linux (Ubuntu) con la clave pública de la persona usuaria. Hoy el único método de acceso de un Ubuntu desplegado es la consola web del portal, que está bloqueada porque exige acreditar aislamiento, identidad nativa de Proxmox y revocación de consola; sin esa evidencia nadie puede usar el servicio sin ayuda de quien tenga acceso de administración al nodo. Se quiere que al pedir el servicio la persona aporte su clave pública SSH, que el motor la instale en el contenedor con el servicio de acceso remoto activo, y que el portal muestre cómo conectarse desde una máquina permitida, igual que ya ocurre con MariaDB. No depende de las identidades ni ACL de consola de Proxmox. Fuera de alcance: terminal web dentro del portal, habilitar la consola Proxmox, cambios a servicios Docker/OCI."

<!-- Principio VII: recorrido más corto útil. La persona sólo aporta un dato nuevo (su clave pública);
     el resto es automático. Principio I: este acceso no deriva a Proxmox ni usa sus permisos, por lo que
     no abre una excepción nueva ni exige enmienda; la excepción de la consola interactiva queda como está. -->

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entrar a mi Ubuntu desde mi computadora (Priority: P1)

Una persona de una cátedra pide un servicio Ubuntu. En el pedido pega su clave pública. Cuando el servicio está listo, el portal le muestra exactamente qué escribir (`ssh usuario@dirección`) y desde qué máquinas funciona. Abre una terminal en su computadora, pega el comando y entra, sin pedir ayuda a quien administra el nodo y sin usar la consola web.

**Why this priority**: Hoy un Ubuntu desplegado no se puede usar: el único método de acceso es la consola web y está bloqueada. Sin esto el servicio no cumple su razón de existir. Es el recorrido completo mínimo.

**Independent Test**: Pedir un Ubuntu con una clave pública, aprobarlo, esperar a que quede disponible y conectarse con la clave privada correspondiente desde una máquina permitida. Se puede demostrar solo, sin ninguna otra historia.

**Acceptance Scenarios**:

1. **Given** una persona con rol cátedra que pide un servicio Linux, **When** completa el pedido, **Then** el formulario pide una clave pública además de lo que ya pedía, rechaza con un mensaje comprensible una clave inválida o ilegible, y no exige ningún otro dato nuevo.
2. **Given** un servicio Linux disponible creado con una clave pública, **When** la persona abre su detalle, **Then** ve la dirección, el usuario y el comando de conexión listo para copiar, indicación de que se entra con la clave y no con contraseña, y desde qué máquinas está permitido.
3. **Given** una máquina permitida y la clave privada de la persona, **When** ejecuta el comando mostrado, **Then** entra al servicio con una sesión de terminal.
4. **Given** una conexión por contraseña, o con una clave distinta de la registrada, **When** intenta entrar, **Then** el servicio la rechaza.
5. **Given** una persona con una clave distinta de la registrada, **When** intenta conectarse, **Then** el acceso es rechazado.

---

### User Story 2 - El acceso sigue la vida del servicio (Priority: P2)

Mientras el servicio existe, la persona lo usa con su clave. Si lo detiene y lo vuelve a iniciar, o si el nodo se reinicia y lo inicia de nuevo, el acceso por clave sigue funcionando sin pasos manuales. Si el servicio se da de baja, el acceso deja de existir y no queda nada reutilizable.

**Why this priority**: Un acceso que se pierde al reiniciar obliga a pedir ayuda otra vez y vuelve al problema original. Depende de la historia 1.

**Independent Test**: Con un servicio de la historia 1, detenerlo e iniciarlo desde el portal, comprobar que se vuelve a entrar con la misma clave; luego darlo de baja y comprobar que ya no responde y que su clave no queda asociada a otro servicio.

**Acceptance Scenarios**:

1. **Given** un servicio con acceso por clave, **When** se detiene y se inicia desde el portal, **Then** la misma clave sigue permitiendo entrar.
2. **Given** un servicio dado de baja, **When** se pide un servicio nuevo que reutiliza el mismo identificador interno o la misma dirección, **Then** la clave del anterior no da acceso al nuevo.
3. **Given** un servicio detenido, **When** el portal muestra su detalle, **Then** no presenta el comando de conexión como utilizable ni afirma que se puede entrar.

---

### User Story 3 - Cambiar de computadora o de clave (Priority: P3)

La persona cambió de computadora o perdió su clave privada. Reemplaza la clave pública de un servicio ya entregado, sin tener que darlo de baja y pedirlo de nuevo, y la clave anterior deja de servir.

**Why this priority**: Sin esto, un cambio de computadora obliga a perder el trabajo. Es importante, pero el servicio ya es útil sin él.

**Independent Test**: Con un servicio entregado, reemplazar la clave pública desde el portal y comprobar que la clave nueva entra y la anterior es rechazada.

**Acceptance Scenarios**:

1. **Given** un servicio Linux entregado, **When** su titular reemplaza la clave pública, **Then** la clave nueva permite entrar y la anterior deja de hacerlo.
2. **Given** una persona que no es titular ni administra ese servicio, **When** intenta reemplazar su clave, **Then** el portal lo rechaza.
3. **Given** un servicio Linux creado antes de esta función y sin clave registrada, **When** su titular registra una clave, **Then** obtiene acceso por SSH con el mismo flujo de la historia 1.

---

### Edge Cases

- Clave pública mal formada, truncada, con varias líneas o de un tipo de clave que la institución no acepta: el pedido no avanza y se explica qué corregir; nunca se instala algo parcial.
- Se pega por error una clave **privada**: se rechaza y se avisa que sólo debe pegarse la pública; la clave privada nunca se guarda ni se registra.
- El servicio queda listo pero el acceso remoto dentro del contenedor no responde: el portal no declara el servicio como utilizable ni muestra el comando de conexión; informa que el acceso aún no está verificado.
- El pedido se aprueba y falla antes de instalar la clave: el servicio no se entrega con acceso a medias; se recupera con el mecanismo existente de reparación, sin duplicar recursos.
- La misma clave pública se usa en varios servicios de la misma persona: es válido y cada servicio la trata de forma independiente.
- Dos cátedras distintas usan la misma clave pública: ninguna obtiene acceso al servicio de la otra por ello.
- La persona se conecta desde una red sin ruta hacia el servicio: el portal informa la dirección y el hecho de que debe estar en la red institucional del laboratorio; el fallo de red no se presenta como un error del servicio.
- El nodo se reinicia: el servicio no arranca solo (decisión vigente); al iniciarlo desde el portal, el acceso por clave sigue vigente y el servicio no se declara utilizable hasta comprobar que el acceso remoto responde.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El pedido de un servicio Linux IaaS MUST solicitar una clave pública SSH de la persona solicitante y MUST NOT exigir otros datos nuevos.
- **FR-002**: El sistema MUST validar la clave antes de aceptar el pedido: formato legible, una sola clave, tipo admitido por la institución. Una clave inválida o una clave privada MUST rechazarse con un mensaje que indique cómo corregirla.
- **FR-003**: El sistema MUST NOT almacenar, mostrar ni registrar claves privadas, ni contraseñas de acceso remoto. Del acceso por clave sólo se conserva la clave pública y una huella para identificarla.
- **FR-004**: Al desplegar el servicio, el sistema MUST dejar dentro del contenedor el acceso remoto activo, un usuario sin privilegios con permiso de elevación y autorizada únicamente la clave aportada para ese usuario, sin intervención manual de quien administra el nodo. MUST NOT habilitar el ingreso remoto directo como administrador del contenedor.
- **FR-005**: El acceso remoto MUST permitir sólo autenticación por clave; MUST NOT admitir ingreso por contraseña.
- **FR-006**: El servicio MUST NOT declararse utilizable ni entregarse hasta comprobar que el acceso remoto responde con la clave registrada; si la comprobación falla, el estado informado es el de fallo con motivo, no «utilizable».
- **FR-007**: El detalle del servicio MUST mostrar dirección, usuario, comando de conexión copiable, el hecho de que se entra con clave, y la indicación de que debe conectarse desde la red institucional. MUST mostrarlo sólo cuando el servicio está en marcha y verificado.
- **FR-008**: Esta función MUST NOT abrir, cerrar ni modificar reglas de red. Los servicios Linux IaaS no tienen hoy restricción de red por instancia: el único control de ingreso es la clave. La spec lo declara de forma explícita y no presenta el acceso como restringido por origen.
- **FR-009**: El acceso MUST NOT depender de las identidades, permisos ni evidencias de la consola de Proxmox, y MUST NOT derivar a la persona a ninguna pantalla de Proxmox.
- **FR-010**: La baja del servicio MUST eliminar el acceso con él, y la clave de un servicio dado de baja MUST NOT dar acceso a otro servicio posterior que reutilice su dirección o identificador interno.
- **FR-011**: Detener e iniciar el servicio desde el portal MUST conservar el acceso por clave sin reenviar la configuración; el detalle MUST ofrecer el comando de conexión solo con el servicio en marcha y el acceso aplicado, y MUST dejar de ofrecerlo mientras esté detenido. Tras el reinicio de un nodo, la clave y la configuración de acceso persisten en el contenedor; el ensayo real debe comprobar que el acceso responde al volver a iniciar el servicio.
- **FR-012**: El titular del servicio y la administración MUST poder registrar o reemplazar la clave pública de un servicio entregado, incluidos los creados antes de esta función; al reemplazarla, la anterior MUST dejar de funcionar. Cualquier otra persona MUST ser rechazada.
- **FR-013**: Registrar, validar y reemplazar una clave, y los intentos rechazados por falta de permiso, MUST quedar en el historial del servicio con autor y momento, sin incluir la clave completa en mensajes de error ni registros operativos.
- **FR-014**: Los servicios Docker/OCI, las bases de datos y las aplicaciones web MUST NOT cambiar de comportamiento ni mostrar este acceso.
- **FR-015**: La consola web existente de los servicios IaaS MUST conservar su comportamiento y su compuerta actuales; esta función no la habilita, la sustituye ni la modifica.

### Key Entities

- **Clave de acceso remoto del servicio**: clave pública aportada por la persona titular para un servicio Linux concreto; tiene huella identificatoria, fecha de registro y de último reemplazo, y pertenece a un único servicio. Nunca incluye la parte privada.
- **Servicio Linux IaaS**: instancia entregada a una cátedra que, además de lo que ya tiene, pasa a tener un método de acceso remoto verificable y los datos de conexión que el portal muestra.
- **Datos de conexión**: dirección, usuario, comando, y redes permitidas, derivados del servicio y de la configuración de red institucional; se presentan sólo cuando el servicio está en marcha y verificado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona sin conocimientos de administración de Proxmox puede pasar de «servicio Ubuntu disponible» a una terminal abierta en él en menos de 2 minutos, usando sólo lo que muestra el portal.
- **SC-002**: Tras aprobar un pedido, en el 100 % de los despliegues exitosos se puede entrar con la clave aportada sin ninguna acción manual sobre el nodo, en un ensayo con al menos 3 servicios en 2 nodos.
- **SC-003**: En todos los intentos de ensayo con una clave distinta de la registrada, con contraseña, o como administrador del contenedor, el acceso es rechazado (0 ingresos indebidos).
- **SC-004**: Tras detener e iniciar un servicio, y tras reiniciar un nodo e iniciar el servicio, la misma clave sigue entrando en el 100 % de los ensayos reales, y el comando de conexión no se ofrece mientras el servicio está detenido.
- **SC-005**: Tras reemplazar la clave, la anterior es rechazada y la nueva admitida en el 100 % de los ensayos.
- **SC-006**: Ninguna clave privada ni contraseña de acceso aparece en pantalla, historial, mensajes de error ni registros operativos en las comprobaciones de seguridad.
- **SC-007**: Las pruebas de regresión existentes de servicios Docker/OCI, bases de datos y consola IaaS pasan sin cambios de comportamiento.

## Assumptions

- La plantilla Linux oficial ya incluye, o el motor puede dejarle activo, el servicio de acceso remoto sin descargar software externo no controlado; si hiciera falta incluirlo, es parte de esta función.
- El usuario de conexión es un usuario sin privilegios con permiso de elevación dentro de su propio contenedor (decisión de aclaración); el ingreso directo como administrador del contenedor no se ofrece. Sólo se admite autenticación por clave. El portal informa ese usuario en lugar del `root` que hoy muestra.
- Los servicios Linux ya entregados antes de esta función pueden incorporar una clave por el mismo camino de reemplazo (decisión de aclaración); el motor les deja el acceso listo sin tener que darlos de baja.
- La máquina de la persona tiene ruta de red hasta el servicio (la red institucional del laboratorio). Los servicios Linux IaaS no tienen hoy aislamiento de red por instancia ni lista de clientes permitidos —eso existe sólo en el motor de aplicaciones Docker/OCI—; agregarlos es una decisión institucional aparte, fuera de esta función. Mientras tanto la clave es el único control de ingreso.
- Una persona aporta una clave por servicio; varias claves por servicio o por cátedra quedan fuera de alcance.
- Los tipos de clave admitidos se fijan por una política institucional simple y revisable, con los tipos modernos habituales; no se pide a la persona que elija un algoritmo.
- El reinicio de un nodo sigue sin arrancar los servicios solos; el inicio desde el portal es el camino, como ya está decidido.
- Esta función necesita ejecutar acciones dentro del contenedor desde el nodo, por lo que requiere reinstalar el paquete de nodo y validarse con un ensayo real en cada nodo antes de habilitarse. No debe alterar el motor Docker/OCI ni sus perfiles ya validados.
- Fuera de alcance: terminal web en el portal, habilitar o modificar la consola interactiva de Proxmox, cambios a servicios Docker/OCI, bases de datos y aplicaciones web, gestión de claves de varias personas por servicio, y cualquier restricción de red por instancia para servicios Linux.
