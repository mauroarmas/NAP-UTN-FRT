# Feature Specification: Biblioteca de aplicaciones reutilizables

**Feature Branch**: `010-integrar-biblioteca-aplicaciones`

**Feature Directory**: `specs/010-integrar-biblioteca-aplicaciones`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Facilitar la búsqueda e incorporación de aplicaciones de Community Scripts, con Draw.io como piloto. Preparar cada aplicación una vez, publicarla en NAP y permitir que las cátedras la seleccionen al crear sus pedidos. Dejar una especificación pequeña para desarrollarla en otro chat."

## Clarifications

### Session 2026-10-25
- Q: ¿Qué debe poder hacer administración desde NAP para preparar Draw.io? → A: NAP ejecuta la preparación en un entorno de ensayo y muestra su estado y resultado; administración comprueba el funcionamiento y publica.
- Q: Si se publica una nueva versión de Draw.io mientras un pedido espera aprobación, ¿qué versión debe recibir ese pedido? → A: Usar la versión publicada vigente al aprobar, informando el cambio y sin pedir confirmación a la cátedra.
- Q: ¿Cuándo debe NAP liberar los recursos del entorno de ensayo usados para preparar y comprobar Draw.io? → A: Automáticamente al publicar, descartar la preparación o vencer un plazo configurable informado al iniciar el ensayo; conservar la definición reutilizable y los resultados registrados.
- Q: Si Community Scripts deja de estar disponible después de publicar Draw.io, ¿debe NAP poder desplegar nuevas instancias de esa versión? → A: Sí. Community Scripts sólo proporciona el comando de instalación ante una búsqueda; NAP conserva lo necesario para desplegar la versión preparada sin consultar ni descargar desde Community Scripts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Buscar e incorporar una aplicación (Priority: P1)

Como administrador quiero buscar aplicaciones desde Definiciones e incorporar sus datos disponibles, para evaluar una oferta nueva sin transcribir todo su contenido.

**Why this priority**: Reduce el trabajo de descubrimiento y alta manteniendo la decisión de publicación en administración.

**Independent Test**: Encontrar Draw.io e importar su borrador, comprobando que no se publicó ni se creó una instalación.

**Acceptance Scenarios**:

1. **Given** administración en Definiciones, **When** busca por nombre o categoría, **Then** ve fichas con el comando de instalación y su origen, los datos disponibles de descripción y compatibilidad y los faltantes señalados; Draw.io se encuentra con «drawio», «draw.io» y «diagramas».
2. **Given** una ficha, **When** se agrega a NAP, **Then** se genera un borrador editable con los datos disponibles y los faltantes señalados. Repetir la misma incorporación identifica el borrador existente sin duplicarlo ni sobrescribir cambios administrativos.
3. **Given** una búsqueda sin coincidencias o un proveedor que no responde, **When** se consulta, **Then** se distinguen ambas situaciones y se permite reintentar; el catálogo interno sigue disponible.
4. **Given** administración operando con teclado, **When** recorre búsqueda, ficha e incorporación y encuentra un error, **Then** puede identificar los controles, completar el recorrido y corregirlo sin perder los datos válidos.

---

### User Story 2 - Preparar y publicar Draw.io (Priority: P1)

Como administrador quiero comprobar y publicar una versión reutilizable de Draw.io para resolver futuras solicitudes mediante una oferta ya preparada.

**Why this priority**: Demuestra el circuito completo con una aplicación concreta y utilizable.

**Independent Test**: Partir de un borrador de Draw.io, completar su preparación y comprobaciones y publicar su oferta de Software.

**Acceptance Scenarios**:

