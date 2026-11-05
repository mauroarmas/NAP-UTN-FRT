# Feature Specification: Desplegar servicios universitarios desde imágenes y biblioteca

**Feature Branch**: `011-desplegar-servicios-universitarios`

**Feature Directory**: `specs/011-desplegar-servicios-universitarios`

**Created**: 2026-10-26

**Status**: En implementación — alcance reducido el 27/10/2026

**Input**: Decisión de Mauro del 27/10/2026: Docker Hub reemplaza a Community Scripts como biblioteca. Se conservan imágenes Docker propias en registries autorizados, un motor OCI común, instancias independientes por cátedra y consola administrativa de lectura. Se retira Community Scripts para acelerar la entrega.

**Alcance vigente**: dos entradas de descubrimiento (Docker Hub e imagen propia), un solo origen de ejecución `imagen_docker`. IaaS Ubuntu/Debian y Draw.io histórico se conservan. No se implementan scripts Community, Core, perfiles por instalador ni sus pilotos. Ver [cambio de alcance](cambio-alcance-oci.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ofrecer una aplicación propia desde su imagen (Priority: P1)

Como administrador quiero agregar una aplicación indicando su imagen Docker y los datos básicos que me entrega quien la desarrolló, para que una cátedra pueda solicitar software propio mediante el mismo motor usado por la biblioteca Docker Hub.

**Why this priority**: Proporciona una vía general de despliegue y evita que NAP quede limitado a aplicaciones con un instalador programado individualmente.

**Independent Test**: Registrar una imagen de una aplicación universitaria, comprobar su aparición en el catálogo y desplegarla mediante un pedido de prueba, sin modificar el programa de NAP para esa aplicación.

**Acceptance Scenarios**:

1. **Given** administración en Catálogo, **When** elige «Imagen propia», **Then** encuentra un formulario con nombre, referencia de la imagen y puerto principal; descripción y configuración adicional sólo se completan cuando hacen falta. No se solicitan comandos, identificadores de infraestructura ni documentos técnicos.
2. **Given** una imagen accesible y una configuración válida, **When** agrega el servicio, **Then** NAP registra una oferta reutilizable y la hace seleccionable por las cátedras, sin crear una instancia ni reservar capacidad por esa acción.
3. **Given** una referencia inexistente, una imagen inaccesible o requisitos incompatibles, **When** se comprueba el alta, **Then** se explica el impedimento, se conservan los datos ingresados y no se anuncia una oferta utilizable.
4. **Given** una imagen en un repositorio institucional privado ya configurado, **When** se agrega, **Then** NAP utiliza el acceso previamente preparado sin pedir al administrador credenciales de infraestructura en cada alta ni mostrarlas en el registro.
5. **Given** una segunda aplicación que cumple el mismo formato, **When** se registra y despliega, **Then** se utiliza el mismo recorrido sin incorporar otro instalador específico al programa de NAP.

---

### User Story 2 - Buscar en Docker Hub y agregar al catálogo (Priority: P1)

Como administrador quiero buscar una imagen en Docker Hub y agregarla al catálogo mediante el mismo formulario de imágenes propias, para ofrecer aplicaciones sin copiar comandos ni preparar instaladores distintos.

**Why this priority**: Reutiliza el motor OCI de US1; Docker Hub es la biblioteca del producto, no otro mecanismo de instalación.

**Independent Test**: Buscar `traefik/whoami`, seleccionar una imagen compatible, completar sólo los datos necesarios, agregarla sin CT/reserva y entregar una instancia desde un pedido aprobado.

**Acceptance Scenarios**:

1. **Given** administración buscando por nombre, **When** consulta Docker Hub, **Then** ve repositorio, descripción/procedencia disponibles y distintivos del proveedor cuando existan; aparecer en resultados no equivale a compatibilidad comprobada.
2. **Given** una imagen seleccionada, **When** pulsa «Agregar servicio», **Then** NAP abre el mismo formulario que para imagen propia, precarga los datos conocidos y solicita puerto/persistencia/configuración sólo cuando no pueda resolverlos. El servidor valida imagen/plataforma/perfil y congela el digest.
3. **Given** una configuración válida, **When** agrega, **Then** aparece «Disponible para solicitar», sin creación de LXC, reserva ni otro paso de preparar/publicar; al desplegar el pedido se usa exactamente el motor Docker de US1.
4. **Given** una imagen inaccesible, incompatible, fuera de Medium o que requiere varios servicios/privilegios no admitidos, **When** se valida, **Then** se explica el motivo y se conservan los datos; NAP no promete ejecutar cualquier imagen encontrada.
5. **Given** fallo o limitación de la búsqueda externa, **When** se consulta, **Then** se distingue de cero resultados y se ofrece reintento o ingresar la referencia manualmente. El catálogo interno sigue disponible. No se agrega un sistema nuevo de caché, espejo o cuentas para la búsqueda.
6. **Given** categorías o filtros del proveedor no disponibles mediante la API elegida, **When** se abre la biblioteca, **Then** se mantiene búsqueda por nombre sin inventar categorías ni bloquear el formulario; filtros adicionales no son condición de entrega.

---

### User Story 3 - Solicitar y recibir una instancia por cátedra (Priority: P1)

Como responsable de cátedra quiero pedir una aplicación por su nombre, propósito y fechas; como administrador quiero resolver el pedido y que NAP entregue la instancia correspondiente sin administrar manualmente Proxmox.

**Why this priority**: Conecta las dos entradas de imágenes con el propósito académico, el aislamiento y el control de capacidad que ya existen.

**Independent Test**: Dos cátedras solicitan una misma oferta, administración aprueba y cada una recibe su instancia, acceso y datos independientes; demostrar la selección desde Docker Hub y la referencia propia sin duplicar la batería del motor.

**Acceptance Scenarios**:

1. **Given** ofertas agregadas desde Docker Hub o mediante referencia propia, **When** la cátedra crea un pedido, **Then** puede elegirlas como los demás servicios, indicar justificación pedagógica y fechas, sin escoger hardware ni conocer el procedimiento de instalación. Se conserva «Otro».
2. **Given** software propio aún no ofrecido, **When** la cátedra lo pide como «Otro», **Then** puede aportar opcionalmente la referencia de su imagen y las instrucciones necesarias de uso; administración revisa esos datos antes de convertirlos en una oferta. Esa referencia no autoriza por sí misma una instalación.
3. **Given** un pedido completo y capacidad suficiente, **When** administración aprueba con Small o Medium, **Then** se reserva la capacidad de forma indivisible y se inicia o programa el despliegue según las fechas y la acción elegida; una aprobación futura no crea un recurso anticipadamente.
4. **Given** capacidad insuficiente o dos aprobaciones simultáneas, **When** se resuelven los pedidos, **Then** no se compromete capacidad dos veces ni se despliega por fuera de la decisión autorizada; se informa el conflicto y se conserva el pedido.
5. **Given** una instalación terminada y su comprobación de disponibilidad satisfactoria, **When** NAP confirma la entrega, **Then** actualiza el pedido mediante su ciclo de vida habitual, registra el resultado, avisa por el canal existente del portal y permite consultar el acceso desde Servicios.
6. **Given** un pedido incompleto, **When** administración pide aclaración, rechaza o la cátedra reenvía, **Then** se conserva el flujo existente y sus avisos, sin reservar recursos ni iniciar instalaciones prematuras.
7. **Given** un cambio en una oferta o en su fuente después de aprobar un pedido, **When** se despliega, **Then** no se sustituye silenciosamente la configuración o versión decidida. Se conserva la decisión o se informa el impedimento para resolverla.

---

### User Story 4 - Entender el avance y abrir una consola de lectura (Priority: P1)

Como administrador quiero ver qué está haciendo NAP durante los despliegues del motor Docker común, sin tener que usar una terminal ni dejar abierta la pantalla para que el trabajo continúe.

**Why this priority**: Evita la sensación de bloqueo, permite diagnosticar errores y mantiene el recorrido habitual comprensible.

**Independent Test**: Ejecutar operaciones de dos imágenes distintas, abrir su consola, cerrar la pantalla durante el proceso y volver a abrirla, comprobando que el trabajo y el registro continúan sin reiniciar la instalación.

**Acceptance Scenarios**:

1. **Given** un despliegue admitido, **When** se consulta su detalle, **Then** se muestra su etapa real, el último avance y una acción «Ver consola». Se distinguen espera, trabajo en curso, interrupción de la consulta, fallo y finalización; no se inventan porcentajes ni tiempos restantes.
2. **Given** administración que abre la consola, **When** el proceso produce salida, **Then** la ve como texto de sólo lectura con fondo negro, letras blancas y fuente monoespaciada, diferenciada del resto de la interfaz. No hay entrada de comandos.
3. **Given** descarga, instalación, configuración o arranque en curso, **When** hay nuevos mensajes, **Then** se incorporan en orden con identificación de la operación y su intento. El seguimiento automático puede pausarse al revisar mensajes anteriores sin perder la salida nueva.
4. **Given** cierre de pestaña, recarga, desconexión o reinicio del procesamiento, **When** se recupera la consulta, **Then** se presenta el estado persistido y los mensajes retenidos, sin iniciar otra operación ni duplicar fragmentos del registro.
5. **Given** un proceso silencioso o una consulta de registro que falla, **When** administración observa el panel, **Then** se indica que no hubo mensajes recientes o que no se pudo actualizar; eso no se presenta como instalación fallida ni como éxito.
6. **Given** un registro con credenciales conocidas o identificadas como sensibles por el instalador, **When** se almacena, transmite, muestra, copia o descarga, **Then** esos valores están ocultos y los mensajes no se interpretan como instrucciones ejecutables.
7. **Given** administración ante una operación finalizada, **When** vuelve a consultarla dentro del período de conservación, **Then** puede leer, copiar o descargar su registro depurado. La cátedra ve el avance y resultado comprensibles, sin esta consola técnica.
8. **Given** un registro que supera el límite retenido o cuya conservación vence, **When** se consulta, **Then** se informa el recorte o vencimiento y siguen disponibles el resultado final, el motivo de fallo y el historial del pedido; no se presenta una consola vacía como si la operación no hubiera ocurrido.

---

### User Story 5 - Recuperar fallos y conservar el servicio (Priority: P1)

Como administrador quiero saber qué ocurrió, reintentar cuando corresponda y operar los servicios basados en imágenes sin duplicar recursos, perder datos o alterar servicios de otra cátedra.

**Why this priority**: Los recursos del laboratorio son escasos y la instalación puede interrumpirse; un camino feliz aislado no constituye un servicio administrable.

**Independent Test**: Interrumpir una instalación tras crear el recurso, recuperar la operación y verificar su identidad; después detener, iniciar, reiniciar y eliminar una instancia con datos de prueba.

**Acceptance Scenarios**:

1. **Given** un recurso creado pero una respuesta perdida, **When** NAP recupera o reintenta la operación, **Then** comprueba qué existe antes de crear otro, conserva su relación con el pedido y muestra la incertidumbre mientras no pueda confirmar el resultado.
2. **Given** un fallo confirmado, **When** administración consulta y reintenta, **Then** ve una explicación breve, puede abrir el registro y continúa o inicia un intento identificado según el estado real, sin multiplicar contenedores ni reservas. El mismo pedido conserva sus credenciales de aplicación, incluso si debe recrearse el recurso tras confirmar su ausencia; un nuevo pedido de alta recibe credenciales propias.
3. **Given** una instancia con datos persistentes declarados, **When** se detiene, inicia o reinicia, **Then** conserva esos datos y no reinstala la aplicación ni cambia sus credenciales de manera inesperada.
4. **Given** una baja autorizada o una limpieza de instalación fallida, **When** se ejecuta, **Then** se eliminan únicamente recursos cuya pertenencia al pedido esté comprobada y se libera capacidad sólo tras confirmar la ausencia. La baja que destruye datos se advierte antes de confirmarse.
5. **Given** una eliminación o comprobación de identidad fallida, **When** no se puede asegurar la ausencia, **Then** se muestra limpieza pendiente, se conserva la contabilización necesaria y no se anuncia capacidad libre ficticia.
6. **Given** una oferta retirada, **When** se revisan sus instancias existentes, **Then** continúan administrándose con sus datos e historia; la retirada sólo impide nuevos pedidos de esa oferta.
7. **Given** un servicio que llega al fin de su vigencia, **When** actúan las políticas académicas existentes, **Then** mantiene avisos, pausas y renovación previstos; no se agrega una eliminación silenciosa de datos ni un plazo de ensayo de 24 horas.
8. **Given** pedidos y servicios existentes de Ubuntu, Debian y Draw.io, **When** se incorpora esta funcionalidad, **Then** siguen consultándose y operándose con sus accesos e historial, sin recrearlos. Las decisiones nuevas distinguen a la persona o al sistema que las tomó y conservan su atribución a la cátedra.

### Edge Cases

- La imagen cambia o desaparece entre el alta, la aprobación y el despliegue: no sustituirla en silencio ni perder la decisión histórica.
- El instalador intenta pedir una respuesta interactiva o crear un recurso distinto del autorizado: no abrir una terminal de escritura; detener o rechazar la operación con estado explícito y recursos identificados.
- Dos clics, recargas o reintentos concurrentes sobre un mismo pedido: una sola operación efectiva y un único compromiso por recurso.
- El proceso termina correctamente pero la aplicación no queda accesible: no entregar basándose sólo en que existe un contenedor o en el mensaje de éxito del instalador.
- La creación del contenedor falla antes de arrancar el instalador: conservar en la misma consola los hitos y el error seguro de creación, sin exigir que exista un trabajo del instalador.
- Se pierde la sesión o cambia el rol mientras la consola está abierta: no permitir nuevas consultas o descargas sin autorización vigente.
- Un registro contiene contraseñas generadas, secuencias de terminal, contenido que aparenta ser una página o una salida muy extensa: depurar antes de exponerlo y señalar cualquier recorte.
- Los recursos mínimos exceden Medium o la aplicación exige un entorno fuera del alcance: explicarlo antes de ofrecerla, sin reducir sus mínimos ni agregar otro tamaño.
- Falta la preparación de red o acceso del laboratorio: informar qué debe completar el responsable técnico, sin pedir parámetros internos por cada alta y sin atribuir una prueba local a la red universitaria.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: NAP MUST ofrecer en el catálogo administrativo los caminos «Docker Hub» e «Imagen propia», conservando los entornos Linux IaaS existentes. El catálogo docente muestra ofertas solicitables, no herramientas de administración.
- **FR-002**: El alta habitual MUST permitir elegir, completar sólo datos necesarios y agregar. MUST NOT incluir listas «Guardadas», pasos manuales de preparar/publicar, formularios de evidencia, hashes, UUID, versiones internas ni comandos para copiar en el nodo.
- **FR-003**: Una oferta nueva MUST representar una configuración reutilizable de despliegue. Agregarla o retirarla MUST NOT reservar capacidad ni mantener un contenedor académico encendido por anticipado; una ficha descubierta sin instalación compatible MUST NOT presentarse como oferta desplegable.
- **FR-004**: El alta de una aplicación propia MUST aceptar una imagen Docker, un nombre y su puerto principal; descripción, configuración de la aplicación, valores sensibles y almacenamiento persistente MUST ser opcionales salvo que la aplicación los necesite. MUST poder utilizar repositorios públicos o institucionales previamente configurados.
- **FR-005**: El camino de imágenes MUST desplegar aplicaciones distintas que cumplen el mismo formato mediante configuración, sin exigir código o un instalador nuevo dentro de NAP por cada aplicación.
- **FR-006**: La biblioteca MUST buscar imágenes por nombre en Docker Hub, mostrar procedencia y datos disponibles y distinguir fallo externo de cero resultados; el catálogo interno y la entrada manual de referencia MUST seguir disponibles. Categorías/filtros sólo si la API utilizada los ofrece; no son condición de aceptación.
- **FR-007**: Una imagen seleccionada desde Docker Hub MUST pasar por la misma validación, configuración inmutable y motor OCI que una referencia propia. Su procedencia MUST NOT crear otra estrategia, contrato de despliegue, reserva o instalador específico. Community Scripts queda fuera de esta feature.
- **FR-008**: La compatibilidad MUST comprobar que la instalación puede completarse sin interacción manual, dentro de Small o Medium y sin cambios generales del nodo o permisos de aplicación fuera de lo admitido. Los casos no soportados MUST explicar el motivo antes de habilitar su oferta; ampliar configuraciones compatibles MUST NOT exigir reescribir un instalador completo por aplicación.
- **FR-009**: El despliegue MUST utilizar fuentes y configuraciones identificadas, mantener la decisión de cada aprobación y rechazar una sustitución no autorizada. Modificar una oferta MUST NOT actualizar instancias existentes ni decisiones aprobadas de forma automática.
- **FR-010**: El responsable de cátedra MUST seguir solicitando aplicación, propósito pedagógico y fechas; «Otro» MUST permitir describir software propio y aportar opcionalmente su referencia de imagen. Sólo administración puede transformar esos datos en una oferta y decidir la aprobación.
- **FR-011**: Administración MUST poder aprobar, rechazar o pedir aclaración con los avisos existentes. Los dos tamaños continúan siendo Small —1 vCPU, 512 MB de RAM, 4 GB de disco— y Medium —2 vCPU, 1024 MB de RAM, 8 GB de disco—, respetando los mínimos de la aplicación y sin cuotas anticipadas por cátedra.
- **FR-012**: Aprobar MUST validar capacidad y crear su reserva de forma indivisible. El despliegue MUST respetar esa asignación, la vigencia aprobada y la decisión de iniciarlo; una fecha futura MUST mantenerlo programado sin creación anticipada.
- **FR-013**: Cada instancia MUST pertenecer a su cátedra y a su pedido y tener recursos, acceso, datos y secretos independientes. Una aplicación MUST NOT obtener acceso administrativo al nodo, credenciales del portal ni información de otras cátedras.
- **FR-014**: Cualquier creación o reintento MUST poder identificar el recurso previsto y comprobar lo ya existente antes de crear otro. La recuperación de una respuesta perdida MUST NOT atribuirse recursos ajenos ni duplicar capacidad comprometida.
- **FR-015**: Una instalación MUST continuar independientemente de la pestaña que la inició y recuperar su estado después de una interrupción del procesamiento, distinguiendo resultado confirmado, fallo e incertidumbre.
- **FR-016**: NAP MUST comprobar el arranque y la disponibilidad por el mecanismo de acceso declarado antes de confirmar la entrega; MUST registrar qué comprobó, actualizar el estado central del pedido y emitir el aviso habitual sin exigir evidencias manuales al administrador. Una comprobación básica MUST NOT presentarse como prueba completa de todas las funciones del software.
- **FR-017**: El acceso de una instancia MUST ofrecerse sólo a administración y al responsable vigente de su cátedra, respetando la sesión y las condiciones de operación. Se conservan los mecanismos de autenticación propios de cada aplicación y el acceso con NAP ya implementado en Draw.io; no se promete inicio de sesión único para cualquier software.
- **FR-018**: Los despliegues MUST mostrar etapas reales y un resumen entendible desde el pedido y el servicio, incluyendo la última actualización. MUST NOT mostrar éxito antes de confirmarlo ni inventar porcentajes, tiempos de finalización o actividad de un proceso silencioso.
- **FR-019**: Administración MUST disponer de «Ver consola» para las operaciones de descarga, creación, instalación, configuración y arranque, incluidos los mensajes iniciales de la aplicación disponibles en cada camino. MUST incluir los hitos seguros del portal aunque la creación falle antes de iniciar el instalador. La consola MUST ser de sólo lectura, con fondo negro y texto blanco monoespaciado; MUST NOT habilitar entrada de comandos ni respuestas a preguntas del instalador.
- **FR-020**: Los mensajes MUST conservar su orden de captura por productor y el orden causal de los hitos entre portal e instalador, y asociarse a una operación e intento, poder recuperarse al volver a abrir la pantalla y permitir seguimiento automático sin impedir revisar mensajes anteriores. Una reconexión MUST NOT duplicar fragmentos ya recibidos ni simular que el proceso volvió a empezar.
- **FR-021**: La consola MUST distinguir un fallo al consultar el registro de un fallo de instalación, mostrar si no hay salida reciente y mantener el último estado confirmado. MUST permitir copiar o descargar deliberadamente el registro retenido y depurado.
- **FR-022**: La salida MUST tratarse como texto, sin ejecutar instrucciones ni contenido de presentación recibido. Las contraseñas, claves y tokens gestionados por NAP o identificados como sensibles por el instalador MUST ocultarse antes de persistir o exponer mensajes, incluidas copia y descarga. El registro MUST NOT almacenar credenciales de sesión ni de repositorios privados.
- **FR-023**: La consola técnica y sus descargas MUST exigir autorización administrativa vigente durante la consulta; las cátedras conservan avance y resultado comprensibles de lo propio. Revocar el acceso, desactivar la cuenta o cerrar la sesión MUST impedir nuevas lecturas; la consola no sustituye ni amplía la consola interactiva IaaS ya existente.
- **FR-024**: NAP MUST conservar registros operativos depurados durante 30 días, con un máximo de 10 MB por operación contando sus intentos. Cualquier recorte o vencimiento MUST indicarse; el límite MUST NOT ocultar el estado final ni eliminar el historial académico, la decisión, el motivo de fallo o la identificación de recursos.
- **FR-025**: Un fallo MUST dejar explicación breve, registro consultable y acciones coherentes con el estado real. Un reintento MUST conservar los intentos anteriores e identificar el nuevo; MUST NOT repetir ciegamente una creación con resultado desconocido. MUST conservar valores y referencias de secretos de aplicación del mismo pedido, incluso al recrear un recurso cuya ausencia se confirmó; un nuevo pedido de alta MUST recibir secretos propios. Esto no reutiliza la identidad ni las claves de infraestructura de un recurso retirado.
- **FR-026**: Detener, iniciar y reiniciar MUST conservar la configuración y el almacenamiento persistente declarado, sin reinstalar ni regenerar credenciales inesperadamente. La baja MUST advertir la eliminación de datos y conservar la historia del pedido y del servicio.
- **FR-027**: La limpieza MUST actuar sólo sobre recursos cuya pertenencia esté comprobada y confirmar la ausencia antes de liberar su capacidad. Si falla, MUST quedar visible y contabilizada como pendiente, sin afectar otras instancias.
- **FR-028**: Las instancias basadas en imágenes MUST integrarse con las vigencias, renovaciones, pausas, avisos y retirada de ofertas ya existentes. La retirada MUST impedir nuevos pedidos sin alterar instancias aprobadas; MUST NOT agregarse vencimiento de ofertas ni ensayos de 24 horas.
- **FR-029**: La preparación de infraestructura, red y accesos MUST realizarse una vez por el responsable técnico y reutilizarse. Su falta MUST expresarse como impedimento concreto; MUST NOT anunciar compatibilidad con un entorno universitario no configurado ni exigir sus identificadores internos en cada alta.
- **FR-030**: La incorporación de los nuevos caminos MUST conservar usuarios, cátedras, pedidos, servicios y sus historiales, las bases Linux ya ofrecidas y el despliegue y acceso de Draw.io ya operativos. Una actualización de esta funcionalidad MUST NOT obligar a recrear servicios existentes.

### Key Entities *(include if feature involves data)*

- **Oferta de servicio**: nombre, descripción, modelo IaaS/PaaS/SaaS, origen de instalación, tamaños admitidos y disponibilidad para nuevos pedidos. Publicarla no crea una instancia.
- **Configuración reutilizable de despliegue**: imagen OCI identificada y datos de procedencia de la biblioteca cuando correspondan, versión efectiva, requisitos, puerto y forma de acceso, configuración necesaria y necesidades de persistencia. Las referencias privadas se mantienen protegidas y fuera de la consola.
- **Solicitud y decisión**: cátedra, solicitante, justificación, vigencia y resolución administrativa con la configuración aprobada; conserva las reservas y transiciones históricas existentes.
- **Instancia de servicio**: recurso concreto de una cátedra, configuración efectiva, disponibilidad, datos persistentes y acceso autorizado. No se comparte entre pedidos distintos por reutilizar una oferta.
- **Operación e intento**: acción de despliegue o recuperación, estado, etapa, último avance, recursos vinculados y resultado comprobado; permite distinguir repetición de consulta y nuevo intento.
- **Registro de consola**: mensajes depurados y ordenados de una operación, con su período de conservación y cualquier recorte señalado. Es un registro operativo distinto del historial académico permanente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un administrador con la información de la aplicación disponible completa el alta por cada entrada (Docker Hub o referencia propia) en un máximo de 3 minutos de interacción, sin terminal, ayuda técnica en ese recorrido ni pasos manuales de preparación o publicación; se comprueba con un administrador del proyecto, sin exigir un grupo de participantes.
- **SC-002**: Se demuestran dos aplicaciones distintas mediante un único motor: una imagen encontrada en Docker Hub (whoami) y una imagen universitaria propia (campus-demo). Cada demostración termina con acceso utilizable y resultado registrado; campus-demo acredita persistencia y se prueba descarga desde registry privado. No se exigen MariaDB/Caddy como pilotos ni cuatro aplicaciones.
- **SC-003**: Dos cátedras reciben instancias de una misma oferta sin compartir datos o credenciales, y detener o eliminar una no altera la otra. Se verifica con dos imágenes diferentes del mismo motor y el 100 % de los intentos de acceso ajeno del ensayo resulta rechazado.
- **SC-004**: En un ensayo de dos operaciones simultáneas con conectividad disponible, al menos el 95 % de los mensajes producidos aparece en la consola en un máximo de 5 segundos desde su captura; abrir la consola o recuperar un registro retenido tarda como máximo 3 segundos. No se exige que el software externo produzca mensajes con una frecuencia determinada.
- **SC-005**: Tras cerrar y reabrir la pantalla y tras interrumpir el procesamiento en ensayos de las dos imágenes de aceptación, administración recupera estado e intentos sin duplicar la instancia ni el compromiso de capacidad; el pedido no se anuncia como entregado mientras su resultado siga incierto.
- **SC-006**: En los ensayos de fallo, reintento y baja del motor común, todo recurso creado queda vinculado a su pedido y al finalizar queda operativo o con limpieza pendiente explícita; nunca se anuncia como libre capacidad correspondiente a un recurso cuya ausencia no se confirmó.
- **SC-007**: En las comprobaciones de consola, ninguna credencial de prueba conocida o identificada como sensible aparece en almacenamiento de registros, pantalla, copia o descarga. Las salidas de prueba con contenido de terminal o de página se muestran como texto, sin ejecutar acciones, y una sesión sin autorización vigente no obtiene nuevos mensajes.
- **SC-008**: Una cátedra puede solicitar una oferta de Docker Hub o referencia propia completando únicamente aplicación, propósito y fechas en un máximo de 2 minutos de interacción; opcionalmente puede describir software propio mediante «Otro», sin gestionar infraestructura.
- **SC-009**: Las pruebas de regresión conservan los pedidos y servicios existentes, los recorridos de Ubuntu/Debian y el uso del Draw.io actual sin recrear sus instancias. La entrega distingue claramente comprobaciones simuladas, laboratorio real y preparación pendiente del entorno universitario.

## Assumptions

- **Objetivo y actores**: NAP es una pequeña nube universitaria. Administración gestiona el catálogo y resuelve pedidos; las cátedras solicitan y usan lo autorizado. No se agrega un rol nuevo ni se delega administración de infraestructura en las cátedras.
- **Decisión de producto vigente**: en esta conversación se acordó guardar en el catálogo cómo desplegar la aplicación e instalarla al ejecutar el pedido aprobado. Para estos nuevos caminos, «elegir → agregar → disponible» significa oferta disponible para solicitar; no afirma que ya exista una instancia funcional. La comprobación real de entrega ocurre durante el despliegue.
- **Alineación normativa**: el Principio VII de la constitución 4.2.0 ya distingue oferta solicitable e instancia instalada, según esta decisión del usuario. Se mantienen automatización, autorización, aislamiento y ausencia de publicación o pruebas manuales; no se reabren los demás principios.
- **Alcance inicial de imágenes**: una imagen ya construida por aplicación, un puerto principal de acceso web o de conexión y los datos persistentes que declare. No se construye software desde su código fuente ni se agregan conjuntos de varios servicios coordinados. El formato solicitado por el usuario es Docker; no se elige aquí cómo ejecutarlo internamente.
- **Acceso a imágenes privadas**: se admiten repositorios institucionales con acceso configurado una vez por el responsable técnico. No se incorpora un gestor general de repositorios, cuentas o certificados en el formulario habitual.
- **Compatibilidad de biblioteca**: Docker Hub es descubrimiento, no garantía de instalación. Sólo se ofrecen imágenes accesibles para la plataforma y perfil Docker admitidos, con configuración resoluble y mínimos reales. Una imagen OCI no sustituye las plantillas LXC de IaaS. No se agregan builds desde código, Docker Compose ni conjuntos de servicios coordinados.
- **Reutilización**: se reutilizan configuración e instrucciones identificadas; eso no obliga a clonar una instalación ya configurada con credenciales compartidas. Los artefactos reutilizables existentes de Draw.io se conservan y no se vuelve a exigir su preparación por cada pedido.
- **Dependencias externas**: un despliegue nuevo puede necesitar descargar imágenes y paquetes de la plataforma Docker. Una oferta guardada no garantiza instalación sin conexión. Esto no revoca el comportamiento ya comprobado de los artefactos de Draw.io; cualquier dependencia inaccesible debe producir un resultado explícito y recuperable.
- **Configuración inicial**: nodo, red, nombres, acceso y capacidad del laboratorio deben prepararse una vez. El clúster y la red de la universidad no se asumen disponibles ni equivalentes a la VM local. La planificación debe verificar que el mecanismo elegido permite controlar identidad y recursos antes de habilitar aplicaciones como compatibles.
- **Registros y datos**: 30 días y 10 MB por operación son límites iniciales de registros operativos, no de datos académicos ni de vigencia del servicio. Detención o vencimiento académico no autorizan una baja destructiva nueva; se mantienen las políticas de acceso y eliminación explícita existentes.
- **Compatibilidad histórica**: esta feature amplía y simplifica la 010 para los nuevos caminos; no exige nuevas pantallas de definiciones/perfiles ni traslada a administración la gestión de versiones técnicas. Tampoco incorpora inicio de sesión único universal, terminal interactiva de instalación, observabilidad continua de todas las aplicaciones o migración automática de servicios existentes.
- **Tecnología solicitada frente a diseño interno**: Docker/OCI, Docker Hub, LXC y Proxmox nombran formatos, fuentes y restricciones de integración ya elegidos por el usuario. El mecanismo de ejecución, almacenamiento, entrega de mensajes y estructura del programa se decidirá en el plan; no forma parte de esta especificación funcional.
