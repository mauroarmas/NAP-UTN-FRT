# Feature Specification: Gestión de servicios para cátedra

**Feature Branch**: `003-gestion-servicios-catedra`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "La cátedra necesita más opciones de gestión sobre sus propios servicios, todas disponibles desde la pestaña "Servicios" que ya usa. Hoy esa pestaña le muestra la tabla de sus contenedores en modo solo lectura (ningún botón de acción, esos son admin-only); la cátedra no tiene forma de actuar sobre lo que ya tiene desplegado sin pedirle a un administrador que lo haga por ella. Se agregan tres capacidades sobre servicios que ya son suyos: (1) apagar y encender su servicio, (2) reiniciarlo (acción nueva, hoy no existe ni para admin), y (3) ver una consola/terminal interactiva de su contenedor embebida en el portal — una terminal real, no solo un visor de estado — sin que la cátedra jamás acceda a la interfaz de Proxmox directamente ni reciba credenciales de Proxmox (el portal actúa de proxy). El administrador debe conservar las mismas capacidades que ya tiene hoy sobre todos los servicios."

## Clarifications

### Session 2026-08-15

- Q: ¿La acción de apagar y/o reiniciar debe pedir confirmación antes de ejecutarse, o se ejecuta
  directo al hacer clic? → A: Confirmar apagar y reiniciar antes de ejecutarse (misma fricción para
  ambas, dado que las dos interrumpen lo que esté corriendo); encender no requiere confirmación,
  ya que no interrumpe nada.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apagar y encender mi propio servicio (Priority: P1)

Una persona con rol cátedra necesita apagar un servicio que no está usando, o volver a encenderlo
cuando lo necesita, sin depender de que un administrador lo haga por ella.

**Why this priority**: Es la acción más frecuente y de menor riesgo; hoy su ausencia obliga a la
cátedra a pedirle a un administrador cada apagado/encendido, lo cual es la fricción más básica que
esta spec busca eliminar.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, se puede apagarlo
desde la pestaña Servicios y ver que su estado pasa a detenido; y desde un servicio propio
detenido, encenderlo y ver que pasa a en ejecución. Ninguna de las dos acciones requiere
intervención de un administrador.

**Acceptance Scenarios**:

1. **Given** un servicio propio en ejecución, **When** la cátedra elige apagarlo y confirma la
   acción, **Then** el servicio queda detenido y su nuevo estado se refleja en la pestaña
   Servicios sin recargar la página manualmente.
2. **Given** un servicio propio detenido, **When** la cátedra elige encenderlo, **Then** el
   servicio queda en ejecución y su nuevo estado se refleja de inmediato.
3. **Given** un servicio propio ya detenido, **When** la cátedra intenta detenerlo de nuevo,
   **Then** el sistema le informa en lenguaje simple que la acción no es válida en el estado
   actual, sin exponer detalles técnicos.

---

### User Story 2 - Reiniciar mi propio servicio (Priority: P2)

Una persona con rol cátedra necesita reiniciar un servicio que dejó de responder bien, en una sola
acción, sin tener que apagarlo y volver a encenderlo por separado ni pedírselo a un administrador.

**Why this priority**: Cubre el caso de "algo no anda bien" sin llegar a un error de
infraestructura — hoy ni siquiera el administrador tiene esta acción como un paso único. Depende
de que existan los controles de encendido/apagado de US1, de los que reutiliza el resultado.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, se puede reiniciarlo
con una única acción y verificar que vuelve a quedar en ejecución (no que queda detenido esperando
un segundo paso).

**Acceptance Scenarios**:

1. **Given** un servicio propio en ejecución, **When** la cátedra elige reiniciarlo y confirma la
   acción, **Then** el servicio se apaga y vuelve a encenderse como resultado de una única acción,
   sin que la cátedra tenga que confirmar un segundo paso adicional a esa primera confirmación.
