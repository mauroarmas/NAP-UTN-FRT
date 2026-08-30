<!--
Sync Impact Report — 2026-08-30
=================================
Version change: 2.0.0 → 3.0.0
Bump rationale: MAJOR. Se redefine el Principio I de forma incompatible con lo
anterior: dejaba de existir cualquier caso en que una persona usuaria final
accediera a la interfaz de Proxmox, y ahora se admite exactamente uno —la
consola interactiva del contenedor propio—. Todo artefacto que asumiera que
ninguna persona toca Proxmox queda desalineado, que es el criterio de MAJOR
fijado en Governance.

Motivación (decisión del usuario, 2026-08-30): la consola embebida que la spec
003 especificaba no es implementable. El relay del portal conecta y autentica
contra Proxmox, pero la sesión muere sin transmitir: Proxmox no acepta API
tokens para el WebSocket de consola y exige un ticket de sesión. Sostener el
principio al pie de la letra dejaría a las cátedras sin ninguna forma de
interactuar con su propio contenedor, que es la razón por la que piden el
servicio. Entre un principio intacto y un sistema inútil, se elige acotar el
principio y dejar registrado por qué.

Principios modificados:
  I. "Proxmox es el back-end, nunca la interfaz"
      → se conserva el título y toda la regla de gestión, y se agrega una
        excepción única, nombrada y acotada: el acceso a la consola interactiva
        del contenedor propio. Se agregan además las condiciones que la
        mantienen acotada, para que no sea la puerta por la que se filtre el
        resto (redefinición incompatible — ver bump rationale).

Secciones modificadas:
  "Restricciones Técnicas y de Seguridad" → se agrega la cláusula de identidad
  en Proxmox: la excepción solo es admisible si el acceso está delimitado por el
  pool de la cátedra, porque de lo contrario el aislamiento por cátedra
  (Principio IV) se perdería al cruzar la frontera.

Secciones agregadas: ninguna.
Secciones removidas: ninguna.

