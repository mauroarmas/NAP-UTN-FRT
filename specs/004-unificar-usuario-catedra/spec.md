# Feature Specification: Unificación usuario–cátedra y control de recursos por aprobación

**Feature Branch**: `004-unificar-usuario-catedra`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "me gustaria que unifiquemos a el usuario y la cátedra, siendo que un solo usuario puede tener varias catedras y ya no se le definirian limites de recursos, sino simplemente los servicios que tendria, si no se usan se deberian pausar para liberar recursos, es el admin quien aceptando los pedidos de cierta forma controla los recursos que tendria una cátedra, analiza bien casos de uso o inconsistencias que puede tener esta forma de trabajo a mi me parece mejor y más simple."

## Resumen del cambio

Hoy el sistema modela la cátedra como un inquilino con **cuota fija** (vCPU, RAM, disco) y ata cada
persona usuaria a **una sola** cátedra. Esta feature propone tres cambios acoplados entre sí:

1. **La persona es la cuenta; la cátedra es una de sus materias.** Una misma persona usuaria opera
   varias cátedras desde una sola sesión, sin cuentas separadas ni volver a iniciar sesión.
2. **Se elimina el techo por cátedra, no la contabilidad de capacidad.** La cátedra ya no tiene un
   límite de vCPU/RAM/disco declarado por adelantado; tiene, simplemente, los servicios que le
   fueron aprobados. Pero el clúster sigue teniendo los recursos finitos que tiene, y el sistema
   sigue llevando esa cuenta — lo que cambia es **quién y cuándo** decide, no si se controla.
3. **El control se traslada al momento de la aprobación, y la aprobación reserva.** El
   administrador decide caso por caso con la capacidad real a la vista; aprobar **compromete** esa
   capacidad de inmediato, aunque el servicio todavía no exista.
4. **La capacidad se recupera por dos vías.** Un vencimiento por servicio, que es la vía
   determinista y garantizada, y el pausado automático de lo que nadie usa, que es la vía
   oportunista en el medio.

**Distinción central**: lo que se elimina es el *techo por cátedra declarado por adelantado*. Lo que
se conserva —y se refuerza— es la *contabilidad de capacidad del clúster*. Confundir ambas cosas es
lo que haría peligroso este modelo.

