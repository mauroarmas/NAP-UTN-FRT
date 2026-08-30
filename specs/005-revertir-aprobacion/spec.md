# Feature Specification: Revertir una aprobación antes del despliegue

**Feature Branch**: `005-revertir-aprobacion`

**Created**: 2026-08-30

**Status**: Draft

**Input**: User description: "Un pedido ya aprobado no se puede deshacer. La transición APROBADO → RECHAZADO existe en la tabla de transiciones válidas pero está reservada al sistema (TRANSICIONES_SISTEMA), que la usa solo cuando vence la reserva de capacidad; si un administrador la intenta recibe 409 'la ejecuta el sistema durante el despliegue'. Consecuencia real, reproducida durante la validación T091 del 2026-08-29: el administrador aprobó un pedido que excedía la capacidad (algo que FR-015 permite deliberadamente, con justificación registrada), el clúster quedó en -12 vCPU y -24 GB de RAM comprometidos, y eso bloqueó la reactivación de un servicio pausado de OTRA cátedra con 409 sin_capacidad. El administrador no tiene ninguna vía para liberar esa capacidad: las únicas salidas desde APROBADO son desplegar el pedido (materializando el sobrecompromiso) o esperar hasta 24 horas a que el trabajo expirar_reservas libere la reserva sola. Durante esa ventana el error de una cátedra degrada el servicio de las demás. Se necesita que el administrador pueda revertir una aprobación antes del despliegue, liberando la reserva en el acto, con el motivo registrado en el historial y avisando a la cátedra afectada; hay que definir qué pasa si el despliegue ya empezó, si la reversión debe distinguirse de un rechazo original en el historial, y si la cátedra puede volver a pedir lo mismo."

> **Nota de lectura**: el `FR-015` que se menciona en el texto de entrada es el de la **feature 004** (sobrecompromiso deliberado con justificación registrada), no un requisito de esta spec. Los requisitos de esta feature son FR-001 a FR-014.

## Resumen del problema

Aprobar un pedido **compromete capacidad del clúster en el acto**, aunque el servicio todavía no
exista. Esa es la corrección central de la feature 004 y funciona como se diseñó. Lo que falta es la
otra mitad: **una aprobación no se puede deshacer**.

Hoy, desde un pedido aprobado y no desplegado, solo hay dos salidas:

1. **Desplegarlo**, materializando una decisión que quizás fue un error.
2. **Esperar** hasta 24 horas a que el vencimiento automático de la reserva la libere.

No hay una tercera. El administrador que aprueba de más —algo que el sistema **le permite hacer
deliberadamente**— no tiene forma de corregirse.

### El daño no queda contenido en la cátedra que pidió

Durante la validación de la feature 004 (2026-08-29) esto se reprodujo de punta a punta:

1. El administrador aprobó un pedido de 16 vCPU y 32 GB sobre un clúster de 4 vCPU y 7,7 GB,
   dejando la justificación que el sistema le exige.
2. La capacidad comprometida quedó en **-12 vCPU y -24 GB**.
3. Una cátedra **distinta**, sin relación con ese pedido, intentó reactivar un servicio suyo que el
   sistema había pausado por inactividad. El portal se lo negó: *"Ahora mismo el clúster no tiene
   capacidad libre para volver a encender este servicio."*
4. Nadie pudo hacer nada hasta que venció la reserva.

Es decir: **el error de una cátedra degrada el servicio de las demás durante hasta 24 horas**, y la
persona que podría arreglarlo no tiene el botón para hacerlo. El sistema le ofreció al administrador
una decisión reversible en apariencia (con advertencia y justificación) que en la práctica no lo es.

> [!NOTE]
> Esta feature **no** discute si el sobrecompromiso debe permitirse. El Principio IV lo permite
> expresamente y esta spec no lo toca. Lo que agrega es la vuelta atrás.

## Clarifications

### Session 2026-08-30

- Q: ¿Revertir una aprobación es lo mismo que rechazar el pedido de entrada? → A: **No.** El
  historial debe distinguirlos. Un rechazo original dice "esto no se va a hacer"; una reversión dice
  "esto se había aprobado y se dio marcha atrás antes de construirlo". Para la cátedra son
  situaciones distintas y para la auditoría también: reconstruir el consumo histórico exige saber
  que hubo capacidad comprometida durante un rato.
- Q: ¿Se puede revertir un pedido cuyo despliegue ya arrancó? → A: **No.** Una vez que el
  aprovisionamiento empezó a tocar la infraestructura, la vuelta atrás deja de ser una decisión
  administrativa y pasa a ser una baja de servicio, que ya tiene su propio camino. El sistema debe
  rechazar el intento con un mensaje que explique cuál es la vía correcta, no con un error genérico.
