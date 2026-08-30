# Feature Specification: Retirar y corregir usuarios, cátedras y plantillas

**Feature Branch**: `006-ciclo-vida-entidades`

**Created**: 2026-08-30

**Status**: Draft

**Input**: Tres defectos encontrados durante la validación T091 de la feature 004 (2026-08-29/30), que
comparten una misma causa de fondo: el portal sabe **crear** entidades administrativas —personas,
cátedras, plantillas— pero no sabe **retirarlas ni corregirlas**. (1) Borrar una persona que alguna
vez creó un pedido devuelve un error 500 sin explicación. (2) El mensaje que impide desactivar a
quien tiene cátedras a cargo aconseja una salida que no funciona. (3) Las plantillas de servicio no
se pueden editar ni dar de baja después de creadas, de modo que una plantilla mal cargada queda
inservible para siempre y visible en el catálogo.

## Resumen del problema

El portal fue creciendo alrededor del camino feliz: dar de alta personas, cátedras y plantillas, y
operar sobre ellas. Lo que no tiene resuelto es el otro extremo del ciclo de vida: **qué pasa cuando
algo hay que retirarlo o corregirlo**.

Los tres defectos se descubrieron por separado, pero son la misma historia:

| Situación real | Lo que hace el portal hoy |
|---|---|
| Un docente deja la facultad y pidió servicios alguna vez | Error **500** sin explicación |
| Hay que desactivar a alguien que es titular de una cátedra | Bloquea con un consejo que **no destraba** |
| Una plantilla se cargó apuntando a una imagen equivocada | **No se puede corregir ni ocultar**, nunca |

Ninguno es catastrófico por separado. Juntos describen un portal que obliga a resolver por fuera
—tocando la base a mano— cosas que son operación normal de un cuatrimestre. Y tocar la base a mano
es justamente lo que la constitución prohíbe.

### Los tres, en detalle

**1. Borrar una persona con historial devuelve 500.** El borrado es físico, y la relación con sus
pedidos no declara qué hacer con ellos, así que el sistema intenta dejar los pedidos sin solicitante
y la base lo rechaza. Además de ser un error opaco, el borrado físico contradice el Principio V: la
autoría de un pedido es parte del historial académico y no debería poder destruirse. El caso normal
—un docente que se va— es exactamente el que falla; borrar a alguien que nunca pidió nada sí
funciona, lo que hace el defecto todavía más confuso.

**2. Un mensaje que aconseja algo que no funciona.** Al intentar desactivar a un titular, el portal
responde: *"Esta persona tiene cátedras a cargo. Reasignalas o dalas de baja antes de desactivar la
cuenta."* Dar la cátedra de baja **no** destraba la operación: el bloqueo mira quién es el titular,
sin importar si la cátedra sigue activa. Solo reasignar funciona. El bloqueo en sí es correcto —una
cátedra dada de baja puede conservar servicios corriendo, que consumen recursos reales—, pero el
consejo manda a la persona a un callejón sin salida.

**3. Las plantillas no se pueden corregir ni retirar.** Una plantilla define qué recibe una cátedra
cuando pide un servicio. Se crean y se consultan, nada más. Si se carga con la imagen equivocada,
queda inservible y **sigue ofreciéndose en el catálogo**: la cátedra la elige, el administrador la
aprueba comprometiendo capacidad, y recién falla al desplegar. Esto se encontró en carne propia
durante la validación: la plantilla sembrada apuntaba a una imagen de Debian que no existía en el
clúster, y no hubo forma de arreglarla desde el portal — hubo que crear otra al lado y desactivar la
vieja por base de datos.

> [!NOTE]
> Esta spec cubre la corrección y el retiro de **entidades administrativas**. No toca el ciclo de
> vida de pedidos y servicios, que ya está resuelto por las features 001 y 004, ni la reversión de
> aprobaciones, que es la feature 005.

## Clarifications

### Session 2026-08-30

- Q: ¿Retirar a una persona es borrarla o desactivarla? → A: **Desactivarla; el registro permanece.**
  Es lo coherente con el Principio V y con lo que ya se hace con pedidos y servicios. La autoría de
  un pedido tiene que seguir siendo reconstruible años después. La acción destructiva se reserva para
  cuentas que nunca produjeron nada.
- Q: Entonces, ¿qué pasa si un administrador pide borrar a alguien con historial? → A: **El sistema lo
  explica y ofrece la alternativa**, en vez de fallar. Nunca un error técnico sin traducción.