2. **Given** un servicio propio detenido, **When** la cátedra intenta reiniciarlo, **Then** el
   sistema le informa en lenguaje simple que primero debe encenderlo, sin exponer detalles
   técnicos.

---

### User Story 3 - Consola interactiva de mi propio servicio (Priority: P3)

Una persona con rol cátedra necesita acceder a una terminal real de su servicio (por ejemplo, para
instalar algo, revisar un archivo o diagnosticar un problema) directamente desde el portal, sin
recibir credenciales ni acceso a la interfaz de administración de la infraestructura subyacente.

**Why this priority**: Es la capacidad de mayor valor para una cátedra que sabe lo que necesita
hacer dentro de su propio servicio, pero también la de mayor costo de construcción; se prioriza
después de los controles de encendido/apagado/reinicio porque estos ya resuelven la fricción más
común y esta puede entregarse como incremento posterior sin bloquear al resto.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, se puede abrir una
consola interactiva desde la pestaña Servicios, escribir un comando dentro de ella y ver su
resultado, todo sin abandonar el portal ni recibir una URL o credencial de la infraestructura
subyacente.

**Acceptance Scenarios**:

1. **Given** un servicio propio en ejecución, **When** la cátedra elige abrir su consola, **Then**
   se muestra una terminal interactiva de ese servicio dentro del portal, donde puede escribir
   comandos y ver su salida en tiempo real.
2. **Given** una consola abierta, **When** la cátedra navega a otra pantalla o cierra sesión,
   **Then** esa sesión de consola deja de estar accesible.
3. **Given** un servicio propio detenido o en error, **When** la cátedra intenta abrir su consola,
   **Then** el sistema le informa que el servicio debe estar en ejecución para acceder a la
   consola, sin ofrecer un acceso que no puede funcionar.

---

### Edge Cases

- Dos personas de la misma cátedra intentan apagar y encender el mismo servicio casi al mismo
  tiempo: el sistema no debe quedar en un estado ambiguo; la segunda acción se resuelve contra el
  estado real vigente, no contra el estado que esa persona vio al cargar la pantalla.
- Un administrador y una cátedra actúan sobre el mismo servicio en paralelo (por ejemplo, el
  admin lo apaga mientras la cátedra intenta reiniciarlo): la acción de la cátedra se resuelve
  contra el estado real vigente, no queda una acción "perdida" ni el servicio en un estado
  inconsistente.
- La conexión de red de la cátedra se corta en medio de una sesión de consola: al reconectar, el
  sistema no debe haber quedado con una sesión huérfana consumiendo recursos indefinidamente.
- Una cátedra intenta apagar, encender, reiniciar o abrir la consola de un servicio que pertenece
  a otra cátedra (por ejemplo, manipulando directamente una URL): la acción se rechaza igual que
  hoy se rechaza el acceso de lectura a servicios ajenos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST permitir a una cátedra apagar y encender sus propios servicios desde
  la pestaña Servicios, sin intervención de un administrador. Apagar un servicio en ejecución MUST
  pedir una confirmación explícita antes de ejecutarse; encender un servicio detenido MUST
  ejecutarse sin pedir confirmación, ya que no interrumpe nada en curso.
- **FR-002**: El sistema MUST permitir a una cátedra reiniciar sus propios servicios en ejecución
  como una única acción, sin requerir que apague y encienda por separado. Reiniciar MUST pedir una
  confirmación explícita antes de ejecutarse, con la misma fricción que apagar.
- **FR-003**: El sistema MUST permitir a una cátedra abrir y operar una consola interactiva real de
  sus propios servicios en ejecución, directamente dentro del portal.
- **FR-004**: El sistema MUST NOT exponer a la cátedra credenciales de la infraestructura
  subyacente ni redirigirla a la interfaz de administración de esa infraestructura en ningún
  momento, incluyendo durante el uso de la consola.
