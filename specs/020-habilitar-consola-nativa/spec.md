# Feature Specification: Habilitar la consola nativa de Linux IaaS

**Feature Branch**: `020-habilitar-consola-nativa`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Habilitar la consola nativa de Proxmox para Linux IaaS en el laboratorio frt/pve91. Hoy la consola de un servicio devuelve consola_no_habilitada porque la configuración de acceso a consola está vacía. Hay que montar y probar en real el circuito ya diseñado en la spec 009 y en el contrato de conexión: identidades individuales por persona (nunca compartidas), permisos limitados al pool de la cátedra, inventario institucional, prueba real de revocación, evidencia tipada y trámite completado. Resultado esperado: una persona de cátedra con identidad asignada abre la consola de su Linux IaaS en el navegador; otra cátedra y quien no tenga identidad siguen bloqueadas. No ampliar la excepción de la constitución ni dar acceso a otras pantallas de Proxmox. Incluir un runbook reutilizable para la universidad y no copiar identidades del Proxmox de Mauro."

<!-- Principio I: esta feature NO abre una excepción nueva. Usa la excepción única ya enmendada
     (consola interactiva del contenedor propio) y la mantiene acotada. Principio VII: la persona
     docente no aporta datos nuevos; el trabajo es institucional (infraestructura + administración). -->

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Abrir la consola de mi Linux desde el navegador (Priority: P1)

Una persona responsable de cátedra tiene un servicio Linux IaaS encendido y con vigencia. Desde el portal pulsa la consola de ese servicio y llega a la terminal de **su** contenedor en el navegador, donde inicia sesión con su cuenta individual de infraestructura. Puede trabajar sin instalar nada ni usar su propia clave SSH.

**Why this priority**: Es el resultado que hoy está bloqueado y el único motivo de la feature. Sin él las cátedras sólo tienen SSH desde una máquina permitida.

**Independent Test**: Con la compuerta habilitada en el laboratorio, una persona de la cátedra 3 con identidad asignada abre la consola de su Ubuntu encendido y ejecuta un comando. Se demuestra sola, sin las otras historias.

**Acceptance Scenarios**:

1. **Given** una persona de cátedra con identidad individual asignada, un servicio de su cátedra encendido, con vigencia y con identidad de infraestructura confirmada, **When** pulsa la consola, **Then** el portal la lleva al destino de consola de ese servicio y nada más, y puede abrir una terminal.
2. **Given** esa misma persona, **When** intenta abrir la consola de un servicio de **otra** cátedra, **Then** el portal la rechaza antes de ofrecer ningún destino.
3. **Given** una persona sin identidad individual asignada o con identidad desconocida, **When** pulsa la consola, **Then** recibe un mensaje claro de que la consola no está habilitada para ella y no se le ofrece ningún destino.
4. **Given** un servicio detenido o sin vigencia, **When** se pide la consola, **Then** se rechaza con el motivo, sin consultar a infraestructura.
5. **Given** la cuenta individual de infraestructura, **When** la persona intenta abrir cualquier otra pantalla de gestión (listado de nodos, otros contenedores, almacenamiento), **Then** no tiene permisos para verla ni operarla.

---

### User Story 2 - Retirar el acceso de verdad (Priority: P1)

Cuando una persona deja la cátedra, cambia de rol o se reasigna la titularidad, administración inicia el trámite y el acceso nativo anterior deja de funcionar: la consola abierta se corta, una dirección o ticket guardado es rechazado y las otras cátedras legítimas de esa persona siguen funcionando.

**Why this priority**: Es condición de seguridad de la excepción. Sin una revocación demostrada la constitución y el contrato de la 009 exigen que la consola siga cerrada; por eso es P1 junto con la historia 1.

**Independent Test**: Abrir una consola con una cuenta de prueba, retirarle el acceso por el procedimiento institucional y comprobar los tres resultados (sesión abierta terminada, ticket guardado rechazado, otro pool conservado), sin depender de ninguna otra historia.