- Q: ¿Se corrige el mensaje o el bloqueo al desactivar un titular? → A: **El mensaje.** El bloqueo es
  correcto: una cátedra sin titular puede tener servicios corriendo sin nadie a quien preguntarle. Lo
  que falla es el consejo. Debe decir qué destraba de verdad.
- Q: ¿Editar una plantilla afecta a los servicios ya desplegados con ella? → A: **No.** Un servicio
  desplegado ya tiene sus recursos asignados; la plantilla describe qué se entrega de ahí en más. El
  portal debe dejarlo explícito para que nadie espere que editar una plantilla reconfigure lo que ya
  existe.
- Q: ¿Una plantilla retirada desaparece? → A: **No: deja de ofrecerse, pero sigue existiendo.** Los
  pedidos y servicios históricos la referencian y tienen que seguir siendo legibles.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Corregir una plantilla mal cargada (Priority: P1)

Un administrador se da cuenta de que una plantilla del catálogo está mal: apunta a una imagen que no
existe, o tiene recursos que ya no quiere ofrecer. La corrige desde el portal, o la retira del
catálogo si ya no sirve.

**Why this priority**: Es el único de los tres que rompe el flujo principal del sistema. Una
plantilla rota no falla al cargarse: falla **al final**, después de que la cátedra pidió y el
administrador aprobó comprometiendo capacidad. Hasta que alguien lo note, cada pedido por esa
plantilla es capacidad reservada que termina en error.

**Independent Test**: Crear una plantilla con una imagen inexistente, corregirla desde el portal y
comprobar que un pedido nuevo con ella se despliega bien; después retirarla y verificar que deja de
ofrecerse sin romper lo ya desplegado.

**Acceptance Scenarios**:

1. **Given** una plantilla con datos equivocados, **When** el administrador la corrige, **Then** los
   pedidos nuevos que la usen toman los valores corregidos.
2. **Given** una plantilla con servicios ya desplegados, **When** el administrador la corrige,
   **Then** esos servicios siguen exactamente como estaban, y el portal deja claro que la corrección
   rige de ahí en más.
3. **Given** una plantilla que ya no se quiere ofrecer, **When** el administrador la retira,
   **Then** deja de aparecer al crear un pedido, **and** los pedidos y servicios históricos que la
   usaron siguen mostrándola correctamente.
4. **Given** una plantilla retirada, **When** una cátedra intenta pedirla igual, **Then** el sistema
   no lo permite y lo explica.
5. **Given** una corrección que llevaría el disco por encima del tope permitido, **When** se
   confirma, **Then** rige la misma regla que en el alta: se rechaza salvo que quede una
   justificación registrada.

---

### User Story 2 - Retirar a una persona que ya no está (Priority: P1)

Un docente deja la facultad. El administrador retira su cuenta. Los pedidos que esa persona hizo
siguen figurando en el historial de su cátedra, con su autoría intacta.

**Why this priority**: Es rotación normal de personal, no un caso raro. Hoy el intento termina en un
error técnico sin explicación, y la única salida es tocar la base a mano — lo que la constitución
prohíbe expresamente.

**Independent Test**: Con una persona que creó pedidos, retirarla desde el portal y comprobar que la
operación se completa con un mensaje claro, que no puede volver a iniciar sesión, y que sus pedidos
siguen consultables con su autoría.

**Acceptance Scenarios**:

1. **Given** una persona que creó pedidos alguna vez, **When** el administrador la retira, **Then**
   la operación se completa sin errores técnicos y la persona deja de poder iniciar sesión.
2. **Given** esa persona retirada, **When** se consulta el historial de los pedidos que hizo,
   **Then** siguen mostrando quién los pidió.
3. **Given** una persona que nunca creó nada, **When** el administrador la retira, **Then** la
   operación se completa igual, sin que el administrador tenga que saber de antemano en cuál de los
   dos casos está.
4. **Given** una persona retirada, **When** se listan las personas del sistema, **Then** no aparece
   entre las vigentes, sin que eso implique que dejó de existir.
5. **Given** un intento de retirarse a uno mismo, **When** se confirma, **Then** el sistema lo
   impide, como ya hace hoy.

---

### User Story 3 - Un bloqueo que dice cómo salir de él (Priority: P2)

Un administrador intenta desactivar a alguien que tiene cátedras a cargo. El sistema lo impide —está
bien que lo impida— y le dice exactamente qué tiene que hacer para poder hacerlo.

**Why this priority**: El bloqueo ya funciona y protege lo que debe proteger; lo que falla es el
texto. Es el de menor impacto de los tres, pero es también el más barato de corregir, y un mensaje
que manda a un callejón sin salida erosiona la confianza en todos los demás mensajes del portal.

