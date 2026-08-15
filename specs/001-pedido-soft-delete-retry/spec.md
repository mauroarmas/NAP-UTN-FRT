# Feature Specification: Recuperación de Errores y Eliminación Lógica de Pedidos/Servicios

**Feature Branch**: `001-pedido-soft-delete-retry`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Refinamiento de la máquina de estados de Pedidos/Servicios (Hito 3 - backend, según PLAN_TRABAJO.md): 1) Soft delete en Pedido y Servicio para conservar el historial académico de recursos consumidos por cátedra, aunque el contenedor ya fue eliminado en Proxmox. 2) Recuperación de errores / reintento de despliegue: hoy la máquina de estados permite ERROR → EN_DESPLIEGUE pero nada vuelve a ejecutar el despliegue real, dejando el pedido colgado. Se necesita una vía explícita de reintento pseudo-idempotente que reutilice el VMID si ya se había asignado. Alcance: solo backend."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reintentar un despliegue fallido (Priority: P1)

Un administrador revisa los pedidos y encuentra uno que quedó en estado de error porque el despliegue contra la infraestructura falló (por ejemplo, un timeout o un error temporal). En lugar de tener que pedirle a la cátedra que solicite un pedido nuevo desde cero, el administrador dispara un reintento sobre ese mismo pedido.

**Why this priority**: Sin esto, cualquier fallo transitorio deja un pedido permanentemente inutilizable y obliga a recrear todo el flujo manualmente en la base de datos. Es el problema operativo más urgente: hoy la máquina de estados promete una recuperación que en la práctica no ocurre.

**Independent Test**: Se puede probar de forma aislada llevando un pedido a estado de error (simulando una falla de infraestructura), disparando el reintento, y verificando que el pedido termina activo con su recurso desplegado — sin tocar nada de soft delete.

**Acceptance Scenarios**:

1. **Given** un pedido en estado de error tras un intento de despliegue fallido, **When** un administrador solicita el reintento, **Then** el sistema vuelve a ejecutar el proceso de despliegue y, si tiene éxito, el pedido queda activo con su recurso disponible.
2. **Given** un pedido en estado de error, **When** un administrador solicita el reintento y la infraestructura vuelve a fallar, **Then** el pedido permanece en estado de error con un nuevo registro de historial que describe este nuevo intento y su motivo de falla (no se pierde ni se sobrescribe silenciosamente el intento anterior).
3. **Given** un pedido que NO está en estado de error (por ejemplo, ya está activo o fue rechazado), **When** se solicita un reintento sobre él, **Then** el sistema rechaza la operación indicando que la transición no es válida desde su estado actual.
4. **Given** un pedido en error que ya tenía un identificador de recurso (VMID) asignado del intento anterior, **When** se reintenta y ese identificador sigue disponible, **Then** el sistema lo reutiliza en vez de reservar uno nuevo innecesariamente.
5. **Given** un pedido en error cuyo identificador de recurso anterior ya no es válido o fue tomado por otro recurso, **When** se reintenta, **Then** el sistema asigna automáticamente un identificador nuevo sin fallar.
6. **Given** un pedido que atraviesa varios reintentos sucesivos, **When** se consulta su historial, **Then** cada intento (éxito o falla) aparece como una entrada distinta y ordenada cronológicamente.

---

### User Story 2 - Preservar el historial académico al dar de baja pedidos y servicios (Priority: P2)

Un administrador necesita dar de baja un servicio cuyo contenedor ya no se usa (por ejemplo, terminó el cuatrimestre). Al eliminarlo, el sistema libera el recurso real en la infraestructura, pero el registro del servicio y del pedido que lo originó siguen existiendo para poder reconstruir, meses o años después, cuánto consumió cada cátedra.

**Why this priority**: Es importante para la trazabilidad académica a largo plazo, pero no bloquea la operación diaria del sistema de la misma forma que un pedido colgado en error — por eso va después del reintento.

**Independent Test**: Se puede probar dando de baja un servicio existente y verificando por un lado que desaparece de los listados normales, y por otro que su información (cátedra, recursos asignados, fechas) sigue siendo recuperable en una consulta histórica, sin depender de la funcionalidad de reintento.