> [!IMPORTANT]
> Este cambio **contradice el Principio IV de la constitución vigente** ("Aislamiento y cuota por
> cátedra", que exige validar la cuota antes de aprovisionar) y afecta la redacción del Principio VI
> (que describe la vista de cátedra en términos de "consumo respecto de su cuota"). Requiere una
> enmienda **MAJOR** de la constitución antes de implementarse. Ver la sección
> [Impacto sobre la constitución](#impacto-sobre-la-constitución).

## Clarifications

### Session 2026-08-16

- Q: ¿Una cátedra pertenece a exactamente una persona usuaria, o varias personas pueden compartir la
  misma cátedra? → A: **Titular único.** Cada cátedra tiene exactamente una persona responsable. Una
  persona puede tener varias cátedras, pero una cátedra no se comparte. La migración debe elegir un
  titular para las cátedras que hoy tengan más de un usuario asignado.
- Q: ¿El pausado por falta de uso lo ejecuta el sistema por su cuenta, o solo lo sugiere? → A:
  **Automático**, con aviso previo a la cátedra y período de gracia antes de ejecutarse. Es el
  mecanismo que reemplaza a la cuota como forma de recuperar capacidad, así que no puede depender de
  que alguien entre a confirmarlo.
- Q: Sin cuota por cátedra, ¿el sistema puede impedirle al administrador aprobar un pedido que el
  clúster no soporta? → A: **Advertir pero permitir**, dejando registrada la justificación. La
  decisión es del administrador; el sobrecompromiso queda posible pero nunca accidental ni sin
  rastro.
- Q: ¿"Pausar" un contenedor libera realmente los recursos? → A: **No con la acción de pausa.** En
  Proxmox, pausar/suspender un LXC congela los procesos pero mantiene la RAM reservada, y la
  hibernación real (volcado de memoria a disco) solo es confiable en VMs QEMU — en contenedores usa
  CRIU y está marcada como experimental. Para un LXC, **detenerlo** libera CPU y RAM al 100%,
  preserva el disco intacto y arranca de nuevo en segundos, por lo que es funcionalmente equivalente
  a hibernar. Se adopta esa mecánica; "Pausado" se conserva como el término de cara a la cátedra.
- Q: ¿"Eliminar la cuota" significa dejar de controlar la capacidad? → A: **No.** Se elimina el
  *techo por cátedra declarado por adelantado*; la *contabilidad de capacidad del clúster* se
  conserva y pasa a ejercerse en el momento de la aprobación. Son dos cosas distintas y la spec debe
  distinguirlas explícitamente.
- Q: ¿Alcanza con mostrarle al administrador la capacidad libre y que decida? → A: **No, por sí
  solo.** Consultar y decidir están separados en el tiempo del efecto real: si la aprobación no
  descuenta capacidad, el administrador puede aprobar tres pedidos seguidos viendo el mismo saldo
  libre y sobrecomprometer el clúster **sin cometer ningún error individual**. La aprobación MUST
  reservar capacidad de forma atómica, y la reserva MUST vencer si el despliegue nunca ocurre.
- Q: ¿Hay un mecanismo de recuperación de capacidad mejor que la detección de inactividad? → A:
  **Sí: el vencimiento por servicio.** La inactividad es un heurístico con falsos positivos (apagar
  algo en uso) y falsos negativos (un contenedor con una tarea periódica parece activo siempre). Una
  fecha de fin es determinista, predecible para la cátedra, pareja para todos, y su renovación
  reutiliza el mismo punto de control (la aprobación del administrador). Se adoptan **ambos**
  mecanismos: el vencimiento como piso garantizado, el pausado como recuperación oportunista.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Una sola cuenta para todas mis cátedras (Priority: P1)

Una docente que dicta tres materias distintas inicia sesión una vez y ve, en un mismo lugar, los
servicios y pedidos de sus tres cátedras. Puede concentrarse en una cátedra a la vez o verlas todas
juntas, y nunca necesita cerrar sesión y volver a entrar con otro usuario.

**Why this priority**: Es el corazón del pedido y el bloqueo actual más concreto — hoy una persona
con dos materias necesita dos cuentas, con dos contraseñas y dos 2FA. Todo lo demás de esta spec
(pedidos, aprobación, pausado) depende de poder decir "esta cátedra" dentro de una sesión.

**Independent Test**: Se crea una persona usuaria con dos cátedras a su nombre, se inicia sesión una
sola vez y se comprueba que ve los servicios y pedidos de ambas, correctamente atribuidos a cada
una, y que no ve nada de una tercera cátedra ajena.

**Acceptance Scenarios**:

1. **Given** una persona usuaria con dos cátedras a su nombre, **When** inicia sesión, **Then** ve
   sus dos cátedras identificadas por nombre y puede pasar de una a otra sin volver a autenticarse.
2. **Given** esa misma sesión, **When** consulta el listado de servicios, **Then** cada servicio
   aparece rotulado con la cátedra a la que pertenece, y no aparece ningún servicio de una cátedra
   que no sea suya.
3. **Given** una persona usuaria con una sola cátedra, **When** inicia sesión, **Then** la
   experiencia es equivalente a la actual: no se le exige elegir cátedra en cada paso ni se le
   muestra un selector innecesario.
4. **Given** una persona usuaria sin ninguna cátedra asignada, **When** inicia sesión, **Then** el
   sistema se lo informa en lenguaje claro e indica que debe pedirle a un administrador que le
   asigne o cree una, sin mostrar pantallas vacías ni errores técnicos.

---

### User Story 2 - Pedir un servicio sin toparse con una cuota (Priority: P1)

Una cátedra pide el servicio que necesita eligiendo qué quiere y para cuál de sus materias, y el
pedido queda registrado a la espera de la decisión del administrador. El sistema ya no le rechaza el
pedido por "cuota excedida": si el pedido es razonable o no lo dirá el administrador.

**Why this priority**: Es la contraparte inmediata de eliminar la cuota. Sin esto, el cambio de
modelo no produce ningún beneficio observable para quien lo pide.

**Independent Test**: Con una cátedra que hoy estaría por encima de cualquier cuota razonable, se
crea un pedido y se verifica que queda registrado en estado "solicitado" y visible para el
administrador, en lugar de ser rechazado automáticamente.

**Acceptance Scenarios**:

1. **Given** una persona usuaria con varias cátedras, **When** crea un pedido, **Then** debe indicar
   para cuál de **sus** cátedras es, y el pedido queda atribuido a esa cátedra.
2. **Given** una persona usuaria con una sola cátedra, **When** crea un pedido, **Then** la cátedra
   se asume sin pedírsela.
3. **Given** una cátedra que ya tiene muchos servicios desplegados, **When** crea un pedido nuevo,
   **Then** el pedido se registra normalmente y queda pendiente de aprobación; el sistema **no** lo
   rechaza por consumo acumulado.
4. **Given** una persona usuaria, **When** intenta crear un pedido a nombre de una cátedra que no
   le pertenece, **Then** el sistema lo rechaza por falta de permisos.

---

### User Story 3 - Aprobar es comprometer capacidad, no opinar (Priority: P1)

El administrador revisa la bandeja de pedidos pendientes. Para cada uno ve qué recursos consumirá,
cuánto tiene ya la cátedra solicitante, cuánta capacidad libre queda en el clúster y cómo quedaría
esa capacidad si aprueba. Al confirmar, el sistema **reserva** esos recursos en el acto: el
siguiente pedido que abra ya refleja el compromiso recién asumido.

**Why this priority**: Al quitar el techo por cátedra, la aprobación pasa a ser **el único** punto de
control de recursos del sistema. Y si aprobar no descuenta capacidad, el administrador puede aprobar
tres pedidos seguidos viendo el mismo saldo libre y sobrecomprometer el clúster sin cometer ningún
error individual — el sistema le habría mentido tres veces. La reserva es lo que hace que este
modelo sea seguro y no solo más simple.

**Independent Test**: Con varios pedidos pendientes y capacidad libre para solo uno de ellos, se
aprueba el primero y se verifica que al abrir el segundo la capacidad libre ya refleja el
compromiso, y que aprobarlo dispara la advertencia de sobrecompromiso.

**Acceptance Scenarios**:

1. **Given** un pedido pendiente, **When** el administrador lo abre, **Then** ve los recursos que
   consumirá, el consumo vigente de la cátedra solicitante, la capacidad libre del clúster y la
   capacidad que quedaría libre si lo aprueba.
2. **Given** capacidad libre para un solo pedido y dos pedidos pendientes equivalentes, **When** el
   administrador aprueba el primero y abre el segundo, **Then** la capacidad libre que ve ya
   descuenta el primero, aunque su servicio todavía no esté desplegado.
3. **Given** un pedido cuya aprobación dejaría al clúster sin capacidad suficiente, **When** el
   administrador intenta aprobarlo, **Then** el sistema se lo advierte de forma explícita y le exige
   una justificación antes de confirmar, sin impedirle la acción.
4. **Given** dos administradores revisando la misma bandeja, **When** uno aprueba un pedido y el otro
   intenta aprobar otro con números que ya quedaron desactualizados, **Then** el sistema no completa
   la segunda aprobación con datos viejos: recalcula la capacidad y le pide confirmar sobre los
   valores vigentes.
5. **Given** un pedido rechazado, **When** la cátedra solicitante consulta su estado, **Then** ve el
   motivo del rechazo escrito por el administrador.
6. **Given** un pedido aprobado cuyo despliegue nunca se concretó, **When** transcurre el plazo de
   vigencia de la reserva, **Then** la capacidad reservada vuelve a estar disponible y el sistema se
   lo informa al administrador.

---

### User Story 4 - Los servicios sin uso se pausan y liberan capacidad (Priority: P3)

Un servicio desplegado para un trabajo práctico que terminó hace semanas sigue consumiendo CPU y
memoria del clúster. El sistema detecta que nadie lo usa, avisa, y lo pausa liberando esa capacidad.
Cuando la cátedra lo vuelve a necesitar, lo reactiva por su cuenta.

**Why this priority**: Es la vía **oportunista** de recuperación de capacidad: recupera entre
vencimientos lo que nadie está usando. Va después del vencimiento (US6) porque aquélla es la vía
garantizada y ésta es un heurístico: acierta seguido, pero puede equivocarse en ambas direcciones
(apagar algo en uso, o no detectar un contenedor ocioso con una tarea periódica). Si hubiera que
elegir una sola de las dos, el vencimiento es la que sostiene el modelo.

**Independent Test**: Con un servicio sin actividad durante el umbral configurado, se comprueba que
el sistema lo marca como inactivo, notifica, y tras el período de gracia lo deja pausado; y que la
cátedra puede reactivarlo desde su pantalla sin intervención del administrador.

**Acceptance Scenarios**:

1. **Given** un servicio sin actividad durante el umbral definido, **When** vence el período de
   gracia posterior al aviso, **Then** el servicio queda pausado y su capacidad de cómputo y memoria
   vuelve a estar disponible para el clúster.
2. **Given** un servicio marcado como candidato a pausa, **When** la cátedra lo usa antes de que
   venza el período de gracia, **Then** el aviso se cancela y el servicio sigue activo.
3. **Given** un servicio pausado automáticamente, **When** la cátedra lo reactiva, **Then** vuelve a
   estar en ejecución con sus datos intactos, sin requerir un pedido nuevo ni la aprobación del
   administrador.
4. **Given** un servicio pausado automáticamente, **When** la cátedra intenta reactivarlo pero el
   clúster no tiene capacidad libre suficiente, **Then** el sistema se lo informa en lenguaje claro,
   deja el servicio pausado (no en error) y le indica cómo escalarlo al administrador.
5. **Given** un servicio que la cátedra declaró como "siempre encendido", **When** transcurre el
   umbral de inactividad, **Then** el sistema no lo pausa, pero sí lo lista al administrador como
   servicio inactivo exento.
6. **Given** una pausa automática ya ejecutada, **When** se consulta el historial de ese servicio,
   **Then** consta la acción, su motivo ("sin uso desde <fecha>") y que la ejecutó el sistema, no
   una persona.

---

### User Story 5 - El administrador gestiona las cátedras de cada persona (Priority: P2)

El administrador crea una cátedra nueva y se la asigna a una persona existente, reasigna una cátedra
cuando cambia el titular, y da de baja una cátedra que terminó su ciclo — sabiendo qué servicios
quedan en juego antes de hacerlo.

**Why this priority**: Sin esto, la relación "una persona, varias cátedras" no puede administrarse y
solo existiría por carga inicial de datos. No es P1 porque el escenario de arranque puede resolverse
con los datos migrados.

**Independent Test**: Se crea una cátedra, se asigna a una persona, se verifica que aparece en su
sesión; se reasigna a otra persona y se verifica que desaparece de la primera y aparece en la
segunda, con los servicios siguiendo a la cátedra.

**Acceptance Scenarios**:

1. **Given** el administrador, **When** crea una cátedra, **Then** debe indicar a qué persona
   usuaria queda a cargo, y esa persona la ve en su sesión sin necesidad de volver a autenticarse.
2. **Given** una cátedra con servicios desplegados, **When** el administrador la reasigna a otra
   persona, **Then** los servicios, pedidos e historial siguen perteneciendo a la cátedra, y la
   persona anterior deja de verlos.
3. **Given** una cátedra con servicios vigentes, **When** el administrador intenta darla de baja,
   **Then** el sistema le muestra cuántos servicios quedarían afectados y le exige confirmación
   explícita.
4. **Given** una persona usuaria a la que se desactiva la cuenta, **When** tenía cátedras a cargo,
   **Then** el sistema advierte que esas cátedras quedarían sin responsable y exige resolverlo
   (reasignar o dar de baja) antes de confirmar.

---

### User Story 6 - Cada servicio tiene fecha de fin, y renovarlo es pedirlo de nuevo (Priority: P2)

Cuando el administrador aprueba un pedido, el servicio nace con una fecha de vencimiento — por
defecto, el fin del cuatrimestre en curso. La cátedra la ve desde el primer día. Antes de que
venza, el sistema le avisa y ella puede pedir una renovación, que el administrador aprueba o
rechaza con la misma pantalla y los mismos números que usó la primera vez. Lo que vence y no se
renueva libera su capacidad.

**Why this priority**: Es la vía **garantizada** de recuperación de capacidad y la que evita que el
clúster solo acumule. A diferencia del pausado por inactividad, no depende de medir nada ni de que
las métricas estén sanas: es determinista y predecible. Además cierra el modelo con elegancia — el
mismo punto de control que otorga los recursos es el que los recupera.

**Independent Test**: Se aprueba un pedido, se verifica que el servicio resultante tiene fecha de
fin visible para la cátedra; se adelanta esa fecha y se comprueba que el sistema avisa antes de
vencer, que la cátedra puede solicitar renovación y que un vencimiento sin renovación libera la
capacidad.

**Acceptance Scenarios**:

1. **Given** un pedido aprobado, **When** su servicio queda desplegado, **Then** tiene una fecha de
   vencimiento visible para la cátedra desde el primer momento.
2. **Given** un servicio próximo a vencer, **When** falta el plazo de aviso definido, **Then** la
   cátedra recibe la notificación con tiempo suficiente para pedir la renovación.
3. **Given** un servicio próximo a vencer, **When** la cátedra solicita renovarlo, **Then** el
   pedido de renovación llega a la bandeja del administrador con la misma información de capacidad
   que un pedido nuevo.
4. **Given** una renovación aprobada, **When** se confirma, **Then** el servicio conserva sus datos y
   su identidad —no se recrea— y solo se corre su fecha de vencimiento.
5. **Given** un servicio vencido sin renovación solicitada, **When** llega la fecha, **Then** el
   sistema libera su capacidad de cómputo y memoria y se lo informa a la cátedra.
6. **Given** un servicio vencido, **When** la cátedra intenta acceder a él, **Then** el sistema le
   explica que venció y le ofrece solicitar su reactivación, sin haber destruido sus datos.
7. **Given** una renovación rechazada, **When** la cátedra consulta el estado, **Then** ve el motivo
   escrito por el administrador y la fecha en la que el servicio dejará de estar disponible.

---

### Edge Cases

- **Persona sin cátedras**: no puede crear pedidos; el sistema se lo dice en lenguaje claro en lugar
  de mostrar un formulario que fallará al enviarse.
- **Administrador con cátedras propias**: un administrador puede además ser titular de cátedras. Sus
  privilegios de administración no se mezclan con su rol de cátedra: sigue viendo todo como
  administrador, y sus propias cátedras aparecen identificadas como tales.
- **Cátedras homónimas de distintos titulares**: dos personas pueden dictar materias con el mismo
  nombre; el sistema debe poder distinguirlas y mostrarlas sin ambigüedad.
- **Aprobación tardía**: entre que un pedido se aprueba y el servicio se despliega, el clúster puede
  quedarse sin capacidad. El despliegue debe fallar de forma limpia, con motivo registrado y
  posibilidad de reintento, sin dejar recursos huérfanos.
- **Aprobación abandonada**: un pedido aprobado que nunca se despliega retendría capacidad
  indefinidamente. Es una fuga silenciosa equivalente a la de los recursos huérfanos: la reserva
  tiene que vencer sola.
- **Dos administradores aprobando a la vez**: ambos pueden estar mirando el mismo saldo libre. La
  segunda aprobación no debe completarse sobre números que ya quedaron viejos.
- **Aprobación con la pantalla abierta mucho tiempo**: el administrador puede dejar la bandeja
  abierta una hora y confirmar después. Vale lo mismo: los números se recalculan al confirmar.
- **Vencimiento en medio del cuatrimestre**: una fecha por defecto mal elegida puede apagar un
  servicio en plena cursada. El aviso previo y la renovación existen para eso, pero la fecha por
  defecto debe ser conservadora.
- **Renovación pedida y no resuelta**: si la renovación llega pero el administrador no la resuelve
  antes del vencimiento, apagar el servicio castiga a la cátedra por una demora ajena. El sistema
  debe contemplar ese caso en lugar de aplicar la fecha a ciegas.
- **Vencimiento y pausado simultáneos**: un servicio pausado por inactividad también puede vencer.
  Los dos mecanismos no deben pisarse ni contar la misma capacidad dos veces.
- **Reactivación imposible**: reactivar un servicio pausado puede fallar por falta de capacidad. El
  servicio debe quedar pausado (estado definido), nunca en un estado ambiguo.
- **Servicio pausado que ya no se necesita**: un servicio puede quedar pausado indefinidamente
  ocupando disco. El disco **no** se libera al pausar; el administrador necesita ver el conjunto de
  servicios pausados hace mucho tiempo para decidir darlos de baja.
- **Pausa durante una operación en curso**: el pausado automático no debe dispararse sobre un
  servicio que está en medio de un despliegue, reinicio u otra operación del portal.
- **Servicio inactivo pero necesario**: un servidor web sin tráfico durante la ventana de medición
  puede ser exactamente el servicio que debe seguir encendido. Por eso existe la marca "siempre
  encendido" y el aviso previo.
- **Métricas ausentes**: si no hay datos de actividad de un servicio (por ejemplo, la recolección
  estuvo caída), el sistema **no** debe interpretar el silencio como inactividad.
- **Servicios preexistentes a la migración**: al aplicar el cambio, los servicios existentes no
  deben quedar todos marcados como inactivos por falta de historial de métricas.
- **Cátedra con varios docentes hoy**: con titular único, una cátedra que actualmente tiene dos
  personas asignadas conserva solo una. La migración debe dejar constancia de quién pierde acceso
  para que el administrador lo resuelva, en lugar de que la persona lo descubra al no poder entrar.
- **Servicio con procesos levantados a mano**: al reactivar un servicio pausado, solo vuelven a
  arrancar los procesos configurados para iniciarse solos. La cátedra debe estar advertida de esto
  antes de la pausa, no después.
- **Buscador con mucha cantidad de cátedras**: si el portal opera 200 cátedras, el buscador de
  cátedras debe poder filtrarlas eficientemente; buscar "Prog" no debe hacer que se pegue la UI
  (búsqueda client-side tolerada, server-side preferido).
- **Cátedra desaparece entre búsqueda y confirmación**: el admin busca, marca "Prog1", se va a
  tomar café y después confirma. Si "Prog1" fue dada de baja en el medio, la operación atomicidad
  (FR-036) la rechaza. El admin ve un error: "Una de las cátedras seleccionadas ya no está disponible,
  por favor busque de nuevo".
- **Dos administradores crean usuarios con la misma cátedra a la vez**: la segunda alta falla
  atomicamente si intentaba asignar una cátedra que ya quedó titular de otro usuario en el medio.
- **Admin selecciona todas las cátedras disponibles**: esto es válido. El sistema no debe tener un
  techo arbitrario de "máximo N cátedras por usuario".
- **Búsqueda que retorna cero resultados**: el sistema debe decirle al admin *por qué* no encuentra
  nada (filtro muy restrictivo, o realmente no hay cátedras sin titular). No dejar una lista vacía
  confusa.

## Requirements *(mandatory)*

### Functional Requirements

**Identidad y pertenencia**

- **FR-001**: El sistema MUST permitir que una persona usuaria tenga cero, una o varias cátedras a
  su cargo, operables dentro de una única sesión autenticada.
- **FR-001b**: Cada cátedra MUST tener exactamente una persona responsable. El sistema MUST NOT
  permitir que dos personas usuarias tengan acceso simultáneo a la misma cátedra por titularidad.
- **FR-002**: El sistema MUST identificar cada cátedra por su nombre y por la persona responsable,
  de modo que dos cátedras homónimas de titulares distintos sean distinguibles en toda pantalla y
  listado.
- **FR-003**: El sistema MUST mostrar a cada persona usuaria únicamente los pedidos, servicios y
  métricas de las cátedras que le pertenecen; el rol administrador MUST seguir viendo la totalidad.
- **FR-004**: Cuando una persona usuaria tiene más de una cátedra, el sistema MUST permitirle
  cambiar el foco entre ellas y MUST rotular cada pedido y servicio con la cátedra a la que
  pertenece.
- **FR-005**: Cuando una persona usuaria tiene exactamente una cátedra, el sistema MUST NOT exigirle
  seleccionarla en ninguna operación.
- **FR-006**: El sistema MUST conservar la cátedra como unidad de atribución histórica: los
  servicios, pedidos e historial pertenecen a la cátedra y MUST sobrevivir a un cambio de titular.
- **FR-007**: El sistema MUST permitir al administrador crear una cátedra, asignarla o reasignarla a
  una persona usuaria, y darla de baja.
- **FR-008**: El sistema MUST impedir que una cátedra con servicios vigentes quede sin persona
  responsable; ante la desactivación de una cuenta con cátedras a cargo, MUST exigir su reasignación
  o baja antes de confirmar.

**Eliminación de la cuota**

- **FR-009**: El sistema MUST NOT rechazar la creación de un pedido por consumo acumulado de la
  cátedra solicitante.
- **FR-010**: El sistema MUST NOT exigir ni exponer un techo de vCPU, RAM o disco declarado por
  cátedra en ninguna pantalla ni operación.
- **FR-011**: El sistema MUST seguir mostrando a la cátedra el consumo vigente de sus servicios en
  términos comprensibles (qué tiene desplegado y cuánto ocupa), ahora sin referencia a un límite
  asignado.
- **FR-012**: El sistema MUST conservar la capacidad de reconstruir el consumo histórico por cátedra,
  incluyendo el de servicios ya dados de baja.
- **FR-013**: El sistema MUST mantener el tope de disco por contenedor vigente (8 GB salvo
  justificación explícita registrada), que es un límite por recurso y no una cuota por cátedra.

**Aprobación como punto de control**

- **FR-014**: Al revisar un pedido pendiente, el sistema MUST mostrar al administrador: los recursos
  que el pedido consumirá, el consumo vigente de la cátedra solicitante, la capacidad libre del
  clúster y la capacidad que quedaría libre si aprueba.
- **FR-014b**: El cálculo de capacidad comprometida MUST incluir, además de los servicios en
  ejecución, **los pedidos ya aprobados cuyo servicio todavía no fue desplegado**, y el
  almacenamiento de los servicios pausados. La capacidad libre MUST recalcularse en el momento de
  mostrarse; el sistema MUST NOT presentar un valor cacheado.
- **FR-014c**: El sistema MUST mostrar al administrador la memoria en riesgo de reactivación — lo
  que demandarían todos los servicios pausados si volvieran a encenderse a la vez — para que pueda
  anticipar las reactivaciones que fallarían.
- **FR-015**: El sistema MUST advertir explícitamente al administrador cuando aprobar un pedido
  dejaría comprometida más capacidad de la que el clúster tiene disponible, y MUST permitirle
  aprobarlo de todos modos. El sistema MUST NOT bloquear la aprobación.
- **FR-015b**: Cuando el administrador aprueba un pedido pese a la advertencia de capacidad, el
  sistema MUST exigirle una justificación y MUST registrarla junto con la aprobación, de modo que
  todo sobrecompromiso del clúster sea rastreable a quién lo decidió y por qué.
- **FR-016**: El sistema MUST registrar quién aprobó o rechazó cada pedido, cuándo y con qué motivo,
  y MUST mostrarle el motivo del rechazo a la cátedra solicitante.
- **FR-017**: El sistema MUST reflejar todo pedido nuevo en la bandeja del administrador sin acción
  manual de sincronización.
- **FR-018**: Cuando un despliegue aprobado falle por falta de capacidad real, el sistema MUST dejar
  el pedido en un estado explícito con el motivo registrado y MUST permitir reintentarlo sin
  duplicar recursos.

**Reserva de capacidad**

- **FR-018b**: La aprobación de un pedido MUST reservar la capacidad correspondiente en el momento
  de aprobarse, aunque el servicio todavía no exista. Esa reserva MUST contar como capacidad
  comprometida para toda decisión posterior.
- **FR-018c**: La verificación de capacidad y la creación de la reserva MUST ocurrir como una
  operación única e indivisible. Si la capacidad disponible cambió entre el momento en que se le
  mostraron los números al administrador y el momento en que confirma, el sistema MUST NOT completar
  la aprobación con los valores viejos: MUST recalcular y pedir una confirmación nueva.
- **FR-018d**: La reserva MUST tener un plazo de vigencia. Si el despliegue no se concreta dentro de
  ese plazo, el sistema MUST liberar la capacidad reservada y MUST notificárselo al administrador.
- **FR-018e**: Un despliegue exitoso MUST convertir la reserva en consumo real sin contabilizarla
  dos veces; un despliegue fallido de forma definitiva MUST liberarla.

**Vencimiento y renovación**

- **FR-018f**: Todo servicio desplegado MUST tener una fecha de vencimiento, definida al aprobarse
  el pedido, con un valor por defecto propuesto por el sistema y ajustable por el administrador.
- **FR-018g**: El sistema MUST mostrarle a la cátedra la fecha de vencimiento de cada uno de sus
  servicios desde el momento en que quedan disponibles.
- **FR-018h**: El sistema MUST avisar a la cátedra responsable antes del vencimiento, con
  antelación suficiente para solicitar una renovación.
- **FR-018i**: La cátedra MUST poder solicitar la renovación de un servicio, y esa solicitud MUST
  atravesar el mismo circuito de aprobación —y mostrarle al administrador la misma información de
  capacidad— que un pedido nuevo.
- **FR-018j**: Una renovación aprobada MUST conservar el servicio, sus datos y su identidad,
  limitándose a extender su fecha de vencimiento. El sistema MUST NOT recrear el servicio.
- **FR-018k**: Al vencer un servicio sin renovación aprobada, el sistema MUST liberar su capacidad
  de cómputo y memoria e informárselo a la cátedra, MUST NOT destruir sus datos de forma automática,
  y MUST permitirle a la cátedra solicitar su reactivación.
- **FR-018l**: El sistema MUST registrar el vencimiento en el historial del servicio, con el sistema
  identificado como autor de la acción.
- **FR-018m**: Si al llegar la fecha de vencimiento existe una solicitud de renovación pendiente de
  resolución, el sistema MUST NOT apagar el servicio por vencimiento; MUST mantenerlo disponible y
  MUST señalarle al administrador que la demora está afectando a un servicio en uso.
- **FR-018n**: El vencimiento y el pausado por inactividad MUST poder aplicarse al mismo servicio
  sin contabilizar dos veces la misma capacidad liberada.

**Pausado por inactividad**

- **FR-019**: El sistema MUST detectar los servicios sin uso a partir de su actividad observada
  durante una ventana de tiempo configurable, y MUST ejecutar la pausa por su cuenta al vencer el
  período de gracia, sin requerir la confirmación de ninguna persona.
- **FR-020**: El sistema MUST avisar a la cátedra responsable antes de pausar un servicio por
  inactividad, y MUST dejar transcurrir un período de gracia entre el aviso y la pausa.
- **FR-021**: Si el servicio registra actividad durante el período de gracia, el sistema MUST
  cancelar la pausa programada.
- **FR-022**: La pausa por inactividad MUST liberar efectivamente la capacidad de cómputo y memoria
  que el servicio ocupaba en el clúster. El sistema MUST NOT presentar como "liberación de recursos"
  una acción que en los hechos mantenga la memoria reservada.
- **FR-023**: El sistema MUST preservar íntegro el contenido del servicio pausado: reactivarlo MUST
  devolverlo a un estado utilizable con sus datos.
- **FR-023b**: El sistema MUST advertir a la cátedra, en el aviso previo a la pausa, que el estado
  en memoria no se conserva: los procesos que estén corriendo volverán a arrancar al reactivar el
  servicio. Los datos en disco no se ven afectados.
- **FR-024**: La cátedra MUST poder reactivar por sí misma un servicio pausado por inactividad, sin
  crear un pedido nuevo ni requerir aprobación del administrador.
- **FR-025**: Si una reactivación no puede completarse por falta de capacidad, el sistema MUST dejar
  el servicio en estado pausado con el motivo registrado y MUST informarlo en lenguaje comprensible.
- **FR-026**: El sistema MUST permitir marcar un servicio como exento del pausado automático
  ("siempre encendido"), y MUST listarle al administrador los servicios exentos que están inactivos.
- **FR-027**: El sistema MUST NOT pausar un servicio sobre el que hay una operación del portal en
  curso.
- **FR-028**: Ante ausencia de datos de actividad, el sistema MUST abstenerse de pausar; la falta de
  medición MUST NOT interpretarse como inactividad.
- **FR-029**: Toda pausa y reactivación automática MUST quedar registrada en el historial del
  servicio con su motivo y con el sistema identificado como autor de la acción.
- **FR-030**: El sistema MUST ofrecer al administrador la lista de servicios pausados, con la fecha
  desde la que lo están, para decidir su baja definitiva.
- **FR-031**: El sistema MUST informar, al presentar un servicio pausado, que el almacenamiento sigue
  ocupado aunque el cómputo esté liberado.

**Migración y continuidad**

- **FR-032**: Al aplicarse el cambio, cada persona usuaria MUST conservar el acceso a la cátedra que
  tenía asignada, y cada cátedra MUST conservar sus servicios, pedidos e historial.
- **FR-033**: Los servicios existentes al momento del cambio MUST NOT ser considerados inactivos por
  la mera falta de historial previo de actividad.
- **FR-034**: Para toda cátedra que al momento del cambio tenga más de una persona usuaria asignada,
  la migración MUST designar una única titular y MUST dejar registrado qué personas perdieron el
  acceso, para que el administrador pueda resolverlo (crear una cátedra propia para cada una, o
  reasignar).

**Alta de usuario con cátedras**

- **FR-035**: El administrador MUST poder crear una persona usuaria y asignarle una o varias
  cátedras en una única operación de alta, sin requerir pasos posteriores de reasignación.
- **FR-035b**: Al crear un usuario, el administrador MUST contar con un buscador de cátedras que:
  - Permita filtrar por nombre (búsqueda substring, insensible a mayúsculas)
  - Muestre cada cátedra con su nombre y titular actual en lenguaje claro
  - Permita marcar/desmarcar cátedras con checkboxes claros
  - Indique visualmente cuáles están seleccionadas (sin desordenar la lista)
  - No requiera scroll excesivo ni ocupe más de un tercio de la pantalla si hay pocas cátedras
- **FR-035c**: El buscador MUST filtrar cátedras que ya están asignadas a otro usuario (no
  disponibles para reasignación en la misma operación). El sistema MUST mostrar cuáles están
  ocupadas para que el admin entienda por qué no puede seleccionarlas.
- **FR-036**: El sistema MUST validar que la creación del usuario y la asignación de cátedras
  ocurran como una operación atómica: si una cátedra deja de estar disponible entre que el admin la
  selecciona y confirma, el sistema MUST rechazar la operación de alta completa (no dejar al usuario
  creado sin todas sus cátedras).
- **FR-036b**: El sistema MUST exigir que al menos una cátedra esté seleccionada para crear el
  usuario. Crear un usuario sin cátedras no tiene sentido en este modelo (no podría crear pedidos).
- **FR-036c**: Después de confirmar la alta, el sistema MUST mostrar al administrador un resumen de
  quién se creó y a qué cátedras quedó asignado, de modo que pueda verificar antes de cerrar.

### Key Entities

- **Persona usuaria**: quien inicia sesión. Tiene credenciales propias, un rol (administrador o
  cátedra) y cero o más cátedras a cargo. Ya no está atada a una única cátedra.
- **Cátedra**: la materia o espacio académico. Es la unidad de aislamiento y de atribución histórica:
  agrupa pedidos, servicios y consumo. Tiene una persona responsable, que puede cambiar sin que la
  cátedra pierda su historia. **Ya no tiene cuota de recursos.**
- **Pedido**: la solicitud de un servicio, hecha por una persona usuaria a nombre de una de sus
  cátedras. Su aprobación por el administrador es el único punto de control de recursos del sistema.
  Un pedido puede ser de alta o de renovación de un servicio existente.
- **Reserva de capacidad**: el compromiso de recursos que nace al aprobar un pedido y muere al
  desplegarse el servicio, al fallar definitivamente el despliegue o al vencer su plazo. Existe para
  que dos aprobaciones consecutivas no puedan comprometer la misma capacidad dos veces.
- **Servicio**: el recurso desplegado, perteneciente a una cátedra. Suma tres atributos nuevos: su
  fecha de vencimiento, si está exento del pausado automático, y desde cuándo está pausado por
  inactividad.
- **Registro de inactividad**: la evidencia que respalda una pausa automática — qué ventana se
  observó, qué actividad se detectó, cuándo se avisó y cuándo se ejecutó la pausa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona que dicta varias materias accede a todas sus cátedras con un único inicio
  de sesión; el número de cuentas necesarias por persona pasa de una por cátedra a exactamente una.
- **SC-002**: Ningún pedido es rechazado automáticamente por consumo acumulado de la cátedra: el
  100% de los pedidos bien formados llega a la bandeja del administrador.
- **SC-003**: El administrador puede decidir sobre un pedido pendiente sin consultar ninguna
  herramienta externa al portal: la información de capacidad necesaria está en la misma pantalla.
- **SC-004**: Al menos el 90% de los servicios sin actividad durante la ventana definida quedan
  pausados y su capacidad de cómputo y memoria vuelve a estar disponible.
- **SC-004b**: Ninguna secuencia de aprobaciones consecutivas puede comprometer más capacidad de la
  disponible sin que el administrador haya visto la advertencia y dejado una justificación: cero
  sobrecompromisos accidentales.
- **SC-004c**: Ninguna aprobación que nunca llega a desplegarse retiene capacidad más allá del plazo
  de reserva definido.
- **SC-004d**: El 100% de los servicios desplegados tiene una fecha de vencimiento conocida por su
  cátedra, y ningún servicio se apaga por vencimiento sin aviso previo ni con una renovación
  pendiente de resolver.
- **SC-005**: Ningún servicio activamente usado es pausado por error durante un ciclo lectivo
  completo (cero falsos positivos observados).
- **SC-006**: Una cátedra reactiva por sí sola un servicio pausado en menos de 2 minutos y sin
  intervención de un administrador.
- **SC-007**: Tras la migración, ninguna cátedra pierde servicios, pedidos ni historial, y toda
  persona usuaria conserva el acceso que tenía.
- **SC-008**: El tiempo de alta de una persona que dicta N materias baja de N altas de cuenta a una
  sola alta más N asignaciones de cátedra.

## Assumptions

- **Ámbito del "unificar"**: se interpreta como unificar la **cuenta de acceso** (una persona, una
  sesión, varias cátedras), no como fusionar cátedra y persona en un único registro. La cátedra
  sigue existiendo como entidad propia porque es la unidad de atribución histórica exigida por el
  Principio V de la constitución: si desapareciera, el consumo histórico dejaría de ser
  reconstruible cuando cambia el titular de la materia.
- **Detección de inactividad**: se apoya en las métricas de actividad que el sistema ya recolecta por
  servicio (uso de CPU, memoria y tráfico de red). Umbral por defecto propuesto: sin actividad
  significativa durante 7 días corridos, con aviso 48 horas antes de la pausa. Ambos valores son
  configurables por el administrador.
- **Alcance del pausado**: la liberación alcanza a cómputo y memoria, mediante la detención del
  contenedor (ver Clarifications y el riesgo 1). El almacenamiento **no** se libera al pausar;
  recuperarlo requiere dar de baja el servicio, que sigue siendo una decisión humana. El estado en
  memoria tampoco se conserva: los procesos vuelven a arrancar al reactivar.
- **Rol administrador**: se mantiene tal como está hoy — ve y opera sobre todo el sistema, y es el
  único que aprueba, rechaza y gestiona el ciclo de vida de los pedidos.
- **Autenticación**: sin cambios. Sigue siendo propia del portal (usuario + contraseña + 2FA); esta
  feature no toca el mecanismo de login, solo qué cátedras alcanza la sesión resultante.
- **Capacidad del clúster**: el sistema ya puede consultar la capacidad real de los nodos; esta
  feature la reutiliza para informar la decisión de aprobación, en lugar de para validar cuotas.
- **Notificaciones**: el aviso previo a la pausa se entrega dentro del portal. El envío por correo
  electrónico queda fuera de alcance de esta feature.
- **Vencimiento por defecto**: se propone el fin del cuatrimestre en curso como fecha por defecto,
  ajustable por el administrador al aprobar. El aviso previo por defecto es de 7 días.
- **Plazo de la reserva**: se propone 24 horas entre la aprobación y el despliegue; vencido ese
  plazo la reserva se libera. El valor es configurable por el administrador.
- **Margen de reserva del clúster**: se asume que el administrador querrá conservar un colchón de
  capacidad libre en lugar de operar al 100%; el valor concreto se define en la fase de plan.
- **Datos de un servicio vencido**: se conservan hasta que el administrador decida darlo de baja. La
  liberación de almacenamiento sigue siendo una decisión humana, igual que en el pausado.

## Riesgos e inconsistencias detectadas

Análisis pedido explícitamente en la descripción de la feature. Cada punto está cubierto por algún
requisito o supuesto de arriba; se listan aquí para que la decisión de avanzar sea informada.

### 1. "Pausar para liberar recursos" no libera lo que parece — resuelto

Hay tres acciones distintas que suelen confundirse bajo la palabra "pausar":

| Acción | Qué hace con la memoria | Aplicable a contenedores |
|---|---|---|
| Pausar / suspender (congelar) | La mantiene **reservada** | Sí, pero no sirve para liberar capacidad |
| Hibernar (volcar la memoria a disco) | La **libera** | Solo confiable en máquinas virtuales |
| Detener | La libera al 100%, junto con la CPU | Sí, y es lo que el sistema ya sabe hacer |

Los servicios del portal son contenedores. Para ellos, la hibernación real depende de un mecanismo
de checkpoint que la plataforma marca como experimental y que falla ante conexiones abiertas, así
que no es una base confiable para el mecanismo principal de recuperación de capacidad.

Detener un contenedor, en cambio, es funcionalmente equivalente a hibernarlo: el disco es
persistente (los datos quedan intactos), libera toda la CPU y la memoria, y el arranque posterior
demora segundos. **Esa es la mecánica adoptada.** Lo único que se pierde frente a una hibernación
real es el estado en memoria — los procesos vuelven a arrancar —, lo que FR-023b exige advertir en el
aviso previo. "Pausado" se conserva como el término de cara a la cátedra, porque describe
correctamente lo que ella percibe. FR-022 exige que la acción libere de verdad cómputo y memoria, y
FR-031 que se aclare que el disco sigue ocupado.

### 2. Consultar y decidir están separados del efecto real — resuelto con reserva

Es el riesgo más serio de todo el modelo, y el que motivó agregar la reserva de capacidad.

Si aprobar no descuenta capacidad, la información que ve el administrador queda desactualizada
apenas aprueba algo. Clúster de 64 GB con 48 comprometidos, tres pedidos de 8 GB pendientes:

| Paso | El administrador ve | Decide | Estado real |
|---|---|---|---|
| Pedido A | 16 GB libres | Aprueba ✅ | Nada desplegado aún |
| Pedido B | **16 GB libres** | Aprueba ✅ | Nada desplegado aún |
| Pedido C | **16 GB libres** | Aprueba ✅ | Nada desplegado aún |

Comprometió 24 GB contra 16 disponibles y **cada decisión individual fue correcta**. El
administrador no se equivocó: el sistema le mostró tres veces un número que ya no era cierto. Esto
no se corrige con más información en pantalla ni con capacitación — se corrige haciendo que la
aprobación descuente (FR-018b) y que el descuento sea indivisible respecto de la verificación
(FR-018c), que además cubre el caso de dos administradores trabajando en paralelo.

El corolario es que la reserva debe poder morir sola: un pedido aprobado que nunca se despliega
retendría capacidad para siempre, que es exactamente la clase de fuga silenciosa que el Principio
III ya prohíbe para los recursos huérfanos. De ahí FR-018d.

### 3. Sin techo por cátedra, el administrador es el único freno — y puede quedar sin información

Hoy la cuota rechaza automáticamente lo que excede el techo. Al quitarla, si la pantalla de
aprobación no muestra la capacidad real, el administrador aprueba a ciegas y el sistema pasa de
"denegaciones injustas" a "sobrecompromiso silencioso del clúster". FR-014 y FR-015 existen
exactamente para eso: el control se traslada, no desaparece.

### 4. Sin techo, tampoco hay freno a la cantidad de pedidos

Nada impide que una cátedra cargue veinte pedidos y convierta al administrador en el cuello de
botella. Es un costo aceptado del modelo (es más simple, y la decisión humana es el punto), pero
conviene tenerlo presente: la carga de trabajo del administrador crece con la adopción, y ahora
crece por dos vías, porque las renovaciones también pasan por su bandeja.

Dos mitigaciones naturales si el problema aparece, ninguna incluida en esta feature: un límite de
pedidos pendientes simultáneos por cátedra, y la aprobación por lote al inicio del cuatrimestre —
que además es una decisión mejor informada que resolver de a un pedido por vez. Se dejan afuera para
no reintroducir techos por la puerta de atrás antes de tener evidencia de que hacen falta.

### 5. Una pausa automática no tiene autor humano

El historial de cambios del sistema exige hoy un autor por cada transición registrada. Una pausa
ejecutada por el sistema no tiene persona detrás. Si no se contempla, o bien la pausa automática no
puede registrarse en el historial (violando el Principio II), o bien se le atribuye falsamente a
alguna persona. FR-029 exige que el sistema quede identificado como autor propio de la acción.

### 6. El silencio no es lo mismo que la inactividad

Si la recolección de métricas se interrumpe, la ausencia de datos parece inactividad total y el
sistema pausaría servicios en pleno uso. Es el peor error posible de esta feature — más caro que no
pausar nada. FR-028 lo prohíbe explícitamente, y FR-033 evita el mismo efecto sobre los servicios
que ya existían antes del cambio.

### 7. Baja actividad no es lo mismo que "no se usa"

Un servidor web sin tráfico durante la ventana de medición puede ser precisamente el servicio que
debe seguir encendido. El aviso previo con período de gracia (FR-020/FR-021) y la marca "siempre
encendido" (FR-026) son las dos defensas; la segunda tiene el riesgo espejo de que todo el mundo la
marque, y por eso FR-026 exige exponerle al administrador los exentos inactivos.

### 8. Reactivar puede fallar

Si el clúster se llenó mientras el servicio estaba pausado, la reactivación no puede completarse. El
riesgo real es dejar el servicio en un estado ambiguo. FR-025 exige que quede pausado con motivo
registrado, coherente con el Principio III.

### 9. Cambiar de titular no debe borrar la historia

Si la cátedra dejara de ser una entidad propia y sus recursos colgaran de la persona, reasignar una
materia rompería la trazabilidad del consumo histórico — justo lo que el Principio V protege. FR-006
mantiene la cátedra como dueña de sus recursos y su historia; la unificación ocurre en la cuenta de
acceso, no en los datos.

### 10. La cátedra deja de ser el filtro implícito

Todo el aislamiento multi-inquilino actual descansa en "el usuario tiene una cátedra". Al pasar a
varias, cada listado y cada verificación de permiso cambia de "es mi cátedra" a "está entre mis
cátedras". Es un cambio mecánico pero de superficie amplia: cualquier punto que se omita se convierte
en una fuga de datos entre cátedras. FR-003 lo cubre como requisito transversal y merece verificación
exhaustiva en la fase de plan.

### 11. Nombres de cátedra repetidos

Hoy el nombre de cátedra es único en todo el sistema. Con varias personas dictando materias
homónimas ("Programación I" en dos comisiones), esa unicidad global deja de ser razonable, pero
relajarla sin más produce listados ambiguos. FR-002 exige que la cátedra sea distinguible por nombre
**y** responsable.

### 12. Un administrador también puede ser titular

Nada impide que quien administra el portal dicte una materia. El sistema debe poder representarlo sin
que sus privilegios de administración se confundan con lo que ve como cátedra.

### 13. El titular único deja fuera a las cátedras con varios docentes

Es la contracara de la decisión tomada (titular único). Hoy el modelo admite varias personas por
cátedra; al pasar a titular único, una cátedra con un titular y un JTP deja de poder representarse:
solo una de las dos personas conserva el acceso. Dos consecuencias concretas:

- **En la migración**: hay que elegir titular y avisar quién queda afuera (FR-034). No es un cambio
  silencioso: alguien pierde acceso a recursos que venía usando.
- **En el uso diario**: la única forma de que dos docentes trabajen sobre la misma materia es que
  cada uno tenga su propia cátedra, con servicios separados. Es una simplificación deliberada, no un
  descuido; si más adelante aparece la necesidad real de cátedras compartidas, el modelo de
  titular + colaboradores es la extensión natural y no invalida nada de lo definido acá.

## Impacto sobre la constitución

> [!NOTE]
> **Resuelto el 2026-08-16**: la constitución fue enmendada a **v2.0.0** y esta feature ya se
> evalúa contra los principios vigentes. La tabla de abajo documenta qué cambió y por qué.

Esta feature no podía implementarse bajo la constitución v1.1.0. Requirió una enmienda **MAJOR** —
se redefinió un principio de forma incompatible con lo anterior.

| Principio | Estado | Detalle |
|---|---|---|
| I. Proxmox es el back-end | ✅ Sin conflicto | La feature no expone Proxmox a nadie. |
| II. La máquina de estados es la única fuente de verdad | ⚠️ Requiere ampliación | Aparece un actor no humano (el sistema) ejecutando transiciones. El principio exige autor por transición; debe admitir explícitamente al sistema como autor. |
| III. Toda operación debe ser recuperable | ✅ Sin conflicto | Reforzado por FR-018, FR-018d y FR-025. La expiración de la reserva extiende el principio de "no dejar recursos huérfanos" a la capacidad comprometida pero no usada. |
| IV. Aislamiento y cuota por cátedra | ❌ **Conflicto directo** | Exige validar cuota antes de aprovisionar. Lo que cae es el **techo por cátedra**; el **aislamiento** se conserva íntegro y la **validación de capacidad antes de aprovisionar** también — solo que ahora ocurre contra la capacidad real del clúster, en el momento de la aprobación, y con reserva (FR-018b/c). El principio debe reescribirse como "Aislamiento por cátedra, control por aprobación con reserva". |
| V. El historial académico no se destruye | ✅ Sin conflicto | Preservado por FR-006 y FR-012; es además el argumento para no fusionar cátedra y persona. |
| VI. La cátedra pide y observa | ⚠️ Requiere ajuste de redacción | Describe la vista de cátedra como "consumo respecto de su cuota". Debe pasar a "consumo vigente de sus servicios". El espíritu del principio se mantiene. |

Vale notar que la enmienda al Principio IV es **menos drástica** de lo que parecía en la primera
redacción de esta spec: el principio exige "validar la cuota antes de aprovisionar, nunca después",
y ese requisito **se cumple** — se valida capacidad antes, y ahora además se reserva. Lo que se
elimina es el techo declarado por cátedra, no la validación previa.

**Enmienda aplicada (v2.0.0, 2026-08-16)**: el Principio IV pasó a "Aislamiento por cátedra; la
capacidad se controla al aprobar"; el II admite ahora al sistema como autor de una transición; el VI
habla de "consumo vigente de sus servicios" y suma el deber de avisar antes de toda acción
automática que afecte la disponibilidad. Se corrigieron además dos secciones que habían quedado
desalineadas: la cláusula de seguridad sobre operaciones mutantes (que ya contradecía a la feature
003) y la compuerta de pruebas, que ahora nombra "control de capacidad" en lugar de "cuotas" y exige
un escenario de concurrencia.

**Siguiente paso**: `/speckit-plan`.
