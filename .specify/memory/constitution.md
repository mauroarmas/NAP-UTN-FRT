<!--
Sync Impact Report — 2026-08-07
=================================
Version change: (plantilla sin ratificar) → 1.0.0
Bump rationale: MAJOR (0→1). Primera ratificación real; se reemplazan todos los
placeholders de la plantilla por principios vinculantes del proyecto.

Principios definidos (los cinco son nuevos; la plantilla no tenía ninguno):
  I.   Proxmox es el back-end, nunca la interfaz
  II.  La máquina de estados es la única fuente de verdad
  III. Toda operación contra la infraestructura debe ser recuperable
  IV.  Aislamiento y cuota por cátedra
  V.   El historial académico no se destruye

Secciones agregadas:
  - Restricciones Técnicas y de Seguridad
  - Flujo de Desarrollo y Compuertas de Calidad
  - Governance

Secciones removidas: ninguna (la plantilla estaba vacía).

Templates y artefactos revisados:
  ✅ .specify/templates/plan-template.md — la compuerta referencia el archivo de
     constitución de forma genérica; alinea por construcción, sin cambios
  ✅ .specify/templates/spec-template.md — sin secciones obligatorias nuevas
     derivadas de estos principios, sin cambios
  ✅ .specify/templates/tasks-template.md — la categorización de tareas ya admite
     las tareas de prueba que exige la compuerta de calidad, sin cambios
  ✅ .claude/skills/speckit-*/SKILL.md — sin referencias agent-specific obsoletas
  ✅ specs/001-pedido-soft-delete-retry/plan.md — la Constitution Check decía
     "PASS por vacuidad"; reevaluada contra los principios ya ratificados

Follow-up TODOs: ninguno. No quedan tokens sin resolver.
-->

# Constitución del Portal de Gestión — Nube Privada UTN FRT

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

**Version**: 1.0.0 | **Ratified**: 2026-08-07 | **Last Amended**: 2026-08-07