- Q: ¿La cátedra puede volver a pedir lo mismo después de una reversión? → A: **Sí, sin
  restricciones.** La reversión no es una sanción ni un juicio sobre la cátedra: lo más común es que
  el pedido se rehaga cuando haya capacidad. Bloquear el nuevo pedido castigaría a quien no cometió
  el error.
- Q: ¿Hace falta un motivo para revertir? → A: **Sí, obligatorio.** La aprobación sobrecomprometida
  ya exige justificación; deshacerla sin explicación dejaría el historial contando la mitad de la
  película. Es además la única forma de que la cátedra entienda por qué le sacaron algo que ya tenía
  aprobado.
- Q: ¿Quién puede revertir? → A: **Solo el rol administrador**, igual que aprobar. No es una acción
  que la cátedra ejerza sobre lo propio: la cátedra pide, el administrador resuelve.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deshacer una aprobación que comprometió de más (Priority: P1)

Un administrador aprueba un pedido y advierte enseguida que se equivocó: eligió el pedido que no
era, o aceptó un sobrecompromiso que no debería haber aceptado. Antes de que el servicio se
despliegue, revierte la aprobación dejando el motivo, y la capacidad vuelve a estar disponible en el
acto.

**Why this priority**: Es la razón de ser de la feature. Sin esto, un error de un minuto cuesta 24
horas de capacidad bloqueada para todo el clúster.

**Independent Test**: Aprobar un pedido, verificar que la capacidad libre bajó, revertir la
aprobación con un motivo, y comprobar que la capacidad volvió al valor previo sin esperar ningún
vencimiento.

**Acceptance Scenarios**:

1. **Given** un pedido aprobado cuyo servicio todavía no se desplegó, **When** el administrador
   revierte la aprobación indicando el motivo, **Then** el pedido deja de estar aprobado, la
   capacidad que tenía comprometida vuelve a figurar como libre de inmediato, y la operación queda
   registrada en el historial con quién la hizo y por qué.
2. **Given** ese mismo pedido revertido, **When** se consulta la capacidad del clúster, **Then** los
   valores coinciden exactamente con los de antes de la aprobación.
3. **Given** un intento de revertir sin indicar motivo, **When** se confirma la operación, **Then**
   el sistema la rechaza y explica que el motivo es obligatorio, sin haber tocado el pedido ni la
   capacidad.
4. **Given** un pedido en estado solicitado (nunca aprobado), **When** se intenta revertir,
   **Then** el sistema indica que no hay ninguna aprobación que deshacer y sugiere rechazarlo.

---

### User Story 2 - La cátedra entiende qué pasó con su pedido (Priority: P1)

Una cátedra tenía un pedido aprobado y esperaba su servicio. La aprobación se revierte. La cátedra
ve, sin tener que preguntar, que su pedido volvió atrás, por qué, y qué puede hacer al respecto.

**Why this priority**: Un pedido que estaba aprobado y deja de estarlo, en silencio, es
indistinguible de una falla del portal. La cátedra pierde la confianza en los estados que el sistema
le muestra, que es justamente lo que la máquina de estados existe para sostener.

**Independent Test**: Con una cuenta de cátedra, mirar un pedido propio antes y después de que un
administrador revierta su aprobación, y comprobar que el cambio y su motivo son visibles y
comprensibles sin conocimientos técnicos.

**Acceptance Scenarios**:

1. **Given** una cátedra con un pedido aprobado, **When** el administrador revierte la aprobación,
   **Then** la cátedra ve el pedido en un estado que refleja lo ocurrido, junto con el motivo que
   dejó el administrador, redactado de forma entendible.
2. **Given** ese pedido revertido, **When** la cátedra crea un pedido nuevo por el mismo recurso,
   **Then** el sistema lo acepta con normalidad y lo pone en la cola del administrador.
3. **Given** ese pedido revertido, **When** la cátedra consulta su historial, **Then** se distingue
   con claridad de un pedido que fue rechazado de entrada.

---

### User Story 3 - La reversión no se confunde con nada más en la auditoría (Priority: P2)

Un administrador revisa meses después qué pasó con los recursos de una cátedra. Necesita poder
distinguir tres cosas que hoy terminarían pareciendo iguales: un pedido rechazado de entrada, una
aprobación revertida por decisión de una persona, y una reserva que venció sola porque el despliegue
nunca ocurrió.