- **FR-005**: Toda acción de apagado, encendido, reinicio o consola MUST restringirse a servicios
  de la propia cátedra; un intento sobre un servicio de otra cátedra MUST rechazarse de la misma
  forma en que hoy se rechaza el acceso de lectura a servicios ajenos.
- **FR-006**: El administrador MUST conservar, sin cambios, todas las capacidades de gestión de
  servicios que ya tiene hoy sobre cualquier servicio de cualquier cátedra, incluyendo las tres
  capacidades nuevas de esta spec (apagar/encender, reiniciar, consola), que quedan disponibles
  para el administrador sobre cualquier servicio del mismo modo en que ya lo están para la cátedra
  sobre los suyos.
- **FR-007**: El sistema MUST informar en lenguaje simple, sin detalles técnicos de
  infraestructura, cuándo una acción de apagado, encendido o reinicio no es válida para el estado
  actual del servicio.
- **FR-008**: El sistema MUST NOT permitir abrir una consola sobre un servicio que no está en
  ejecución; MUST informar por qué en lenguaje simple.
- **FR-009**: Una sesión de consola MUST dejar de estar accesible cuando la persona usuaria
  abandona esa vista o cierra sesión; MUST NOT quedar accesible indefinidamente sin que nadie la
  esté usando.
- **FR-010**: El estado de un servicio mostrado en la pestaña Servicios MUST reflejar el resultado
  de una acción de apagado, encendido o reinicio sin requerir que la persona usuaria recargue la
  página manualmente.

### Key Entities

- **Servicio**: entidad ya existente (contenedor desplegado de una cátedra). Esta spec no le
  agrega campos nuevos; le agrega comportamiento disponible para el rol cátedra sobre sus propios
  registros.
- **Sesión de consola**: acceso interactivo temporal a un servicio en ejecución. No es un registro
  persistente de negocio — existe solo mientras la persona usuaria la tiene abierta y no
  sobrevive a la desconexión.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una cátedra puede apagar o encender un servicio propio sin ninguna intervención de un
  administrador, en el 100% de los casos en que el estado del servicio lo permite.
- **SC-002**: Una cátedra puede reiniciar un servicio propio en ejecución completando una sola
  acción (no dos acciones separadas de apagar y encender).
- **SC-003**: Una cátedra puede abrir la consola de un servicio propio en ejecución y ver el
  resultado de un comando en menos de 15 segundos desde que elige abrirla.
- **SC-004**: El 100% de los intentos de una cátedra de actuar (apagar, encender, reiniciar, abrir
  consola) sobre un servicio que no es suyo son rechazados.
- **SC-005**: Cero casos en los que una cátedra ve u obtiene una credencial o una URL directa de la
  interfaz de administración de la infraestructura subyacente durante el uso de estas funciones.

## Assumptions

- "Reiniciar" significa un reinicio estándar del servicio (apagar y volver a encender como una
  sola operación), no una reinstalación ni una restauración a un estado anterior.
- El tipo de consola requerida es una terminal interactiva real (no un visor de solo lectura de
  estado o logs) — decisión explícita tomada en la conversación previa a esta spec, dado que es la
  que aporta valor real para diagnosticar y operar el servicio, aun siendo la de mayor costo de
  construcción de las tres capacidades.
- El administrador obtiene las mismas tres capacidades nuevas sobre cualquier servicio, como
  extensión natural de que ya tiene hoy visibilidad y control totales sobre todos los servicios;
  no se le resta ni condiciona nada de lo que ya podía hacer.
- Esta spec no incluye trazabilidad/auditoría de qué usuario ejecutó qué acción — esa capacidad
  está identificada como un hito aparte y todavía no existe en el sistema para ninguna acción
  existente; agregarla aquí sería inconsistente con el resto de las acciones ya implementadas.
- El límite de una sesión de consola por servicio a la vez (o el comportamiento si dos personas de
  la misma cátedra intentan abrir la consola del mismo servicio simultáneamente) se resuelve en la
  fase de planificación; no cambia el valor ni el alcance funcional de esta spec para quien la usa.