**Acceptance Scenarios**:

1. **Given** una consola abierta por una cuenta individual, **When** infraestructura aplica el procedimiento de retiro, **Then** la sesión abierta deja de transmitir en un plazo acotado y documentado.
2. **Given** una dirección o ticket de consola guardado antes del retiro, **When** se intenta usar después, **Then** es rechazado.
3. **Given** una cuenta con acceso a dos cátedras, **When** se retira sólo una, **Then** la consola de la otra sigue disponible con una sesión nueva.
4. **Given** que el procedimiento no logra terminar sesiones o tickets, **When** se revisa el resultado, **Then** queda registrado que la consola **permanece deshabilitada** en esa instalación; no se supone una función de terminación que no exista.

---

### User Story 3 - Dejar constancia y habilitar por instalación (Priority: P2)

Administración registra la evidencia de la prueba real de revocación, completa el trámite correspondiente y la instalación queda habilitada con una configuración que enlaza esa evidencia, el clúster, su versión y las identidades con las cátedras que pueden usar. Si la evidencia, el clúster o una revisión cambian, la habilitación deja de valer.

**Why this priority**: Convierte la prueba técnica en una habilitación auditable y revocable. Depende de las historias 1 y 2 para tener qué acreditar.

**Independent Test**: Registrar la evidencia de un ensayo real, confirmar el trámite y comprobar que la compuerta pasa de cerrada a abierta; alterar la revisión de una cátedra y comprobar que se cierra otra vez.

**Acceptance Scenarios**:

1. **Given** una evidencia real de revocación con clúster y versión, **When** administración la registra y confirma el trámite, **Then** el trámite queda completado y la configuración de la instalación puede referenciarla.
2. **Given** una evidencia de otro clúster, de otra versión, simulada o anterior a la solicitud, **When** se intenta usar, **Then** la compuerta sigue cerrada.
3. **Given** una instalación habilitada, **When** cambia la revisión de una cátedra o la titularidad de una persona, **Then** esa persona deja de tener consola hasta completar un trámite nuevo.
4. **Given** una identidad de infraestructura que ya pertenece a otra persona, **When** se intenta asignarla, **Then** se rechaza: nunca se comparte una identidad individual.

---

### User Story 4 - Repetir en la universidad con un runbook (Priority: P3)

Una persona de infraestructura de la universidad sigue un runbook corto para habilitar la consola en su propio clúster: qué inventariar, cómo crear identidades y permisos por pool, cómo hacer y registrar la prueba de revocación y cómo cargar la configuración. No hay valores del laboratorio ni identidades ajenas copiadas.

**Why this priority**: Es el motivo por el que se hace en el laboratorio, pero sólo vale después de que el circuito funcione.

**Independent Test**: Un revisor que no participó lee el runbook y confirma que cada paso nombra qué dato propio de la instalación hace falta y no contiene identidades, claves ni direcciones del laboratorio.

**Acceptance Scenarios**:

1. **Given** el runbook, **When** se recorre sin acceso al laboratorio, **Then** cada paso indica a quién corresponde, qué dato institucional necesita y cómo comprobar el resultado.
2. **Given** el repositorio, **When** se buscan identidades, tokens, claves o direcciones del laboratorio o del Proxmox de otra persona, **Then** no aparece ninguno en archivos versionados.

---

### Edge Cases