1. **Given** un borrador incompleto o una comprobación fallida, **When** se intenta publicar, **Then** se indican los motivos y la oferta permanece fuera de la selección docente.
2. **Given** Draw.io preparado, **When** se comprueba desde la red prevista que permite crear, editar, exportar y volver a abrir un diagrama editable conservando su contenido, **Then** se registran los resultados y administración puede publicar esa versión y su perfil ofrecido.
3. **Given** una oferta publicada, **When** cambia la versión externa, **Then** se conserva la versión aprobada; adoptar la actualización exige otra decisión y comprobación.
4. **Given** una preparación o despliegue con resultado incierto, **When** se reintenta, **Then** se comprueba lo que ya existe y se continúa sin duplicar recursos ni perder su historia.
5. **Given** un borrador de Draw.io con los datos necesarios y un entorno de ensayo disponible, **When** administración inicia su preparación desde NAP, **Then** NAP la ejecuta en ese entorno y muestra su estado y resultado; la comprobación funcional y la publicación requieren la intervención posterior de administración.
6. **Given** un ensayo con plazo y vencimiento informados al iniciar y aviso previo al vencimiento, **When** se publica, se descarta la preparación o vence el plazo, **Then** NAP libera sus recursos y conserva la definición reutilizable y los resultados registrados.
7. **Given** una liberación de recursos de ensayo fallida, **When** administración consulta su estado y reintenta, **Then** ve el motivo y la limpieza pendiente, los recursos continúan contabilizados hasta liberarse y el reintento no duplica recursos ni elimina resultados.

---

### User Story 3 - Seleccionar y reutilizar una oferta publicada (Priority: P1)

Como responsable de cátedra quiero seleccionar una aplicación ya publicada al crear un pedido, sin volver a describirla como «Otro» ni conocer hardware o instalación.

**Why this priority**: Hace efectiva la reutilización para todas las cátedras dentro del recorrido de pedidos existente.

**Independent Test**: Con Draw.io publicado, dos cátedras crean pedidos independientes desde Catálogo y Nuevo pedido y reciben sus instancias propias tras aprobar y desplegar.

**Acceptance Scenarios**:

1. **Given** Draw.io publicado como Software, **When** una cátedra crea un pedido, **Then** puede seleccionarlo, completar nombre, justificación pedagógica y fechas válidas desde 2026, sin especificar hardware. Solicitar desde Catálogo conserva la oferta elegida.
2. **Given** dos pedidos de distintas cátedras para esa oferta, **When** administración aprueba y despliega, **Then** se reutiliza la definición preparada y se mantienen reservas, instancias, accesos e historial independientes; ninguna cátedra accede a la instancia de la otra.
3. **Given** una aplicación todavía no publicada o retirada, **When** se crea un pedido, **Then** no puede seleccionarse como oferta disponible. «Otro» continúa permitiendo describir una necesidad nueva; los pedidos aprobados conservan sus referencias históricas.
4. **Given** un pedido pendiente cuya oferta tiene una nueva versión publicada, **When** administración lo aprueba, **Then** se asigna la versión publicada vigente, se evalúa y reserva capacidad para ella y se informa el cambio a la cátedra sin exigir su confirmación; una publicación posterior no modifica la versión ya aprobada.

### Edge Cases