**Acceptance Scenarios**:

1. **Given** un servicio activo, **When** un administrador lo elimina, **Then** el recurso real en la infraestructura se libera y el registro del servicio queda marcado como eliminado (no se borra de la base de datos).
2. **Given** un servicio o pedido marcado como eliminado, **When** cualquier usuario consulta los listados normales de Servicios o Pedidos, **Then** esos registros no aparecen.
3. **Given** un servicio o pedido marcado como eliminado, **When** se consulta específicamente el historial de consumo de una cátedra, **Then** el registro aparece incluido y claramente identificado como eliminado, junto con la fecha en que ocurrió.
4. **Given** un pedido cuyo servicio asociado fue marcado como eliminado, **When** se revisa el pedido, **Then** la relación entre ambos y su historial de estados permanece intacta y consultable.
5. **Given** un servicio o pedido ya marcado como eliminado, **When** se intenta eliminarlo nuevamente, **Then** el sistema no falla de forma inesperada (operación idempotente o mensaje claro de "ya estaba eliminado").
6. **Given** un pedido que nunca llegó a desplegarse (por ejemplo, rechazado o abandonado en solicitud), **When** un administrador lo da de baja explícitamente, **Then** el pedido queda marcado como eliminado sin ejecutar ninguna operación contra la infraestructura.
7. **Given** un pedido cuyo servicio asociado sigue vigente, **When** un administrador intenta dar de baja el pedido, **Then** el sistema rechaza la operación e indica que primero debe darse de baja el servicio para liberar el recurso real.

### Edge Cases

- ¿Qué pasa si se solicita un reintento y la infraestructura vuelve a estar caída? El pedido debe volver (o permanecer) en estado de error con el nuevo intento registrado, sin corromper el estado de la base de datos ni dejar recursos duplicados a medio crear.
- ¿Qué pasa si, entre el fallo original y el reintento, el identificador de recurso (VMID) que tenía reservado el pedido fue tomado por otro despliegue? El sistema debe detectar el conflicto y asignar uno nuevo, no debe fallar silenciosamente ni reutilizar un identificador ajeno.
- ¿Qué pasa si se pide eliminar un servicio que nunca llegó a tener un recurso real desplegado (por ejemplo, el despliegue nunca se completó)? Debe poder marcarse como eliminado sin depender de una operación contra la infraestructura que no tiene sentido ejecutar.
- ¿Qué pasa con la cuota de una cátedra cuando uno de sus servicios se marca como eliminado? Ese servicio debe dejar de contar como consumo activo inmediatamente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE permitir a un administrador solicitar un nuevo intento de despliegue para un pedido que quedó en estado de error, sin necesidad de crear un pedido nuevo.
- **FR-002**: El sistema DEBE rechazar la solicitud de reintento si el pedido no se encuentra en estado de error, indicando claramente que la transición no es válida.
- **FR-003**: Al reintentar, el sistema DEBE ejecutar nuevamente el proceso completo de aprovisionamiento del recurso en la infraestructura (selección de nodo, creación del contenedor), equivalente al intento original.
- **FR-004**: El sistema DEBE reutilizar el identificador de recurso (VMID) previamente asignado al pedido si sigue siendo válido y no está en uso; en caso contrario, DEBE asignar uno nuevo automáticamente.
- **FR-005**: El sistema DEBE dejar registro de cada intento de despliegue —inicial y reintentos—, incluyendo resultado y detalle del error cuando corresponda, de forma visible para revisión posterior.
- **FR-006**: Solo usuarios con rol administrador DEBEN poder solicitar el reintento de un pedido, en línea con el resto de las transiciones administrativas de la máquina de estados existente.
- **FR-007**: El sistema DEBE permitir marcar un Pedido o Servicio como eliminado sin borrar físicamente su información histórica.
- **FR-008**: El sistema DEBE registrar la fecha y hora en que un Pedido o Servicio fue marcado como eliminado.
- **FR-009**: Las vistas y listados normales de Pedidos y Servicios NO DEBEN mostrar por defecto los registros marcados como eliminados.
- **FR-010**: Al eliminar un Servicio con un recurso activo en la infraestructura, el sistema DEBE continuar intentando liberar ese recurso (comportamiento actual) antes de marcarlo como eliminado; si la liberación falla, el registro NO DEBE marcarse como eliminado.
- **FR-011**: El sistema DEBE preservar las relaciones históricas entre Pedido, Servicio, Cátedra y su historial de eventos para los registros eliminados, de forma que el consumo de recursos pasado por cátedra siga siendo consultable.
- **FR-012**: Los registros marcados como eliminados NO DEBEN contar contra la cuota de recursos disponible de su cátedra.
- **FR-013**: El sistema DEBE ofrecer una acción explícita e independiente para dar de baja un Pedido, disponible cualquiera sea su estado actual, incluidos los pedidos que nunca llegaron a desplegarse (por ejemplo, abandonados en solicitud o rechazados).
- **FR-014**: El sistema DEBE rechazar la baja de un Pedido cuyo Servicio asociado siga vigente (no dado de baja), indicando que primero debe darse de baja el Servicio para liberar el recurso real; esto evita dejar recursos huérfanos activos en la infraestructura.
- **FR-015**: Solo usuarios con rol administrador DEBEN poder dar de baja un Pedido o un Servicio.

