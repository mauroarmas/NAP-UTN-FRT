<!--
Sync Impact Report — 2026-08-15
=================================
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR. Se agrega un principio nuevo (no se redefine ni remueve
ninguno de los cinco existentes); corresponde a una ampliación material de la
guía vigente, no a una corrección de redacción.

Principio agregado:
  VI. La cátedra pide y observa; el administrador gestiona

Motivación (entrada del usuario): el dashboard actual muestra a un usuario
cátedra la misma pantalla orientada a infraestructura que ve el administrador
(tabla global de cátedras, conteos agregados), sin priorizar sus dos tareas
reales: cargar un pedido rápido y ver cómo vienen sus servicios. No todas las
cátedras son técnicas, así que esa pantalla no aporta valor y es fricción.

Secciones agregadas: ninguna nueva a nivel de encabezado; el principio VI se
agrega dentro de "Core Principles".

Secciones removidas: ninguna.

Templates y artefactos revisados:
  ✅ .specify/templates/plan-template.md — la Constitution Check se completa
     dinámicamente contra el archivo de constitución vigente; no requiere
     hardcodear principios, sin cambios
  ✅ .specify/templates/spec-template.md — sin secciones obligatorias nuevas
     derivadas de este principio (es una guía de diseño de UI, no una sección
     de spec nueva), sin cambios
  ✅ .specify/templates/tasks-template.md — la categorización por historia de
     usuario ya admite tareas de frontend por rol, sin cambios
  ✅ .claude/skills/speckit-*/SKILL.md — sin referencias agent-specific obsoletas
  ✅ specs/001-pedido-soft-delete-retry/plan.md — feature exclusivamente de
     backend (soft delete y reintento); no toca UI ni distingue vista por rol,
     el principio VI no le aplica, se mantiene el PASS ya registrado
  ⚠ frontend/src/pages/Dashboard.jsx — implementación actual viola el
     principio VI recién ratificado (ver detalle abajo); código preexistente,
     no queda en infracción retroactiva automática, pero corresponde abrir un
     feature (`/speckit-specify`) para remediarlo

Follow-up TODOs: ninguno pendiente de definición en este documento. Queda
pendiente, fuera de la constitución, iniciar la spec que rediseñe el
dashboard de cátedra conforme al principio VI.
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
- La persona usuaria MUST poder consultar en qué estado está su pedido en todo momento.

**Rationale**: El flujo estilo AWS con estados visibles es un requisito explícito del proyecto.
Además, la divergencia entre lo que la tabla de transiciones promete y lo que el orquestador
ejecuta ya produjo un defecto real (pedidos atascados sin posibilidad de recuperación); este
principio existe para que esa clase de desajuste sea detectable por inspección.

### III. Toda operación contra la infraestructura debe ser recuperable

Las llamadas a Proxmox fallan: por red, por timeout, por estado del clúster. El sistema se diseña
asumiendo el fallo, no la excepción.

- Ante un fallo, el sistema MUST dejar el pedido en un estado definido y explícito, con el motivo
  registrado; MUST NOT dejar la base de datos en un estado intermedio o ambiguo.
- MUST NOT quedar recursos huérfanos: todo contenedor creado en la infraestructura tiene su
  registro correspondiente en la base, y viceversa. Ante duda, el sistema reconcilia antes de crear.
- Toda operación de reintento MUST ser pseudo-idempotente: repetirla no MUST multiplicar recursos
  reales.
- Los errores devueltos MUST distinguir el fallo de infraestructura (502) del conflicto de estado
  (409) y del problema de permisos (403).

**Rationale**: Los recursos huérfanos consumen cuota real del clúster sin figurar en ningún
listado, y son invisibles hasta que el clúster se queda sin capacidad. En un entorno compartido
entre cátedras, esa clase de fuga es especialmente costosa de diagnosticar.

### IV. Aislamiento y cuota por cátedra

La cátedra es la unidad de aislamiento del sistema. El portal es multi-inquilino desde el diseño,
no como agregado posterior.

- Una persona usuaria con rol de cátedra MUST ver y operar únicamente sobre los recursos de su
  propia cátedra; toda consulta de listado MUST filtrar por cátedra salvo para el rol administrador.