**Why this priority**: El Principio V exige que el consumo histórico sea reconstruible. Si las tres
situaciones se registran igual, se pierde la información de que hubo capacidad comprometida y por
cuánto tiempo. Es P2 y no P1 porque el daño aparece más tarde, no en la operación diaria.

**Independent Test**: Producir los tres casos sobre pedidos distintos y verificar que el historial
permite distinguirlos sin ambigüedad, incluyendo quién fue el autor de cada uno.

**Acceptance Scenarios**:

1. **Given** un pedido rechazado de entrada, uno con la aprobación revertida y uno cuya reserva
   venció sola, **When** se consulta el historial de los tres, **Then** cada uno indica con
   claridad cuál de las tres cosas ocurrió.
2. **Given** una aprobación revertida, **When** se consulta su historial, **Then** figura la persona
   que la revirtió; **and** la entrada de la aprobación original sigue presente, sin sobrescribirse.
3. **Given** una reserva vencida sola, **When** se consulta su historial, **Then** el autor es el
   sistema y no una persona.

---

### Edge Cases

- **El despliegue ya empezó.** Si el aprovisionamiento arrancó, revertir deja de ser una decisión
  administrativa: ya hay algo construyéndose en la infraestructura. El sistema rechaza la reversión y
  explica cuál es el camino correcto (dar de baja el servicio una vez que exista).
- **Dos administradores intentan revertir el mismo pedido a la vez.** La capacidad debe liberarse una
  sola vez. Un doble descuento inflaría el saldo libre e invitaría a aprobar sobre capacidad que no
  existe, que es exactamente el defecto que la feature 004 vino a corregir.
- **Revertir y desplegar a la vez.** Si una reversión y un despliegue se disparan sobre el mismo
  pedido simultáneamente, solo uno puede prosperar; el otro debe fallar con un mensaje que diga qué
  pasó, y el pedido no puede quedar en un estado ambiguo.
- **La reserva ya había vencido sola.** Si el vencimiento automático se adelantó a la persona, la
  reversión no debe volver a liberar capacidad ni contradecir lo que ya registró el sistema.
- **Un pedido de renovación revertido.** Una renovación aprobada y revertida no debe alterar el
  servicio que renovaba: ese servicio conserva su fecha de vencimiento anterior y sigue funcionando.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El administrador MUST poder revertir la aprobación de un pedido mientras el servicio no
  se haya desplegado.
- **FR-002**: La reversión MUST exigir un motivo; el sistema MUST rechazarla si el motivo está vacío,
  sin modificar el pedido ni la capacidad.
- **FR-003**: La reversión MUST liberar la capacidad comprometida por ese pedido de forma inmediata,
  sin depender de ningún trabajo periódico.
- **FR-004**: La liberación de capacidad y el cambio de estado del pedido MUST constituir una
  operación indivisible: MUST NOT quedar un pedido revertido cuya capacidad siga comprometida, ni
  capacidad liberada sobre un pedido que sigue aprobado.
- **FR-005**: El sistema MUST impedir que dos reversiones simultáneas sobre el mismo pedido liberen la
  capacidad dos veces.
- **FR-006**: El sistema MUST rechazar la reversión de un pedido cuyo despliegue ya comenzó,
  indicando en el mensaje cuál es la vía correcta para dar de baja el servicio.
- **FR-007**: El sistema MUST rechazar la reversión de un pedido que nunca estuvo aprobado,
  indicando la acción que corresponde en su lugar.
- **FR-008**: Toda reversión MUST quedar registrada en el historial del pedido con su autor humano y
  su motivo, y MUST NOT sobrescribir el registro de la aprobación original.
- **FR-009**: El historial MUST permitir distinguir una aprobación revertida por una persona de un
  rechazo original y del vencimiento automático de una reserva.
- **FR-010**: La cátedra dueña del pedido MUST poder ver que su pedido fue revertido y el motivo,
  expresado en lenguaje comprensible sin conocimientos de administración de sistemas.
- **FR-011**: La cátedra MUST poder volver a pedir el mismo recurso después de una reversión, sin
  restricción ni demora impuesta por el sistema.
- **FR-012**: Revertir un pedido MUST ser exclusivo del rol administrador; el rol cátedra MUST NOT
  poder revertir, ni siquiera sobre pedidos propios.
- **FR-013**: Revertir la aprobación de una renovación MUST NOT alterar el servicio que se renovaba:
  conserva su vencimiento previo y su estado.
- **FR-014**: Si la reserva del pedido ya había vencido por sí sola, el sistema MUST informar que no
  hay nada que revertir en vez de liberar capacidad por segunda vez.

### Key Entities