- Resultado correspondiente a una máquina virtual, una herramienta del nodo o una aplicación incompatible: informar la limitación sin anunciar instalación disponible.
- Requisitos, versión o acceso desconocidos: señalar lo que falta, sin inventar valores ni comprobaciones.
- Oferta retirada mientras se completa un pedido: conservar lo escrito y pedir revisar la selección antes de enviarlo. Si un pedido ya enviado sigue pendiente y no existe una versión publicada vigente de su oferta, impedir su aprobación hasta revisar la selección.
- Datos o credenciales de ensayos en una preparación: impedir que pasen a una oferta reutilizable.
- Fallo al liberar los recursos de ensayo: conservar el estado de limpieza pendiente y su motivo, permitir reintentar sin duplicar recursos ni borrar resultados. El vencimiento del ensayo debe avisarse con antelación para permitir completar las comprobaciones.
- Community Scripts inaccesible después de publicar: conservar las ofertas internas y los servicios existentes y permitir nuevos despliegues de las versiones preparadas sin consultar ni descargar desde Community Scripts.
- Falta de capacidad o fecha inicial futura: conservar la evaluación de capacidad y la espera vigentes, sin crear anticipadamente recursos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Sólo administración DEBE buscar en la biblioteca externa desde Definiciones, revisar fichas e incorporar borradores. La cátedra utiliza el catálogo publicado y sus pedidos propios.
- **FR-002**: La búsqueda DEBE admitir nombre y categorías disponibles, localizar Draw.io con los términos de US1.1 y distinguir ausencia de coincidencias de falta de conexión.
- **FR-003**: La ficha DEBE mostrar el comando de instalación proporcionado por Community Scripts y su procedencia, además de descripción, versión y requisitos cuando estén disponibles. DEBE distinguir información externa de preparación comprobada por NAP y señalar los datos desconocidos para completarlos administrativamente. La búsqueda NO DEBE ejecutar el comando.
- **FR-004**: Incorporar una aplicación DEBE crear un borrador editable y conservar su origen. Repetir la incorporación de la misma aplicación y versión NO DEBE duplicarla ni sobrescribir decisiones previas.
- **FR-005**: Buscar o importar información NO DEBE ejecutar instalaciones, crear contenedores, reservar capacidad ni publicar ofertas. La preparación y la publicación requieren acciones administrativas explícitas.
- **FR-006**: El piloto DEBE incorporar Draw.io como una oferta de Software utilizable. Encontrar otras aplicaciones NO DEBE anunciar su compatibilidad sin preparación y comprobaciones propias.
- **FR-007**: Publicar DEBE exigir una versión preparada, requisitos, acceso previsto y resultados registrados de comprobación funcional y acceso desde la red prevista. Una preparación incompleta o fallida NO DEBE quedar seleccionable.
- **FR-008**: La preparación reutilizable NO DEBE incluir datos de cátedras, credenciales de ensayo ni accesos compartidos. Cada entrega DEBE conservar las garantías vigentes de aislamiento y verificación de acceso.
- **FR-009**: Publicar una definición y su perfil ofrecido DEBE hacerla seleccionable tanto en Catálogo como en Nuevo pedido para cualquier responsable con acceso operativo, dentro de su tipo de servicio.
- **FR-010**: Solicitar desde Catálogo DEBE conservar la oferta elegida. La cátedra completa cátedra, nombre, justificación pedagógica y vigencia; NO DEBE indicar hardware ni parámetros de instalación.
- **FR-011**: Cada pedido DEBE conservar revisión administrativa, aclaración o rechazo, reserva al aprobar, preparación del pool de cátedra y despliegue desde la fecha inicial. Al aprobar se DEBE asignar la versión publicada vigente de la oferta y evaluar y reservar capacidad con sus requisitos. Si difiere de la seleccionada al enviar el pedido, se DEBE registrar el cambio en el historial e informarlo a la cátedra sin exigir su confirmación. La versión aprobada DEBE conservarse ante publicaciones posteriores. Incorporar una oferta no aprueba pedidos automáticamente.
- **FR-012**: Una publicación DEBE reutilizarse en pedidos de distintas cátedras sin repetir su alta. Cada pedido aprobado y desplegado DEBE producir una instancia propia, con recursos, acceso, datos e historia independientes.
- **FR-013**: Los reintentos por doble envío o pérdida de confirmación NO DEBEN duplicar ofertas o recursos. Los fallos DEBEN conservar datos válidos y un estado consultable con vía de recuperación.
- **FR-014**: Cambios o indisponibilidad de Community Scripts NO DEBEN reemplazar versiones aprobadas ni interrumpir ofertas internas, servicios existentes o nuevos despliegues de versiones preparadas. NAP DEBE conservar lo necesario para esos despliegues sin consultar ni descargar desde Community Scripts. Retirar una publicación impide pedidos nuevos sobre ella y conserva las referencias históricas.
- **FR-015**: «Otro» DEBE mantenerse en Plataforma y Software para necesidades no publicadas; su resolución puede vincular una oferta de esta biblioteca al pedido original.
- **FR-016**: El asistente DEBE usar lenguaje comprensible, señalar campos obligatorios, permitir operación por teclado y conservar lo completado ante errores.
- **FR-017**: NAP DEBE permitir a administración iniciar la preparación de Draw.io en un entorno de ensayo separado de las instancias de cátedras, ejecutar esa preparación y consultar su estado y resultado, incluidos fallos y recuperación. Completar la preparación NO DEBE publicar automáticamente: administración DEBE comprobar el funcionamiento antes de publicar.
- **FR-018**: Cada ensayo DEBE tener un plazo configurable y un vencimiento informado al iniciarlo, con aviso previo a administración. NAP DEBE liberar automáticamente sus recursos al publicar, descartar la preparación o vencer el ensayo, conservando la definición reutilizable y los resultados registrados. La limpieza fallida DEBE quedar visible y permitir reintento; los recursos pendientes de liberar DEBEN seguir contabilizados como ocupados.