- La cuota (vCPU, RAM, disco) MUST validarse **antes** de aprovisionar, nunca después.
- El cómputo de consumo MUST considerar únicamente recursos vigentes: lo dado de baja no ocupa cuota.
- El disco de un contenedor MUST NOT superar los 8 GB sin una justificación explícita registrada.

**Rationale**: La infraestructura es finita y compartida entre cátedras. Una cuota que se valida
tarde, o que cuenta recursos que ya no existen, produce tanto denegaciones injustas como
sobrecompromiso del clúster.

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
contenedores se hayan eliminado.

### VI. La cátedra pide y observa; el administrador gestiona

El rol cátedra no es un operador de infraestructura. Su pantalla principal se diseña alrededor de
dos tareas, no alrededor de lo que el sistema sabe mostrar.

- La pantalla principal del rol cátedra MUST limitarse a: acceso directo para crear un pedido, y
  el estado/comportamiento de sus propios servicios (activo, con problemas, consumo dentro de su
  cuota). MUST NOT mostrar información cuyo dominio es el administrador: listado de otras
  cátedras, conteos agregados de todo el sistema, o estado del nodo/clúster Proxmox.
- El flujo de creación de un pedido MUST ser operable por una persona sin formación técnica: MUST
  NOT exigir que la cátedra conozca o complete parámetros de infraestructura (VMID, nodo, template
  ID de Proxmox); se limita a elegir qué necesita y cuánto, dentro de su cuota asignada.
- Todo pedido nuevo MUST quedar visible en la bandeja de gestión del administrador sin acción
  manual de sincronización. Aprobar, rechazar y gestionar el ciclo de vida del pedido es
  responsabilidad exclusiva del administrador; la cátedra consulta el estado, no lo cambia.
- El "comportamiento de sus servicios" que ve la cátedra MUST presentarse en términos entendibles
  sin conocimientos de administración de sistemas (activo/inactivo, consumo respecto de su cuota);
  MUST NOT requerir que interprete métricas de infraestructura cruda (uso físico del nodo, CPU
  steal, particionado de disco), que quedan reservadas a la vista de administrador.

**Rationale**: No todas las cátedras son técnicas — es una condición explícita del proyecto, no un
detalle de estilo. Una pantalla que expone el mismo panorama de infraestructura al administrador y
a la cátedra fuerza a esta última a interpretar información que no puede accionar y que no
responde a su necesidad real (pedir rápido, ver cómo viene su servicio), lo que degrada la
adopción por parte de quien menos margen tiene para lidiar con fricción técnica.

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
- Toda operación mutante sobre pedidos, servicios, usuarios, cátedras y templates MUST exigir rol
  administrador, salvo la creación de pedidos por parte de la cátedra solicitante.
- Las credenciales de infraestructura MUST vivir únicamente en configuración de entorno, nunca en
  el código ni en el repositorio.
- Los cambios de esquema MUST versionarse con Alembic; MUST NOT modificarse la base a mano.

## Flujo de Desarrollo y Compuertas de Calidad

**Metodología**: incremental e iterativa, con desarrollo dirigido por especificación (Spec Kit).
Toda funcionalidad nueva de entidad significativa MUST atravesar `/speckit-specify` →
`/speckit-plan` → `/speckit-tasks` antes de implementarse.

**Compuertas de calidad**:

- Todo código nuevo o modificado que toque **orquestación, máquina de estados o cuotas** MUST
  incluir pruebas automatizadas, y esas pruebas MUST cubrir al menos un camino de fallo de
  infraestructura simulado. No alcanza con probar el camino feliz.
- Las pruebas MUST poder ejecutarse sin un Proxmox real, mediante un doble de prueba del cliente.
- Una compuerta que no se puede verificar automáticamente MUST declararse como tal en el plan, en
  lugar de darse por cumplida.

**Alcance de la compuerta**: se aplica a partir de la ratificación de esta constitución. El código
anterior no queda en infracción retroactiva, pero MUST incorporar pruebas cuando se lo modifique.

**Rationale de la excepción**: al momento de ratificar, el repositorio no tiene pruebas
automatizadas. Declarar todo el código existente en infracción haría la constitución inaplicable
desde el día uno; el criterio de "cubrir al tocar" hace que la deuda se salde donde importa.

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

**Version**: 1.1.0 | **Ratified**: 2026-08-07 | **Last Amended**: 2026-08-15