- **Pedido**: incorpora la posibilidad de volver desde "aprobado" a un estado final por decisión
  humana, distinguible del rechazo inicial y del vencimiento automático.
- **Entrada de historial del pedido**: incorpora la reversión como un hecho propio, con autor humano
  y motivo, conviviendo con la entrada de la aprobación que revierte.
- **Reserva de capacidad**: pasa a tener una segunda forma de terminar además del vencimiento por
  tiempo: la liberación deliberada por una persona.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un administrador que advierte un error en su aprobación puede liberar la capacidad
  comprometida en menos de un minuto, sin esperar ningún proceso automático.
- **SC-002**: Tras revertir una aprobación, la capacidad libre del clúster vuelve exactamente a los
  valores previos a esa aprobación.
- **SC-003**: El tiempo máximo durante el cual una aprobación equivocada puede degradar el servicio
  de otras cátedras baja de 24 horas a lo que tarde una persona en advertirlo.
- **SC-004**: Cualquier persona que audite el historial puede distinguir, sin ayuda externa, entre un
  pedido rechazado de entrada, una aprobación revertida y una reserva vencida sola.
- **SC-005**: Una cátedra cuyo pedido fue revertido puede explicar, leyendo solo lo que el portal le
  muestra, qué pasó con su pedido y qué puede hacer a continuación.
- **SC-006**: Ninguna secuencia de reversiones concurrentes produce una capacidad libre mayor que la
  real.

## Assumptions

- El punto sin retorno es el **comienzo del despliegue**, no su finalización: en cuanto el sistema
  empieza a tocar la infraestructura, la vuelta atrás es una baja de servicio y no una decisión
  administrativa.
- La reversión se ofrece desde la misma pantalla en la que el administrador gestiona los pedidos, al
  lado de las acciones que ya conoce; no se asume ninguna herramienta nueva.
- El aviso a la cátedra usa el mismo canal por el que ya se entera del estado de sus pedidos. Si en
  el futuro se suma el correo institucional que el cliente ofreció (reunión del 2026-08-25), esta
  notificación es candidata natural a viajar por ahí, pero esta feature no depende de eso.
- No se toca el vencimiento automático de reservas: sigue existiendo como red de seguridad para los
  pedidos que nadie mira.
- No se toca la posibilidad de sobrecomprometer deliberadamente: el Principio IV la permite y esta
  feature solo agrega la vuelta atrás.
- El volumen de reversiones es bajo (son correcciones de error, no operación rutinaria), así que no
  se asumen requisitos especiales de rendimiento más allá de la atomicidad.

## Impacto sobre la constitución

Esta feature **no requiere enmienda**. Se apoya en principios vigentes y cubre un hueco que ninguno
de ellos había previsto explícitamente:

- **Principio II** (la máquina de estados es la única fuente de verdad): la transición
  `aprobado → rechazado` ya figura como válida, pero hoy solo la puede ejecutar el sistema. Esta
  feature le da un segundo ejecutor legítimo —el administrador— sin agregar caminos que esquiven la
  función central de transición. El principio exige además que toda transición declarada válida tenga
  un ejecutor real; acá gana uno más, no pierde ninguno.
- **Principio III** (toda operación debe ser recuperable): es el principio que hoy queda incumplido.
  Una aprobación es una operación que compromete recursos reales y no tiene vuelta atrás por decisión
  humana. La cláusula de que no debe quedar "capacidad huérfana" se apoya hoy solo en el vencimiento
  automático, que tarda hasta 24 horas.
- **Principio IV** (la capacidad se controla al aprobar): se refuerza. El principio exige que
  sobrecomprometer sea un acto deliberado y nunca accidental; esta feature agrega que además sea
  **reversible**, que es lo que vuelve honesta la advertencia que el sistema ya muestra.
- **Principio V** (el historial académico no se destruye): FR-008 y FR-009 lo respetan — la reversión
  agrega historia, no la reescribe.
- **Principio VI** (la cátedra pide y observa): FR-010 y FR-012 lo respetan — la cátedra se entera y
  entiende, pero no revierte.

## Contexto de origen

El defecto se descubrió ejecutando la validación T091 de la feature 004 contra infraestructura real
(Proxmox VE 9.2.2) el 2026-08-29. No surgió de una revisión de código sino de la interacción entre
dos escenarios de prueba que se pisaron: el sobrecompromiso deliberado de E5 dejó el clúster en
negativo y eso hizo fallar la reactivación de E7 sobre una cátedra distinta. La secuencia completa
está registrada en
[`specs/004-unificar-usuario-catedra/quickstart.md`](../004-unificar-usuario-catedra/quickstart.md).
