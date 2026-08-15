# Feature Specification: Panel simple para cátedra

**Feature Branch**: `002-panel-catedra-simple`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "para la spec catedra, mejorar el front y back de acuerdo a lo hablado, sin que sea muy compleja la spec, solo mejoras pequeñas."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pantalla principal simple para la cátedra (Priority: P1)

Una persona con rol cátedra —no necesariamente técnica— inicia sesión y llega a una pantalla
principal que le muestra únicamente lo que le importa para su trabajo diario: un acceso directo
para pedir un nuevo servicio y el estado de los servicios que ya tiene, sin tablas ni indicadores
que pertenecen al mundo del administrador (otras cátedras, estado del clúster, conteos globales).

**Why this priority**: Es el problema concreto que motivó esta spec: la pantalla actual reutiliza
la vista de administrador y no le aporta nada a la cátedra. Sin esto, ninguna otra mejora del
panel tiene dónde vivir.

**Independent Test**: Se puede probar iniciando sesión como usuario cátedra y verificando que la
pantalla principal solo contiene el acceso a "nuevo pedido" y el estado de sus propios servicios;
que no aparecen datos de otras cátedras ni de infraestructura física; y que la misma verificación
con un usuario administrador sigue mostrando su vista actual sin cambios.

**Acceptance Scenarios**:

1. **Given** un usuario con rol cátedra autenticado, **When** llega a la pantalla principal,
   **Then** ve un acceso directo para crear un pedido y el estado de sus propios servicios, y no
   ve el listado de otras cátedras ni el estado del nodo/clúster de infraestructura.
2. **Given** un usuario con rol administrador autenticado, **When** llega a la pantalla principal,
   **Then** sigue viendo la información agregada y de infraestructura que ya tenía disponible hoy.
3. **Given** una cátedra sin servicios todavía, **When** llega a la pantalla principal, **Then** ve
   un estado vacío que la invita a crear su primer pedido, en lugar de una tabla vacía sin contexto.

---

### User Story 2 - Pedir un servicio de forma rápida (Priority: P2)

Desde su pantalla principal, la cátedra inicia la creación de un pedido sin tener que navegar a
otra sección ni completar datos de infraestructura que no puede conocer (identificadores internos
de nodo o de máquina virtual). Solo elige qué tipo de servicio necesita, dentro de lo que su cuota
permite.

