# Feature Specification: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS

**Feature Branch**: `007-solicitud-aprovisionamiento-servicios`

**Created**: 2026-10-08

**Status**: Completed

**Input**: User description: "Solicitud y aprovisionamiento de recursos de infraestructura y servicios (IaaS, PaaS, SaaS) para cátedras con gestión de templates, evaluación administrativa, aprobación con opciones avanzadas, rechazo fundamentado, solicitud de ajustes y autogestión de servicios desplegados."

> **Convención de Nomenclatura de Estados:**  
> Para preservar la coherencia entre el diseño funcional y el modelo de datos/API canónico (Principio II de la Constitución), los estados formales del ciclo de vida son:  
> - `SOLICITADO` (presentado en la interfaz de usuario como *Pendiente*).  
> - `REQUIERE_AJUSTE` (presentado en la interfaz de usuario como *Requiere Ajuste*).  
> - `EN_DESPLIEGUE` (presentado en la interfaz de usuario como *En Despliegue*).  
> - `ACTIVO` (presentado en la interfaz de usuario como *Disponible / Activo*).  
> - `RECHAZADO` (presentado en la interfaz de usuario como *Rechazado*).  
> - `CANCELADO` (presentado en la interfaz de usuario como *Cancelado*).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Solicitud de Recursos y Servicios por la Cátedra (Priority: P1)

Como docente o responsable de cátedra, quiero solicitar recursos de cómputo indicando el tipo de servicio (IaaS, PaaS o SaaS), la descripción de mis necesidades y la vigencia temporal requerida (cuatrimestre, ciclo lectivo o rango de fechas), para contar con el entorno necesario para las actividades académicas.

**Why this priority**: Es la puerta de entrada indispensable del autoservicio. Sin la capacidad de registrar solicitudes estructuradas con vigencia y modelo de servicio, no existe flujo operativo posible.

**Independent Test**: Una cátedra puede completar y enviar un formulario de solicitud seleccionando el modelo (IaaS, PaaS o SaaS), ingresando la justificación pedagógica/técnica y la vigencia deseada. El sistema valida los datos y registra la solicitud en estado `SOLICITADO` (Pendiente), entregando un identificador de seguimiento verificable.

**Acceptance Scenarios**:

1. **Given** que una cátedra con sesión activa accede a la sección de nueva solicitud, **When** selecciona el modelo IaaS, elige un perfil de tamaño predefinido (*Small*, *Medium*, *Large*), especifica la vigencia temporal (ej: "1° Cuatrimestre") y confirma el envío, **Then** el sistema registra el pedido en estado `SOLICITADO` y muestra un mensaje de confirmación con el código de seguimiento.
2. **Given** que una cátedra requiere un software específico (SaaS) o una API especializada (PaaS), **When** completa la descripción con el software requerido (ej: libro virtual interactivo, Moodle o API de IA) y la vigencia estimada, **Then** el sistema almacena los requerimientos detallados y notifica que el pedido ha sido recibido para evaluación técnica en estado `SOLICITADO`.
3. **Given** un formulario de solicitud incompleto (falta descripción, tipo de servicio o vigencia), **When** la cátedra intenta enviar el pedido, **Then** el sistema bloquea el envío y destaca los campos requeridos sin perder la información previamente cargada.

---

### User Story 2 - Evaluación Administrativa y Aprobación con Despliegue Automático (Priority: P1)

Como administrador de infraestructura, quiero revisar los pedidos pendientes (`SOLICITADO`), seleccionar o afinar la plantilla de aprovisionamiento aplicable (pudiendo consultar o modificar parámetros en opciones avanzadas) y aprobar la solicitud, para que el sistema despliegue el recurso de forma automatizada en el clúster institucional y quede disponible (`ACTIVO`) para la cátedra.

**Why this priority**: Representa el núcleo del ciclo de aprovisionamiento (*happy path*). Garantiza la gobernanza técnica de los recursos institucionales y activa la instanciación real del entorno solicitado.

**Independent Test**: El administrador visualiza un pedido en estado `SOLICITADO`, selecciona una plantilla homologada, confirma la aprobación, y el sistema orquesta la creación del entorno virtual, pasando el pedido a `EN_DESPLIEGUE` y posteriormente a `ACTIVO` (Disponible), generando los datos de conexión correspondientes.

**Acceptance Scenarios**:

1. **Given** un pedido en estado `SOLICITADO`, **When** el administrador revisa los detalles, selecciona la plantilla homologada correspondiente y confirma la aprobación estándar, **Then** el sistema cambia el estado a `EN_DESPLIEGUE`, reserva la capacidad de cómputo, dispara el aprovisionamiento automatizado y, al finalizar con éxito, actualiza el estado a `ACTIVO` registrando la IP y datos de acceso.
2. **Given** un pedido con requerimientos específicos de red o almacenamiento, **When** el administrador despliega el panel de opciones avanzadas, ajusta parámetros específicos (nodo de despliegue o subred) y aprueba, **Then** el sistema ejecuta el despliegue respetando los parámetros avanzados configurados.
3. **Given** un pedido en proceso de aprobación, **When** el clúster experimenta una falla transitoria de aprovisionamiento, **Then** el sistema deja el pedido en un estado explícito de error de despliegue (`ERROR`) con el motivo registrado, liberando cualquier reserva inconclusa y permitiendo reintentar la acción.

---

### User Story 3 - Flujo de Rechazo y Negociación de Ajustes (Priority: P2)

Como administrador, quiero poder rechazar una solicitud inviable con un motivo escrito obligatorio, o devolverla a la cátedra con una propuesta de ajustes (por ejemplo, reducción de recursos o cambio de fechas), para que la cátedra pueda aceptar las modificaciones o desistir sin fricción.

**Why this priority**: En un entorno con recursos finitos, no todas las solicitudes pueden aprobarse de inmediato. Permitir ajustes colaborativos evita rechazos frustrantes y optimiza la capacidad disponible.

**Independent Test**: El administrador puede devolver un pedido con observaciones de ajuste; la cátedra visualiza el pedido en estado `REQUIERE_AJUSTE`, revisa las notas del administrador, ajusta los valores y lo reenvía a revisión, pasando nuevamente a `SOLICITADO`. Asimismo, el administrador puede rechazar un pedido ingresando un motivo obligatorio, dejando el pedido en estado final `RECHAZADO`.

**Acceptance Scenarios**:

1. **Given** un pedido en estado `SOLICITADO` que excede la capacidad disponible o no cuenta con justificación válida, **When** el administrador selecciona "Rechazar" e ingresa el motivo fundado, **Then** el sistema cambia el estado a `RECHAZADO`, registra el motivo y lo pone a disposición de la cátedra para su consulta.
2. **Given** un pedido que requiere cambios menores (ej: reducir RAM sugerida o ajustar fechas), **When** el administrador solicita modificaciones indicando las observaciones, **Then** el sistema cambia el estado a `REQUIERE_AJUSTE` y notifica a la cátedra.
3. **Given** un pedido en estado `REQUIERE_AJUSTE`, **When** la cátedra revisa las observaciones del administrador, actualiza los campos solicitados y confirma el reenvío, **Then** el pedido pasa nuevamente a estado `SOLICITADO` conservando la trazabilidad de la negociación.
4. **Given** un pedido en estado `REQUIERE_AJUSTE`, **When** la cátedra decide no continuar con la solicitud y presiona "Cancelar", **Then** el sistema cancela definitivamente el pedido (`CANCELADO`) sin comprometer recursos.

---

### User Story 4 - Visualización, Consumo y Autogestión de Servicios por la Cátedra (Priority: P2)

Como docente de cátedra, quiero ver en mi panel el listado de mis servicios en estado activo/disponible (`ACTIVO`) con su fecha de vigencia y datos de conexión, y disponer de controles de operación (Iniciar, Detener, Reiniciar y métricas de uso), para gestionar el ciclo lectivo de manera autónoma sin requerir soporte administrativo para tareas operativas rutinarias.

**Why this priority**: Cierra el valor para el usuario docente, otorgándole control sobre su entorno y garantizando que los alumnos puedan acceder al servicio desplegado a través de los datos provistos por la cátedra.

**Independent Test**: Una cátedra con un servicio en estado `ACTIVO` puede consultar los endpoints de acceso, enviar comandos de reinicio o detención sobre su servicio y visualizar el estado actualizado en pantalla.

**Acceptance Scenarios**:

1. **Given** un servicio desplegado con éxito en estado `ACTIVO`, **When** la cátedra accede al detalle del servicio, **Then** visualiza la dirección IP/URL de conexión, las credenciales generadas, la fecha de vigencia programada y los indicadores de consumo (CPU, memoria, disco).
2. **Given** un servicio en ejecución (`running`), **When** el docente presiona "Reiniciar", **Then** el sistema envía la instrucción operativa al entorno, actualiza transitoriamente el estado y confirma la finalización del reinicio manteniendo intactas las configuraciones.
3. **Given** un servicio que la cátedra no utilizará temporalmente durante un receso, **When** el docente presiona "Detener", **Then** el entorno pasa a estado detenido (`stopped`), reduciendo el consumo activo del clúster hasta que vuelva a ser iniciado.

---

### User Story 5 - Administración y Catálogo de Plantillas de Recursos (Priority: P3)