**Independent Test**: Intentar desactivar a un titular, seguir literalmente el consejo del mensaje, y
comprobar que la acción se destraba.

**Acceptance Scenarios**:

1. **Given** una persona titular de una cátedra, **When** el administrador intenta desactivarla,
   **Then** el sistema lo impide indicando qué cátedras lo bloquean y **qué acción concreta lo
   resuelve**.
2. **Given** ese bloqueo, **When** el administrador hace exactamente lo que el mensaje indica,
   **Then** la desactivación se completa.
3. **Given** una persona sin cátedras a cargo, **When** se la desactiva, **Then** la operación se
   completa sin fricción.

---

### Edge Cases

- **La última persona con acceso a una cátedra.** Retirar al único titular dejaría la cátedra sin
  nadie que la opere, con servicios posiblemente corriendo. Aplica el mismo criterio que hoy: se
  bloquea y se indica cómo resolverlo.
- **El último administrador.** El sistema no puede quedarse sin ninguna cuenta capaz de administrar.
- **Retirar a alguien con pedidos en curso.** Un pedido a la espera de aprobación, hecho por una
  persona que ya se fue, sigue siendo un pedido de su cátedra: no debe cancelarse solo porque quien
  lo escribió ya no esté.
- **Corregir una plantilla mientras hay un pedido aprobado sin desplegar.** Ese pedido comprometió
  capacidad según los valores viejos. Hay que definir con qué valores se despliega, y que la
  capacidad comprometida y la finalmente usada no queden en desacuerdo.
- **Retirar una plantilla con pedidos pendientes.** Los pedidos ya hechos con ella tienen que poder
  resolverse o rechazarse con una explicación, no quedar colgados.

## Requirements *(mandatory)*

### Functional Requirements

**Plantillas**

- **FR-001**: El administrador MUST poder corregir los datos de una plantilla existente.
- **FR-002**: Corregir una plantilla MUST NOT alterar los servicios ya desplegados con ella.
- **FR-003**: El portal MUST dejar explícito que una corrección rige para los pedidos futuros y no
  para lo ya entregado.
- **FR-004**: El administrador MUST poder retirar una plantilla del catálogo.
- **FR-005**: Una plantilla retirada MUST NOT ofrecerse al crear un pedido, y el sistema MUST
  rechazar los pedidos que intenten usarla igual.
- **FR-006**: Una plantilla retirada MUST seguir siendo legible desde los pedidos y servicios
  históricos que la referencian.
- **FR-007**: La corrección de una plantilla MUST estar sujeta al mismo tope de disco y a la misma
  exigencia de justificación que el alta.
- **FR-008**: Corregir o retirar plantillas MUST ser exclusivo del rol administrador.

**Personas**

- **FR-009**: El administrador MUST poder retirar a una persona sin que la operación falle por tener
  historial asociado.
- **FR-010**: Retirar a una persona MUST NOT destruir la autoría de los pedidos que creó.
- **FR-011**: Una persona retirada MUST NOT poder iniciar sesión.
- **FR-012**: Una persona retirada MUST quedar fuera de los listados operativos por defecto, sin que
  eso implique su desaparición del sistema.
- **FR-013**: El sistema MUST impedir que se retire la última cuenta con rol administrador.
- **FR-014**: El sistema MUST impedir que alguien se retire a sí mismo.
- **FR-015**: Ningún intento de retiro MUST devolver un error técnico sin traducción: si no se puede,
  el sistema explica por qué y qué hacer.

**Mensajes de bloqueo**

- **FR-016**: Todo bloqueo que impida retirar o desactivar una entidad MUST indicar una acción
  concreta que efectivamente lo resuelva.
- **FR-017**: El bloqueo por cátedras a cargo MUST seguir aplicándose aunque la cátedra esté dada de
  baja, porque puede conservar servicios vigentes; el mensaje MUST reflejar eso con precisión.

**Correspondencia entre lo aprobado y lo entregado**

> Este requisito se agregó el 2026-08-30, después del análisis de consistencia. Habilitar la
> corrección de plantillas (FR-001) vuelve alcanzable un escenario que hasta ahora era imposible, y
> que sin esta regla produciría una fuga de capacidad silenciosa. Se numera como FR-018 y no se
> intercala para no renumerar los requisitos ya referenciados por el plan y las tareas.