Templates y artefactos revisados:
  ✅ .specify/templates/*.md — no referencian el Principio I, sin cambios
  ⚠ specs/003-gestion-servicios-catedra/ — su US3 especifica una consola
     embebida con el portal de proxy. Esa parte queda **superada**: se anota en
     la spec y su T025 se cierra con el alcance nuevo.
  ✅ frontend/src/components/ConsolaServicio.jsx — se elimina: implementaba la
     consola embebida que ya no se persigue, y nunca estuvo conectada
  ✅ backend/app/routers/servicios.py — se elimina el relay de WebSocket y el
     endpoint de ticket, que solo servían a ese componente
  ✅ specs/001, 002, 004, 005, 006 — no dependen del Principio I

Follow-up TODOs: ninguno pendiente de definición en este documento.
-->


# Constitución del Portal de Gestión — Nube Acaedmia Personal UTN FRT

## Core Principles

### I. Proxmox es el back-end, nunca la interfaz — con una única excepción nombrada

El portal es el **único** punto de contacto entre las personas usuarias y la gestión de la
infraestructura (Proxmox VE, TrueNAS, MikroTik). Ninguna persona usuaria final administra recursos
desde la interfaz de Proxmox, ni depende de su modelo de permisos para operar el portal.

- El sistema MUST mantener autenticación propia (usuario + contraseña + 2FA); MUST NOT delegar
  el login del portal en Proxmox.
- Toda operación contra la infraestructura MUST pasar por la capa de servicios del portal
  (`app/services/`); los routers MUST NOT invocar `proxmoxer` directamente.
- Los identificadores de recurso de Proxmox (VMID, nodo) son detalle interno: el portal los
  mapea en su propia base de datos y MUST NOT exigir que la persona usuaria los conozca o gestione.

**Excepción única: la consola interactiva del contenedor propio.**

El acceso a la terminal de un contenedor MAY resolverse derivando a la consola de Proxmox, para
el rol administrador y para el rol cátedra sobre sus propios servicios. Es la **única** excepción
admitida a este principio y MUST mantenerse acotada:

- La excepción cubre **solo** la sesión interactiva con el contenedor. Toda otra operación
  —crear, aprobar, desplegar, apagar, reiniciar, renovar, dar de baja— MUST seguir ocurriendo
  dentro del portal.
- El portal MUST NOT derivar a Proxmox ninguna pantalla de gestión, listado ni panel: la
  derivación se limita al destino de consola del servicio concreto que la persona ya opera.
- La pertenencia del servicio MUST verificarse en el portal antes de ofrecer el acceso; MUST NOT
  delegarse esa comprobación en Proxmox.
- Que exista esta excepción MUST NOT usarse como precedente para abrir otras. Cualquier
  derivación nueva hacia Proxmox exige una enmienda propia.

**Rationale**: la premisa fundacional del proyecto la fijó el profesor —*"Olvidémonos de Proxmox.
Proxmox va a ser nuestro back. El software tiene que gestionar todo."*— y sigue rigiendo para todo
lo que es gestión. La consola es el único punto donde no se puede cumplir: Proxmox no acepta API
tokens para el WebSocket de consola y exige un ticket de sesión, de modo que un proxy propio del
portal no llega a transmitir. Se intentó y quedó documentado.

Sostener el principio al pie de la letra en este punto no lo protegería: dejaría a las cátedras sin
ninguna forma de interactuar con el contenedor que pidieron, que es la razón por la que existe el
servicio. Un principio que vuelve inútil al sistema que ordena no se está cumpliendo, se está
incumpliendo de la peor manera. La excepción se nombra, se acota y se registra —en lugar de
tolerarse en silencio— porque una frontera con una puerta declarada es defendible, y una frontera
que se filtra sin que nadie lo diga, no.

### II. La máquina de estados es la única fuente de verdad

El ciclo de vida de un pedido está definido en un único lugar y ningún camino de código puede
esquivarlo.

- Todo cambio de `estado` de un pedido MUST ejecutarse a través de la función central de
  transición; MUST NOT existir asignación directa del campo `estado` fuera de ella.
- Toda transición declarada como válida MUST tener un ejecutor real que la lleve a cabo. Una
  transición permitida por la tabla pero que ningún código concreta es un defecto, no una
  funcionalidad pendiente.
- Toda transición MUST quedar registrada en el historial del pedido, con su autor y su motivo.
- El autor de una transición puede ser una persona o el propio sistema. Cuando la ejecuta el
  sistema sin intervención humana —vencimiento de un servicio, pausado por inactividad, liberación
  de una reserva de capacidad—, MUST quedar identificado como autor propio; MUST NOT atribuirse a
  una persona que no la decidió, ni omitirse del historial por carecer de autor humano.
- La persona usuaria MUST poder consultar en qué estado está su pedido en todo momento.

**Rationale**: El flujo estilo AWS con estados visibles es un requisito explícito del proyecto.
Además, la divergencia entre lo que la tabla de transiciones promete y lo que el orquestador
ejecuta ya produjo un defecto real (pedidos atascados sin posibilidad de recuperación); este
principio existe para que esa clase de desajuste sea detectable por inspección. La admisión del
sistema como autor se agrega porque el modelo de recuperación automática de capacidad ejecuta
transiciones que ninguna persona decide: sin esta salida, esas acciones quedarían fuera del
historial o falsamente atribuidas a alguien.

### III. Toda operación contra la infraestructura debe ser recuperable

Las llamadas a Proxmox fallan: por red, por timeout, por estado del clúster. El sistema se diseña
asumiendo el fallo, no la excepción.

- Ante un fallo, el sistema MUST dejar el pedido en un estado definido y explícito, con el motivo
  registrado; MUST NOT dejar la base de datos en un estado intermedio o ambiguo.
- MUST NOT quedar recursos huérfanos: todo contenedor creado en la infraestructura tiene su
  registro correspondiente en la base, y viceversa. Ante duda, el sistema reconcilia antes de crear.
- Tampoco MUST quedar **capacidad huérfana**: una capacidad comprometida que nunca llega a
  materializarse en un recurso real MUST liberarse sola, sin depender de que alguien lo advierta.
- Toda operación de reintento MUST ser pseudo-idempotente: repetirla no MUST multiplicar recursos
  reales.
- Los errores devueltos MUST distinguir el fallo de infraestructura (502) del conflicto de estado
  (409) y del problema de permisos (403).

**Rationale**: Los recursos huérfanos consumen capacidad real del clúster sin figurar en ningún
listado, y son invisibles hasta que el clúster se queda sin capacidad. En un entorno compartido
entre cátedras, esa clase de fuga es especialmente costosa de diagnosticar. La capacidad reservada
y nunca usada produce el mismo efecto sin que exista siquiera un contenedor que encontrar.

### IV. Aislamiento por cátedra; la capacidad se controla al aprobar

La cátedra es la unidad de aislamiento y de atribución histórica del sistema. El portal es
multi-inquilino desde el diseño, no como agregado posterior. La infraestructura es finita, y el
punto donde eso se controla es la aprobación del pedido.

**Aislamiento**:

- Una persona usuaria con rol de cátedra MUST ver y operar únicamente sobre los recursos de las
  cátedras a su cargo; toda consulta de listado MUST filtrar por ese conjunto, salvo para el rol
  administrador.
- Los pedidos, servicios, historial y consumo pertenecen a la **cátedra**, no a la persona, y MUST
  sobrevivir a un cambio de titular.

**Control de capacidad**:

- MUST NOT exigirse ni declararse por adelantado un techo de recursos por cátedra. Una cátedra
  tiene los servicios que le fueron aprobados, no un cupo estimado de antemano.
- La capacidad MUST validarse contra la capacidad real del clúster **antes** de aprovisionar,
  nunca después.
- La aprobación de un pedido MUST reservar en el acto la capacidad comprometida, aunque el recurso
  todavía no exista. La verificación de disponibilidad y la creación de la reserva MUST constituir
  una operación indivisible: el sistema MUST NOT resolver una aprobación sobre valores de capacidad
  que pudieron cambiar entre la consulta y la confirmación.
- El cálculo de capacidad comprometida MUST incluir las reservas vigentes —pedidos aprobados cuyo
  recurso aún no fue desplegado—, no solamente lo ya desplegado.
- Comprometer más capacidad de la disponible MUST ser posible únicamente como acto deliberado del
  administrador, advertido por el sistema y con justificación registrada. MUST NOT ocurrir como
  efecto lateral de decisiones individualmente correctas.
- La capacidad MUST poder recuperarse sin depender de que alguien se acuerde: todo servicio MUST
  tener un vencimiento conocido por su cátedra desde que queda disponible.
- El cómputo de consumo MUST considerar únicamente recursos vigentes: lo dado de baja no ocupa
  capacidad.
- El disco de un contenedor MUST NOT superar los 8 GB sin una justificación explícita registrada.

**Rationale**: La cuota fija por cátedra obligaba a declarar por adelantado un techo que nadie sabe
estimar antes de que empiece la cursada, y convertía errores de estimación en denegaciones
automáticas contra personas que no podían hacer nada al respecto. El control no desaparece: se
mueve al único momento en que hay una decisión informada posible, que es cuando el administrador ve
el pedido concreto contra la capacidad real. Pero trasladarlo a una persona sin reserva sería peor
que la cuota: entre consultar la capacidad libre y que el recurso exista hay una ventana en la que
la información mostrada ya no es cierta, y el administrador puede sobrecomprometer el clúster sin
cometer un solo error individual. Por eso la reserva —y su atomicidad— son parte del principio y no
un detalle de implementación.

### V. El historial académico no se destruye

El sistema conserva el rastro de lo que ocurrió, aunque el recurso físico ya no exista.

- La baja de pedidos y servicios MUST ser lógica: el recurso real se libera, el registro permanece.
- El historial de transiciones es de solo agregado: MUST NOT sobrescribirse ni borrarse, ni siquiera
  al reintentar una operación fallida.
- El consumo histórico por cátedra MUST seguir siendo reconstruible sin recurrir a copias de seguridad.
- Los registros dados de baja MUST quedar excluidos de los listados operativos por defecto, sin que
  eso implique su desaparición.

**Rationale**: El destinatario del sistema es una institución académica que necesita responder
"cuántos recursos consumió esta cátedra el cuatrimestre pasado" mucho después de que los
contenedores se hayan eliminado. Es además la razón por la que la cátedra sigue siendo una entidad
propia y no un atributo de la persona: si los recursos colgaran de quien dicta la materia, cambiar
de titular rompería la trazabilidad.

### VI. La cátedra pide y observa; el administrador gestiona

El rol cátedra no es un operador de infraestructura. Su pantalla principal se diseña alrededor de
dos tareas, no alrededor de lo que el sistema sabe mostrar.

- La pantalla principal del rol cátedra MUST limitarse a: acceso directo para crear un pedido, y el
  estado y comportamiento de los servicios de las cátedras a su cargo. MUST NOT mostrar información
  cuyo dominio es el administrador: listado de cátedras ajenas, conteos agregados de todo el
  sistema, o estado del nodo/clúster Proxmox.
- El flujo de creación de un pedido MUST ser operable por una persona sin formación técnica: MUST
  NOT exigir que la cátedra conozca o complete parámetros de infraestructura (VMID, nodo, template
  ID de Proxmox); se limita a elegir qué necesita y para cuál de sus cátedras. MUST NOT exigirle
  encuadrarse por sí misma en un techo de recursos: resolver el pedido es tarea del administrador.
- Todo pedido nuevo MUST quedar visible en la bandeja de gestión del administrador sin acción
  manual de sincronización. Aprobar, rechazar y gestionar el ciclo de vida del pedido es
  responsabilidad exclusiva del administrador; la cátedra consulta el estado, no lo cambia.
- El "comportamiento de sus servicios" que ve la cátedra MUST presentarse en términos entendibles
  sin conocimientos de administración de sistemas: activo o inactivo, el consumo vigente de sus
  servicios, y hasta cuándo los tiene disponibles. MUST NOT requerir que interprete métricas de
  infraestructura cruda (uso físico del nodo, CPU steal, particionado de disco), que quedan
  reservadas a la vista de administrador.
- Toda acción del sistema que afecte la disponibilidad de un servicio sin que la cátedra la haya
  pedido —pausarlo por inactividad, aplicarle su vencimiento— MUST avisarse con antelación
  suficiente para reaccionar. MUST NOT ejecutarse por sorpresa.

**Rationale**: No todas las cátedras son técnicas — es una condición explícita del proyecto, no un
detalle de estilo. Una pantalla que expone el mismo panorama de infraestructura al administrador y
a la cátedra fuerza a esta última a interpretar información que no puede accionar y que no
responde a su necesidad real (pedir rápido, ver cómo viene su servicio), lo que degrada la
adopción por parte de quien menos margen tiene para lidiar con fricción técnica. El aviso previo se
agrega porque un sistema que recupera capacidad por su cuenta puede apagar el trabajo de alguien: si
lo hace en silencio, la cátedra no tiene forma de distinguirlo de una falla.

## Restricciones Técnicas y de Seguridad

**Stack fijo** (decisiones ya tomadas, no se revisan sin enmienda a esta constitución):

| Capa | Tecnología |
|---|---|
| Backend | Python + FastAPI + proxmoxer |
| Base de datos | PostgreSQL (SQLAlchemy async + Alembic) |
| Frontend | React + Vite (SPA) |

**Seguridad**:

- La autenticación MUST ser propia del portal: usuario + contraseña + 2FA (TOTP). El login de
  Proxmox MUST NOT usarse.
- Toda operación mutante sobre usuarios, cátedras, templates y el ciclo de vida de los pedidos MUST
  exigir rol administrador. Las únicas excepciones son las que el rol cátedra ejerce sobre lo
  propio: crear un pedido, solicitar la renovación de un servicio, y operar los servicios de sus
  cátedras dentro de las acciones que el portal le concede. Aprobar, rechazar y resolver pedidos
  MUST seguir siendo exclusivo del administrador.
- Toda operación del rol cátedra MUST verificar la pertenencia del recurso a alguna de sus cátedras
  antes de ejecutarse; la pertenencia MUST NOT inferirse de lo que el cliente envía.
- Las credenciales de infraestructura MUST vivir únicamente en configuración de entorno, nunca en
  el código ni en el repositorio.
- **Identidad en Proxmox para la consola** (habilita la excepción del Principio I): si una persona
  con rol cátedra necesita identidad propia en Proxmox para abrir la consola, esa identidad MUST
  estar delimitada al pool de recursos de sus cátedras. MUST NOT otorgarse una cuenta con
  visibilidad sobre el clúster completo ni sobre recursos de otras cátedras. Sin esa delimitación
  la excepción del Principio I no es admisible, porque el aislamiento por cátedra (Principio IV)
  se perdería al cruzar la frontera: dejaría de sostenerlo el portal y nadie lo sostendría del
  otro lado.
- Los cambios de esquema MUST versionarse con Alembic; MUST NOT modificarse la base a mano.

## Flujo de Desarrollo y Compuertas de Calidad

**Metodología**: incremental e iterativa, con desarrollo dirigido por especificación (Spec Kit).
Toda funcionalidad nueva de entidad significativa MUST atravesar `/speckit-specify` →
`/speckit-plan` → `/speckit-tasks` antes de implementarse.

**Compuertas de calidad**:

- Todo código nuevo o modificado que toque **orquestación, máquina de estados o control de
  capacidad** (reservas, vencimientos, pausado por inactividad) MUST incluir pruebas automatizadas,
  y esas pruebas MUST cubrir al menos un camino de fallo de infraestructura simulado. No alcanza con
  probar el camino feliz.
- El código que decide sobre capacidad MUST probarse además con al menos un escenario de
  concurrencia: dos decisiones simultáneas sobre la misma capacidad disponible.
- Las pruebas MUST poder ejecutarse sin un Proxmox real, mediante un doble de prueba del cliente.
- Una compuerta que no se puede verificar automáticamente MUST declararse como tal en el plan, en
  lugar de darse por cumplida.

**Alcance de la compuerta**: se aplica a partir de la ratificación original de esta constitución
(2026-08-07). Las enmiendas posteriores no reinician este plazo. El código anterior a esa fecha no
queda en infracción retroactiva, pero MUST incorporar pruebas cuando se lo modifique.

**Rationale de la excepción**: al momento de ratificar, el repositorio no tenía pruebas
automatizadas. Declarar todo el código existente en infracción haría la constitución inaplicable
desde el día uno; el criterio de "cubrir al tocar" hace que la deuda se salde donde importa. El
escenario de concurrencia se agrega porque el fallo característico del control de capacidad no se
manifiesta en una ejecución aislada: aparece cuando dos decisiones correctas se toman a la vez.

## Governance

**Autoridad**: esta constitución prevalece sobre cualquier otra práctica del proyecto. Ante
conflicto entre un documento de diseño y estos principios, prevalecen los principios.

**Enmiendas**: cualquier cambio MUST documentarse en este archivo con su justificación, MUST
actualizar el número de versión, y MUST revisar los artefactos dependientes (plantillas de
`.specify/templates/` y specs vigentes en `specs/`).

**Versionado semántico**:

- **MAJOR**: se remueve o redefine un principio de forma incompatible con lo anterior.
- **MINOR**: se agrega un principio o sección, o se amplía materialmente una guía existente.
- **PATCH**: aclaraciones, redacción, correcciones sin cambio de semántica.

**Revisión de cumplimiento**: la Constitution Check del `plan.md` de cada feature MUST evaluarse
contra estos principios antes de la fase de investigación, y reevaluarse tras el diseño. Toda
violación aceptada MUST registrarse en la tabla de Complexity Tracking con su justificación y la
alternativa más simple que se descartó; una violación sin justificación registrada bloquea la
implementación.

**Version**: 3.0.0 | **Ratified**: 2026-08-07 | **Last Amended**: 2026-08-30