Como administrador, quiero gestionar un catálogo de plantillas (templates) predefinidas para IaaS (*Small*, *Medium*, *Large*), PaaS y SaaS (crear, editar, activar/desactivar), para mantener actualizados los perfiles estándar que las cátedras pueden seleccionar y que el sistema utiliza para aprovisionar.

**Why this priority**: Facilita la gobernanza técnica a largo plazo y desacopla la definición de tamaños de hardware del código de la aplicación.

**Independent Test**: El administrador puede acceder al módulo de plantillas, crear un nuevo tamaño de plantilla (ej: *GPU-Lab* o *Micro*), definir sus cuotas de CPU, RAM y disco, y verificar que dicho perfil quede disponible para nuevas solicitudes.

**Acceptance Scenarios**:

1. **Given** el módulo de gestión de plantillas, **When** el administrador crea una nueva plantilla indicando nombre, tipo de servicio, vCPU, memoria RAM y almacenamiento base, **Then** la plantilla se registra activa en el catálogo institucional.
2. **Given** una plantilla existente en el catálogo, **When** el administrador modifica sus valores predeterminados o la desactiva, **Then** los pedidos futuros reflejan el cambio sin alterar los servicios ya desplegados bajo versiones previas.

---

### Edge Cases

- **Solicitud de recursos durante saturación de capacidad:** Si el clúster alcanza el límite de cómputo durante la evaluación de un pedido, el sistema advierte al administrador antes de confirmar la aprobación, impidiendo sobrecompromisos accidentales salvo autorización explícita con justificación registrada.
- **Vencimiento de la vigencia del servicio:** Al alcanzarse la fecha de fin de vigencia pactada en la solicitud, el servicio no se elimina de inmediato de forma destructiva; el sistema notifica a la cátedra y marca el servicio como vencido (`VENCIDO`), permitiendo solicitar una prórroga o proceder a la baja controlada.
- **Acceso concurrente de alumnos:** Los estudiantes acceden directamente a las aplicaciones o servicios desplegados mediante la red universitaria; fallas de autenticación o uso del servicio final no interfieren con la estabilidad del portal de gestión de NAP.
- **Rechazo sin justificación:** Si el administrador intenta rechazar un pedido sin proporcionar un texto explicativo, el sistema bloquea la acción exigiendo el ingreso obligatorio del motivo.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE permitir a los usuarios con rol de Cátedra crear solicitudes de recursos especificando el modelo de servicio (**IaaS**, **PaaS** o **SaaS**).
- **FR-002**: Para solicitudes IaaS, el sistema DEBE permitir seleccionar un perfil de tamaño predeterminado desde el catálogo de plantillas activas (*Small*, *Medium*, *Large*).
- **FR-003**: Para solicitudes SaaS y PaaS, el sistema DEBE proporcionar campos de texto descriptivo libre para detallar el software, plataforma, servicios de API o concurrencia estimada requerida.
- **FR-004**: Toda solicitud DEBE incluir obligatoriamente la especificación de vigencia temporal (rango de fechas desde/hasta, cuatrimestre o ciclo lectivo anual).
- **FR-005**: Al enviar una solicitud válida, el sistema DEBE registrarla en estado canónico `SOLICITADO` (presentado como *Pendiente*) y asignarle un identificador único de seguimiento visible para la cátedra.
- **FR-006**: El sistema DEBE ofrecer al Administrador una bandeja de solicitudes en estado `SOLICITADO` con información consolidada de la cátedra solicitante, requerimientos, vigencia y recursos estimados.
- **FR-007**: El sistema DEBE permitir al Administrador aprobar una solicitud seleccionando la plantilla de despliegue definitiva y registrando la transición a `EN_DESPLIEGUE`.
- **FR-008**: El sistema DEBE incluir una sección de opciones avanzadas en el flujo de aprobación que permita al Administrador ajustar parámetros de infraestructura (nodo, subred o configuración de almacenamiento) previo al despliegue.
- **FR-009**: Al confirmar la aprobación, el sistema DEBE orquestar automáticamente la creación del entorno virtual en la infraestructura institucional sin requerir comandos manuales externos.
- **FR-010**: Una vez completado el aprovisionamiento, el sistema DEBE transicionar el pedido a `ACTIVO` (presentado como *Disponible*), generar el registro del `Servicio` asociado y almacenar los datos de conexión (IP, URL, credenciales o tokens).
- **FR-011**: El sistema DEBE permitir al Administrador rechazar un pedido pendiente, requiriendo de forma obligatoria un motivo fundamentado por escrito y actualizando el estado a `RECHAZADO`.
- **FR-012**: El sistema DEBE permitir al Administrador devolver un pedido en estado `REQUIERE_AJUSTE`, adjuntando observaciones y sugerencias de modificación para la cátedra.
- **FR-013**: El sistema DEBE permitir a la cátedra consultar las observaciones de un pedido en estado `REQUIERE_AJUSTE`, modificar los campos de su solicitud y reenviarla a estado `SOLICITADO`, o cancelarla definitivamente (`CANCELADO`).
- **FR-014**: El sistema DEBE mostrar a la cátedra el listado y detalle de sus servicios en estado `ACTIVO`, exhibiendo su estado operativo en tiempo real, vigencia y parámetros de acceso.
- **FR-015**: La cátedra DEBE poder ejecutar acciones de autogestión supervisada sobre sus servicios activos: **Iniciar**, **Detener** y **Reiniciar**, con retroalimentación inmediata del resultado.
- **FR-016**: El sistema DEBE presentar métricas básicas de utilización del servicio (CPU, memoria y almacenamiento asignado).
- **FR-017**: El sistema DEBE proveer al Administrador un módulo para la administración completa (crear, listar, editar, activar/desactivar) de plantillas de recursos computacionales.
- **FR-018**: Todo cambio de estado en el ciclo de vida del pedido y servicio DEBE registrarse en un historial de auditoría de solo lectura, identificando autor (persona o sistema), fecha, estado anterior, estado nuevo y motivo.