### Key Entities *(include if feature involves data)*

- **Aplicación externa**: identidad en la fuente, nombre, comando de instalación y procedencia; descripción, categorías, versión y requisitos cuando estén disponibles. Es una candidata, no una oferta autorizada.
- **Definición preparada**: versión revisada por administración, información de preparación, estado y vencimiento del ensayo, estado de liberación de sus recursos y resultados de comprobación. Se reutiliza conservando su origen.
- **Oferta publicada**: perfil seleccionable de una definición, con tipo de servicio y requisitos utilizados al evaluar pedidos; puede retirarse sin borrar historia.
- **Pedido e instancia de cátedra**: solicitud de una oferta y servicio individual resultante, con cátedra, versión seleccionada al enviar, versión autorizada al aprobar, fechas y acceso propios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con el proveedor disponible, administración encuentra Draw.io con cada uno de los tres términos e incorpora su borrador en menos de 2 minutos, sin transcribir nombre, descripción o procedencia cuando estén disponibles.
- **SC-002**: El 100 % de los intentos de publicar borradores incompletos, incompatibles o con comprobaciones fallidas queda fuera del catálogo docente e informa el motivo.
- **SC-003**: Una publicación de Draw.io permite a dos cátedras crear pedidos y recibir instancias independientes sin repetir el alta de la aplicación. Ambas pueden crear, editar, exportar y volver a abrir un diagrama editable conservando su contenido desde la red prevista; los intentos cruzados de consultar u operar la instancia ajena se deniegan.
- **SC-004**: El responsable completa un pedido de la oferta publicada en menos de 3 minutos desde Catálogo o Nuevo pedido, sin ayuda técnica ni campos de hardware o instalación.
- **SC-005**: Dos envíos repetidos de cada operación y al menos una pérdida simulada de confirmación no producen ofertas o instancias duplicadas y mantienen el resultado consultable.
- **SC-006**: Durante una interrupción simulada de Community Scripts, una oferta ya publicada sigue siendo seleccionable y permite enviar, aprobar y desplegar un pedido nuevo de la versión preparada sin consultas ni descargas desde Community Scripts; la instancia resultante supera las comprobaciones funcionales de SC-003.

## Assumptions

- Se conservan la autenticación, roles y recorrido de pedidos de NAP. No se agregan cuentas institucionales de alumnos para esta función.
- La fuente inicial es Community Scripts: su función se limita a proporcionar el comando de instalación ante una búsqueda. NAP gestiona la preparación, comprobación, publicación y reutilización; los datos que no aporte la búsqueda se completan administrativamente. El piloto es Draw.io en LXC. No se promete instalar automáticamente todo el catálogo externo.
- «Preparar una vez» reutiliza una definición comprobada; cada cátedra recibe su instancia independiente al aprobar y desplegar su pedido.
- Hoy los productos preparados son Linux, PostgreSQL y BookStack. Draw.io requiere ampliar esa compatibilidad: encontrar su ficha externa no acredita que ya pueda desplegarse.
- El acceso autorizado a la información vigente del proveedor y los datos disponibles se comprobarán durante la planificación. No se supone disponibilidad permanente ni se da por verificada una integración externa operativa.
- La preparación y aceptación necesitan un entorno de ensayo separado de las instancias de cátedras. Su ausencia no permite anunciar comprobaciones como realizadas.
- La función mínima de Draw.io es trabajar con diagramas y archivos exportados. Guardado centralizado, colaboración simultánea y gestión de cuentas de la aplicación quedan fuera del piloto.
- Quedan fuera la interpretación automática de lenguaje natural, nuevas máquinas virtuales, herramientas de administración del nodo, incorporación masiva, actualizaciones automáticas y ejecución libre de instrucciones pegadas por usuarios.
- NAP conserva el control de reservas, fechas, pools, accesos y recuperaciones; este recorrido no exige administrar recursos desde el panel de Proxmox.
- Planificación, tareas e implementación se continuarán en otro chat; esta entrega sólo deja la especificación y su contexto.