- La persona tiene identidad asignada pero el servicio aún no confirmó su identidad de infraestructura (resultado incierto): la consola no se ofrece y el motivo es claro.
- El servicio se reubica o su identificador se reutiliza después de una baja: el permiso de una cátedra no alcanza al contenedor nuevo de otra.
- Dos personas de la misma cátedra: cada una con su propia identidad; retirar a una no afecta a la otra.
- El administrador del portal abre la consola de un servicio: usa su cuenta individual; el portal nunca comparte las credenciales de la API de infraestructura ni emite tickets.
- Fallo o incertidumbre del operador durante el retiro: el trámite queda abierto como fallido, se mantiene el bloqueo y no se transfiere la titularidad.
- El contenedor está en cualquier nodo del clúster (frt, pve91, otros): la consola debe abrir igual, sin que la persona elija ni conozca el nodo, y también si el nodo de entrada habitual del portal está apagado pero el clúster tiene quórum.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La consola de un servicio Linux IaaS MUST permanecer cerrada para toda persona mientras la instalación no tenga la habilitación completa (evidencia real vigente, trámite completado, identidades con alcance y revisiones actuales).
- **FR-002**: Cuando la habilitación esté completa, el sistema MUST ofrecer la consola sólo a la persona con identidad individual asignada, sobre servicios de sus propias cátedras, encendidos, con vigencia y con identidad de infraestructura confirmada, y MUST rechazar cualquier otro caso con un motivo comprensible.
- **FR-003**: El sistema MUST verificar la pertenencia del servicio en el portal antes de ofrecer el destino de consola y MUST NOT delegar esa comprobación en la infraestructura.
- **FR-004**: Cada persona con consola MUST usar una identidad individual de infraestructura propia; el sistema MUST rechazar identidades compartidas, repetidas o privilegiadas de administración.
- **FR-005**: Los permisos nativos de cada identidad MUST limitarse al contenedor y al pool de las cátedras de esa persona; no MUST permitir ver ni operar nodos, almacenamiento, otros pools ni pantallas de gestión.
- **FR-006**: El sistema MUST NOT ampliar la excepción de la constitución: la derivación cubre sólo la sesión interactiva del contenedor propio; crear, aprobar, desplegar, apagar, reiniciar, renovar y dar de baja siguen ocurriendo en el portal.
- **FR-007**: Debe existir un procedimiento institucional documentado y ensayado en el clúster real que, al retirar el acceso de una identidad, termine la sesión abierta, rechace un ticket guardado y conserve los otros pools legítimos; el ensayo MUST registrar resultados observados por separado para cada uno de esos tres puntos.
- **FR-008**: Si el ensayo no logra demostrar los tres puntos, el resultado MUST quedar documentado como "consola deshabilitada" para esa instalación y no se MUST cargar la habilitación.
- **FR-009**: La evidencia de revocación MUST identificar clúster y versión reales, MUST distinguirse de pruebas con dobles y MUST ser posterior a la solicitud del trámite; el sistema MUST rechazar evidencias de otro clúster, otra versión o simuladas.
- **FR-010**: El trámite de cambio de acceso MUST seguir el orden bloqueo → revocación acreditada → transferencia, y su estado (pendiente, fallido, completado) MUST ser visible para administración.
- **FR-011**: La habilitación MUST dejar de valer si cambian el clúster, su versión, la evidencia o la revisión de la persona o de las cátedras que la sustentan.
- **FR-012**: Las identidades, claves, tokens y direcciones del laboratorio MUST mantenerse fuera de los archivos versionados; la configuración privada de la instalación es el único lugar donde viven. No se copian identidades del entorno de otra persona.
- **FR-013**: Debe publicarse un runbook reutilizable que cubra inventario, creación de identidades y permisos por pool, ensayo de revocación, registro de evidencia, carga de la habilitación y comprobación posterior, sin valores del laboratorio.
- **FR-014**: La interfaz MUST mostrar a la persona docente el estado real de la consola (disponible, no habilitada para ella, servicio detenido, sin vigencia) sin términos técnicos de infraestructura ni exigirle conocer identificadores internos.
- **FR-015**: El sistema MUST registrar en auditoría cada habilitación, revocación y apertura de consola con persona, servicio y resultado, sin tickets ni cookies.
- **FR-016**: La persona MUST llegar a la consola de su contenedor con un único paso desde el portal, sin importar qué nodo del clúster lo aloja ni a qué nodo apunta la configuración del portal; el sistema MUST resolver el destino correcto a partir del servicio y MUST fallar con un mensaje claro, no con un destino equivocado, si el nodo no responde.

