<!--
Sync Impact Report — 2026-08-16
=================================
Version change: 1.1.0 → 2.0.0
Bump rationale: MAJOR. Se redefine el Principio IV de forma incompatible con lo
anterior: desaparece la cuota de recursos declarada por adelantado por cátedra,
que era una obligación explícita del principio. El aislamiento por cátedra y la
validación previa al aprovisionamiento se conservan, pero el mecanismo de control
cambia de "techo declarado" a "aprobación con reserva contra la capacidad real
del clúster". Todo artefacto que asumiera la existencia de una cuota por cátedra
queda desalineado, que es exactamente el criterio de MAJOR fijado en Governance.

Motivación (entrada del usuario, feature 004): una cuota fija por cátedra obliga
a declarar por adelantado un techo que nadie sabe estimar, produce denegaciones
automáticas injustas, y ata cada persona usuaria a una sola cátedra. El modelo
nuevo unifica la cuenta (una persona, varias cátedras) y traslada el control al
único momento en que hay una decisión informada posible: la aprobación del
pedido por parte del administrador.

Principios modificados:
  II. La máquina de estados es la única fuente de verdad
      → ampliado: se admite explícitamente al sistema como autor de una
        transición (vencimiento, pausado por inactividad, liberación de reserva).
        Antes el principio exigía autor sin contemplar que pudiera no ser una
        persona, lo que dejaba las acciones automáticas sin forma legítima de
        registrarse.
  IV. "Aislamiento y cuota por cátedra"
      → "Aislamiento por cátedra; la capacidad se controla al aprobar"
        (redefinición incompatible — ver bump rationale)
  VI. La cátedra pide y observa; el administrador gestiona
      → ajuste de redacción: "consumo respecto de su cuota" pasa a "consumo
        vigente de sus servicios"; se agrega la fecha de vencimiento como
        información que la cátedra MUST poder ver.

Secciones modificadas:
  "Restricciones Técnicas y de Seguridad" → la cláusula de operaciones mutantes
  decía que todo, salvo la creación de pedidos, exige rol administrador. Eso ya
  contradecía al principio VI y a la feature 003 (la cátedra opera sus propios
  servicios). Se corrige enumerando las excepciones reales.
  "Flujo de Desarrollo y Compuertas de Calidad" → la compuerta de pruebas
  nombraba "cuotas"; pasa a nombrar "control de capacidad". Se aclara que las
  enmiendas no reinician el plazo de la compuerta.

Secciones agregadas: ninguna.
Secciones removidas: ninguna.

Templates y artefactos revisados:
  ✅ .specify/templates/plan-template.md — la Constitution Check se completa
     dinámicamente contra el archivo vigente ("[Gates determined based on
     constitution file]"); no hardcodea principios, sin cambios
  ✅ .specify/templates/spec-template.md — sin referencias a cuota, sin cambios
  ✅ .specify/templates/tasks-template.md — sin referencias a cuota, sin cambios
  ✅ .claude/skills/speckit-*/SKILL.md — sin referencias agent-specific obsoletas
  ✅ frontend/src/pages/Dashboard.jsx — el ⚠ registrado en v1.1.0 quedó
     resuelto: el dashboard deriva al rol cátedra a PanelCatedra
     (Dashboard.jsx:38), conforme al principio VI
  ✅ specs/004-unificar-usuario-catedra/ — es la feature que motiva esta
     enmienda; su spec ya está redactada contra estos principios
  ⚠ specs/001-pedido-soft-delete-retry/ — menciona cuota al justificar que lo
     dado de baja no la ocupa. La regla de fondo (el consumo cuenta solo
     recursos vigentes) sobrevive en el nuevo IV; la redacción queda obsoleta.
     Feature entregada: no se reescribe, se anota.
  ⚠ specs/002-panel-catedra-simple/ — el panel muestra consumo contra cuota.
     Requiere revisión al implementar 004; la spec 004 ya lo cubre (FR-011).
  ⚠ specs/003-gestion-servicios-catedra/ — menciona cuota en plan.md y
     research.md. No afecta su alcance (acciones sobre servicios propios).
  ⚠ backend/app/routers/catedras.py, backend/app/services/pedido_service.py —
     implementan la cuota por cátedra (verificar_cuota, _cuotas_comprometidas).
     Código preexistente: no queda en infracción retroactiva. Su remediación es
     el objeto de la feature 004.

Follow-up TODOs: ninguno pendiente de definición en este documento.
-->

# Constitución del Portal de Gestión — Nube Acaedmia Personal UTN FRT

## Core Principles

### I. Proxmox es el back-end, nunca la interfaz

El portal es el **único** punto de contacto entre las personas usuarias y la infraestructura
(Proxmox VE, TrueNAS, MikroTik). Ninguna persona usuaria final recibe credenciales de Proxmox,
ni accede a su interfaz, ni depende de su modelo de permisos.

- El sistema MUST mantener autenticación propia (usuario + contraseña + 2FA); MUST NOT delegar
  el login en Proxmox.
- Toda operación contra la infraestructura MUST pasar por la capa de servicios del portal
  (`app/services/`); los routers MUST NOT invocar `proxmoxer` directamente.
- Los identificadores de recurso de Proxmox (VMID, nodo) son detalle interno: el portal los
  mapea en su propia base de datos y MUST NOT exigir que la persona usuaria los conozca o gestione.

**Rationale**: Es la premisa fundacional del proyecto, fijada por el profesor: *"Olvidémonos de
Proxmox. Proxmox va a ser nuestro back. El software tiene que gestionar todo."* Si esta frontera
se filtra, el portal deja de ser un middleware y pasa a ser un adorno sobre Proxmox.

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

**Version**: 2.0.0 | **Ratified**: 2026-08-07 | **Last Amended**: 2026-08-16