### Key Entities

- **Pedido**: Solicitud de un recurso hecha por una cátedra. Además de su ciclo de estados actual, ahora puede quedar marcado como eliminado sin perder su historial, y puede registrar múltiples intentos de despliegue cuando pasa por error.
- **Servicio**: Recurso desplegado (contenedor) asociado a un pedido aprobado. Ahora puede quedar marcado como eliminado una vez liberado el recurso real, conservando su información de consumo (recursos asignados, cátedra, fechas).
- **Historial de Pedido**: Registro cronológico de cada cambio de estado de un pedido, que ahora también refleja cada intento de despliegue (incluidos los reintentos) y su resultado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un administrador puede recuperar un pedido atascado en estado de error y llevarlo a estado activo en un solo paso, sin intervención manual directa sobre la base de datos.
- **SC-002**: El 100% de los intentos de despliegue de un pedido (inicial y reintentos) quedan visibles en su historial, permitiendo reconstruir la secuencia completa de eventos ante cualquier auditoría.
- **SC-003**: Los reportes de consumo histórico por cátedra incluyen el 100% de los servicios y pedidos eliminados de períodos anteriores, sin necesidad de restaurar copias de seguridad.
- **SC-004**: Los listados normales de "Servicios" y "Pedidos" no muestran ningún registro eliminado, manteniendo la experiencia actual del usuario sin cambios visibles salvo la nueva capacidad de reintento.
- **SC-005**: Ningún registro eliminado lógicamente sigue contando contra la cuota de recursos disponible de su cátedra.

## Assumptions

- El reintento de despliegue reutiliza la misma lógica central del despliegue original (selección de nodo, construcción de la configuración del contenedor); solo cambia la validación del estado de entrada y el manejo del identificador de recurso.
- No hay un límite máximo de reintentos automáticos por pedido en esta iteración; si un administrador decide abandonar el intento, puede usar la transición de rechazo que ya existe en la máquina de estados.
- El acceso a los registros marcados como eliminados (para reportes o auditoría histórica) es una vía de consulta separada de los listados por defecto; el diseño concreto de esa consulta se define en la fase de planificación, no en este documento.
- La baja de Pedido es una acción explícita e independiente de la baja de Servicio (no ocurre en cascada automática): dar de baja un Servicio no da de baja su Pedido, y viceversa. El orden operativo esperado es dar de baja primero el Servicio (que libera el recurso real) y luego el Pedido, si se desea.
- Los pedidos que nunca llegaron a tener un servicio desplegado también pueden marcarse como eliminados sin interactuar con la infraestructura real.
- Esta funcionalidad es exclusivamente de backend; cualquier cambio de interfaz (por ejemplo, un botón "Reintentar" o una vista de "eliminados") queda fuera de este documento y corresponde a un hito de frontend posterior.
- Los reportes de auditoría histórica mencionados en este documento son de solo lectura; su exposición completa (filtros, vista dedicada) se cubre en el hito de Trazabilidad y Logs de Auditoría, no en este.