- **FR-018**: Un pedido aprobado MUST desplegarse con la capacidad que se le reservó al aprobarlo,
  aunque su plantilla haya cambiado entre la aprobación y el despliegue. Lo reservado, lo desplegado
  y lo registrado MUST coincidir siempre. Corregir una plantilla MUST NOT alterar de forma retroactiva
  lo que un pedido ya aprobado va a consumir.

  **Por qué es un requisito y no un detalle**: sin esta regla, un administrador que corrige una
  plantilla de 1 a 4 vCPU hace que un pedido aprobado por 1 vCPU se despliegue con 4, comprometiendo
  el clúster en 3 vCPU que nadie aprobó y sin dejar rastro en ningún historial. Es la misma clase de
  fuga que el Principio IV vino a cerrar, entrando por una puerta nueva que abre esta feature.

  Se distingue de **FR-002**, que protege lo **ya desplegado**: FR-018 protege lo **aprobado y
  todavía no desplegado**, que es el estado en el que vive una reserva de capacidad.

### Key Entities

- **Usuario**: incorpora la distinción entre estar retirado y no existir. Su autoría sobre pedidos
  sobrevive al retiro.
- **RecursoTemplate**: incorpora la posibilidad de corregirse y de salir del catálogo sin dejar de
  ser legible para lo que la referencia.
- **Cátedra**: participa como la condición que puede bloquear el retiro de una persona.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un administrador puede corregir una plantilla mal cargada desde el portal, sin
  intervención sobre la base de datos.
- **SC-002**: Ningún pedido llega a comprometer capacidad usando una plantilla que el administrador
  ya retiró del catálogo.
- **SC-003**: Retirar a un docente que dejó la institución se completa en un solo intento, sin
  errores técnicos, con independencia de cuánto historial tenga.
- **SC-004**: El consumo histórico por cátedra sigue siendo reconstruible después de retirar a las
  personas que hicieron los pedidos.
- **SC-005**: Todo mensaje de bloqueo indica una acción que, ejecutada literalmente, destraba la
  operación.
- **SC-006**: Ninguna operación de retiro o corrección expone un error técnico sin traducir a la
  persona que la ejecuta.

## Assumptions

- Retirar equivale a **desactivar**, no a destruir, salvo en el caso de cuentas que nunca produjeron
  historial, donde el borrado real sigue siendo aceptable.
- El vocabulario que ya usa el portal para pedidos y servicios dados de baja se reutiliza para
  personas y plantillas; no se introduce un concepto nuevo.
- El catálogo de plantillas que ve la cátedra ya distingue las activas: retirar una plantilla se
  apoya en ese mecanismo existente.
- La cantidad de plantillas y de personas es chica (decenas), así que no hay requisitos especiales de
  rendimiento.
- Esta feature no cambia quién puede hacer qué: todo lo que hoy es exclusivo del administrador lo
  sigue siendo.

## Impacto sobre la constitución

**No requiere enmienda.** Los tres defectos son incumplimientos de principios vigentes, no
tensiones con ellos:

- **Principio V** (el historial académico no se destruye): el borrado físico de personas lo
  contradice directamente. La autoría de un pedido es parte del rastro que el principio manda
  conservar. FR-009 a FR-012 lo alinean.
- **Principio III** (toda operación debe ser recuperable): un 500 sin explicación es exactamente el
  "estado ambiguo" que el principio prohíbe. FR-015 lo corrige.
- **Principio VI** (lenguaje entendible sin formación técnica): el principio lo exige para la
  cátedra; esta spec extiende el criterio a los mensajes que recibe el administrador, que hoy incluyen
  un consejo que no funciona y un error técnico crudo.
- **Restricciones técnicas** ("los cambios de esquema MUST versionarse con Alembic; MUST NOT
  modificarse la base a mano"): hoy corregir una plantilla **obliga** a violar esa regla, porque no
  hay otra vía. FR-001 la elimina.

## Contexto de origen

Los tres defectos se encontraron entre el 2026-08-29 y el 2026-08-30, ejecutando la validación T091
de la feature 004 contra infraestructura real y limpiando después los datos de prueba:

- La plantilla sembrada apuntaba a `debian-12`, que no existe en el clúster (tiene `debian-13` y
  `ubuntu-24.04`). Sin endpoint de corrección, hubo que crear una plantilla nueva y desactivar la
  vieja por SQL.
- Al intentar borrar la cuenta de prueba `ajeno`, que había creado un pedido: error 500 por violación
  de no-nulo sobre el solicitante del pedido.
- Al intentar desactivar esa misma cuenta, el bloqueo por cátedras a cargo aconsejó dar la cátedra de
  baja; hecho eso, el bloqueo siguió. Solo reasignar el titular lo resolvió.

Un cuarto defecto de la misma tanda —que el arranque del backend abortaba si existía más de un
administrador— ya fue corregido en el momento y no forma parte de esta spec.