### Key Entities

- **Identidad individual de consola**: cuenta personal en la infraestructura asignada a una única persona del portal; tiene permisos sólo sobre los pools de sus cátedras.
- **Inventario institucional**: registro verificado por infraestructura de qué persona tiene qué identidad (asignada o sin identidad), con actor y referencia; ausencia de dato equivale a desconocido, no a "sin acceso".
- **Trámite de cambio de acceso**: proceso con estado que bloquea, revoca, acredita y recién entonces transfiere o libera el acceso.
- **Evidencia de revocación**: constancia canónica de una prueba real, con clúster, versión, identidad, alcances, revisión y fecha.
- **Habilitación de instalación**: configuración privada que enlaza evidencia, clúster, versión e identidades con las cátedras autorizadas.
- **Servicio Linux IaaS**: contenedor con identidad de infraestructura confirmada y perteneciente al pool de su cátedra.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona de cátedra con identidad asignada abre la terminal de su Linux IaaS en el navegador en menos de 1 minuto desde que pulsa la consola, sin ayuda de administración.
- **SC-002**: El 100 % de los intentos de abrir la consola de un servicio de otra cátedra, de una persona sin identidad asignada o de un servicio detenido se rechazan antes de ofrecer destino alguno (verificado con al menos 3 casos por categoría).
- **SC-003**: Tras aplicar el procedimiento de retiro, la sesión abierta deja de transmitir y un ticket guardado es rechazado dentro del plazo que el runbook declara, en el 100 % de los ensayos reales, y la consola del otro pool de esa persona sigue funcionando.
- **SC-004**: Con la cuenta individual, la persona no puede ver ni operar ninguna otra pantalla de gestión de la infraestructura (0 pantallas o recursos ajenos accesibles en la comprobación).
- **SC-005**: Una persona de infraestructura que no participó puede completar el runbook en un clúster de prueba y obtener la habilitación sin consultar a quien lo escribió.
- **SC-006**: Una búsqueda en archivos versionados no encuentra ninguna identidad, token, clave ni dirección del laboratorio.
- **SC-007**: La consola abre con el mismo procedimiento para contenedores alojados en cada uno de los dos nodos del laboratorio (frt y pve91), verificado con al menos un servicio por nodo.

## Assumptions

- Alcance de la instalación: el laboratorio frt/pve91 con la cátedra 3 y la cuenta de Ivan como primera persona habilitada; las demás cátedras se habilitan repitiendo el mismo procedimiento.
- Sólo servicios Linux IaaS (contenedores); las aplicaciones OCI (MariaDB, nginx) y el gateway de aplicaciones quedan fuera.
- La consola abre el destino de consola del contenedor dentro de la interfaz de la infraestructura, como ya define la constitución; no se construye un terminal propio en el portal ni se reemplaza el acceso SSH de la feature 017.
- Las identidades de consola se crean en un dominio de autenticación propio de la instalación, distinto del de administración; el portal no crea ni modifica identidades ni permisos de infraestructura: lo hace el operador institucional.
- La persona operadora institucional es Ivan en el laboratorio; en la universidad lo será quien administre el clúster.
- Se reutiliza el contrato implementado en la spec 009 (compuerta, inventario, trámites, evidencia tipada); esta feature lo habilita y prueba en real, y sólo corrige lo que el ensayo demuestre que falta.
- La consola nativa depende de que la infraestructura ofrezca un modo de terminar sesiones y tickets; si el ensayo demuestra que no existe, la entrega de esta feature es el diagnóstico y la consola queda cerrada (FR-008).
- Dependencias: laboratorio encendido con quórum y almacenamiento compartido, un Linux IaaS desplegado por el portal y acceso de administración a los nodos para el operador.