---

### Key Entities *(include if feature involves data)*

- **Pedido**: Representa la solicitud formal de una cátedra. Atributos conceptuales: identificador único, cátedra solicitante, tipo de servicio (IaaS, PaaS, SaaS), plantilla solicitada/asignada, descripción de requerimientos, vigencia temporal (fecha inicio, fecha fin, período académico), estado actual canónico (`SOLICITADO`, `REQUIERE_AJUSTE`, `EN_DESPLIEGUE`, `ACTIVO`, `RECHAZADO`, `CANCELADO`, `ERROR`, `SUSPENDIDO`), fecha de creación y fecha de resolución.
- **Servicio**: Representa la instancia activa de cómputo resultante de un pedido aprobado. Atributos conceptuales: identificador único, referencia al pedido originario, cátedra propietaria, identificador de recurso en la infraestructura, dirección IP, URLs de acceso, credenciales/tokens de consumo, estado operativo (`RUNNING`, `STOPPED`, `PAUSED`, `ERROR`), fecha de vencimiento y fecha de alta.
- **PlantillaRecurso (Template)**: Representa los perfiles predefinidos de cómputo homologados. Atributos conceptuales: identificador único, nombre comercial (*Small*, *Medium*, *Large*, etc.), tipo de servicio aplicable, asignación de vCPU, memoria RAM, almacenamiento en disco, estado (activo/inactivo) y fecha de actualización.
- **ObservacionAjuste**: Registro de las observaciones y contrapropuestas intercambiadas entre la administración y la cátedra durante el estado de ajuste. Atributos conceptuales: identificador del pedido, emisor (administrador / cátedra), texto de la observación, valores sugeridos y fecha de emisión.
- **HistorialTransicion**: Bitácora inmutable de eventos de ciclo de vida. Atributos conceptuales: identificador de entidad (pedido/servicio), estado previo, estado resultante, actor responsable (docente, administrador o proceso automático del sistema), justificación/motivo y marca temporal.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El tiempo total requerido por un docente para completar y enviar una solicitud estructurada de recursos es inferior a 3 minutos.
- **SC-002**: El aprovisionamiento desatendido tras la aprobación administrativa culmina con el servicio disponible y accesible en menos de 5 minutos para entornos basados en plantillas estándar.
- **SC-003**: El 100% de los pedidos aprobados, rechazados o devueltos a ajuste cuentan con registro de trazabilidad completo (autor, motivo y fecha) sin pérdida de historial.
- **SC-004**: Al menos el 90% de los docentes evalúa satisfactoriamente la autonomía provista por los controles de autogestión (iniciar, detener, reiniciar y consulta de métricas) sin necesidad de abrir solicitudes de soporte operativo.
- **SC-005**: Cero incidentes de sobrecompromiso no advertido de capacidad física en el clúster durante el proceso de aprobación de pedidos.

---

## Assumptions

- **A-001**: Los usuarios de cátedra cuentan con credenciales institucionales habilitadas y asignadas a una cátedra válida dentro del portal de gestión.
- **A-002**: El acceso de los estudiantes al servicio final desplegado ocurre directamente por la red universitaria (o VPN institucional) sin requerir cuentas de usuario individuales en el portal administrativo de NAP.
- **A-003**: Los servidores físicos locales y el clúster de virtualización cuentan con conectividad de red interna y almacenamiento centralizado operativo para el despliegue automático de plantillas.
- **A-004**: Las plantillas predefinidas (*Small*, *Medium*, *Large*) cubren la mayor parte de las solicitudes IaaS iniciales; solicitudes excepcionales de mayor volumen son evaluadas puntualmente mediante las opciones avanzadas de aprobación.