**Why this priority**: Es la segunda mitad del pedido original ("pedidos de forma fácil y
rápida"). Depende de que la pantalla principal (US1) ya tenga un lugar para este acceso directo.

**Independent Test**: Se puede probar de forma independiente iniciando el flujo de "nuevo pedido"
desde el acceso directo de la pantalla principal y completándolo sin que en ningún paso se pida un
identificador de infraestructura (nodo, VMID); el pedido creado debe quedar visible para la cátedra
con su estado inicial.

**Acceptance Scenarios**:

1. **Given** una cátedra con cuota disponible, **When** usa el acceso directo de "nuevo pedido"
   desde la pantalla principal, **Then** puede completar el pedido eligiendo únicamente el tipo de
   servicio deseado, sin ingresar datos de infraestructura.
2. **Given** una cátedra sin cuota disponible para lo que intenta pedir, **When** intenta crear el
   pedido, **Then** el sistema le informa en lenguaje claro que no tiene cuota suficiente, sin
   exponer detalles técnicos de infraestructura.
3. **Given** un pedido recién creado por la cátedra, **When** el administrador revisa su bandeja de
   gestión, **Then** el pedido aparece de inmediato, sin que la cátedra deba realizar ninguna
   acción adicional para "enviarlo" o notificarlo.

---

### Edge Cases

- Una cátedra con varios pedidos en distintos estados (solicitado, rechazado, activo) al mismo
  tiempo: la pantalla principal debe distinguir claramente cuáles requieren su atención (por
  ejemplo, un rechazo con motivo) de cuáles ya están resueltos.
- Un servicio de la cátedra queda en estado de error de infraestructura: la cátedra debe ver que
  "algo anda mal" en lenguaje simple, sin que se le muestre el detalle técnico del fallo (eso queda
  para la vista de administrador).
- Una cátedra con cero pedidos y cero servicios: la pantalla principal no debe verse como una
  versión vacía del dashboard de administrador, sino guiar directamente a crear el primer pedido.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST mostrar, como pantalla principal del rol cátedra, únicamente: un
  acceso directo para crear un pedido nuevo, el estado de sus pedidos recientes, y el estado de sus
  propios servicios.
- **FR-002**: El sistema MUST ocultar al rol cátedra la información reservada al rol
  administrador en esa pantalla: listado de otras cátedras, conteos globales del sistema y estado
  del nodo o clúster de infraestructura.
- **FR-003**: El sistema MUST permitir a la cátedra iniciar la creación de un pedido en un único
  paso desde su pantalla principal, sin navegación adicional previa.
- **FR-004**: El flujo de creación de pedido para la cátedra MUST limitarse a elegir el tipo de
  servicio deseado dentro de su cuota disponible; MUST NOT pedir identificadores internos de
  infraestructura (nodo, VMID u otro dato que la cátedra no puede conocer).
- **FR-005**: El sistema MUST presentar el estado de cada servicio de la cátedra en lenguaje no
  técnico (por ejemplo: activo, apagado, con problemas) en lugar de códigos o métricas de
  infraestructura cruda.
- **FR-006**: El sistema MUST mostrar a la cátedra el consumo de su cuota (vCPU, RAM, disco) en
  relación a lo que tiene asignado, sin exponer métricas del nodo físico compartido.
- **FR-007**: Todo pedido nuevo creado por una cátedra MUST quedar visible de inmediato en la
  bandeja de gestión del administrador, sin acción manual adicional de sincronización.
- **FR-008**: El sistema MUST seguir permitiendo al administrador aprobar, rechazar y gestionar el
  ciclo de vida de cada pedido desde su bandeja, como ya ocurre hoy.
- **FR-009**: El sistema MUST seguir mostrando al rol administrador la vista actual (cátedras
  registradas, estado de infraestructura, conteos globales); esta spec no le quita información al
  administrador.

### Key Entities

- **Pedido**: solicitud de un servicio hecha por una cátedra; ya existe en el sistema. Esta spec no
  agrega estados ni campos, solo cambia qué parte de su información se muestra y dónde.
- **Servicio**: recurso desplegado asociado a una cátedra; ya existe en el sistema. Esta spec
  agrega una forma simplificada de presentar su estado y consumo al rol cátedra, sin crear un
  nuevo tipo de dato.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona con rol cátedra puede completar la creación de un pedido en menos de 1
  minuto desde que llega a la pantalla principal, sin ayuda externa.
- **SC-002**: El 100% de los elementos visibles en la pantalla principal de un usuario cátedra
  corresponden a sus propios pedidos, sus propios servicios, o al acceso para crear un pedido nuevo
  — cero elementos de otras cátedras o de infraestructura física.
- **SC-003**: Un pedido nuevo aparece en la bandeja del administrador sin demora perceptible
  (dentro de la misma sesión de uso, sin recargar manualmente ni esperar un proceso en segundo
  plano).
- **SC-004**: Una persona sin formación técnica puede identificar si un servicio propio "funciona
  bien" o "tiene un problema" con solo mirar la pantalla principal, sin necesitar explicación
  adicional.

## Assumptions

- El significado de "mejorar el front y back" se acota a lo hablado en la sesión previa: la
  pantalla principal del rol cátedra y el punto de entrada para crear un pedido. No incluye
  rediseñar la bandeja de gestión del administrador (ya existe y ya funciona), ni agregar
  funcionalidades nuevas fuera de pedidos y servicios (por ejemplo, no incluye notificaciones push,
  auditoría ni WebSockets).
- La cátedra ya elige un tipo de servicio de un catálogo existente (no un identificador crudo de
  Proxmox); esta spec no cambia esa mecánica, solo cómo se accede a ella y qué tan simple se ve.
- El mapeo de estado técnico a lenguaje simple usa como base los estados de servicio ya existentes:
  en ejecución → "activo", detenido o pausado → "apagado", error → "con problemas".
- Esta spec no modifica los datos ni cálculos de cuota ya existentes; solo cambia cómo se presentan
  a la cátedra (resumen simple en vez de tabla técnica).
- "Sin demora perceptible" (SC-003) se cumple si el administrador ve el pedido nuevo la próxima vez
  que consulta su bandeja dentro de la misma sesión, sin requerir que la cátedra realice una acción
  extra de envío o confirmación.
