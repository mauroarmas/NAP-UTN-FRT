# Feature Specification: Remediación de hallazgos y cierre funcional de la práctica

**Feature Branch**: `009-remediar-hallazgos-cierre`

**Feature Directory**: `specs/009-remediar-hallazgos-cierre`

**Created**: 2026-10-18

**Status**: Specified — sesión de aclaración completada; cuatro respuestas incorporadas y lista para planificación.

**Input**: User description: "Llevemos adelante una especificación para encarar estos hallazgos para su solución, consultame si tienes dudas". Fuente de alcance: [análisis del proyecto del 18 de octubre de 2026](../../docs/analisis-proyecto-2026-10-18.md), aceptado por el usuario.

## Clarifications

### Session 2026-10-18

- Q: ¿Cómo se recupera el segundo factor si se pierde el teléfono? → A: Opción A: códigos de recuperación de un solo uso y recuperación asistida si también se pierden. El usuario aclara que el 2FA es voluntario para todos los usuarios y solo se exige cuando la cuenta lo tiene activado.
- Q: ¿Qué alcance tendrán los respaldos de PostgreSQL y BookStack de las cátedras? → A: Opción A: respaldo propio del portal y procedimiento documentado y probado de respaldo/restauración de las aplicaciones mediante herramientas externas al portal, coordinadas con infraestructura. No se incorpora un módulo de gestión de respaldos de aplicaciones al portal.
- Q: Si una renovación comienza semanas después del vencimiento actual, ¿qué ocurre durante el intervalo? → A: Opción A: pausar al terminar el período actual, conservar datos y habilitar reactivación desde el inicio del período renovado, verificando capacidad. La renovación no autoriza el uso del intervalo intermedio.
- Q: Para la demostración de BookStack, ¿cómo accederán los alumnos a la lectura? → A: Opción A: cuentas individuales de lectura, gestionadas por el docente dentro de su instancia de BookStack. Los alumnos permanecen fuera del portal NAP y no reciben cuentas ni roles en él.

### Session 2026-10-21

- Q: ¿Se necesitan cinco personas para validar el envío de pedidos? → A: El usuario indica que sólo una persona, el responsable de cátedra, hará el pedido. SC-007 se valida con ese responsable y su feedback; no se exige reunir cinco participantes. El plan individual prevé uso simulado de una cátedra de prueba. Esta aclaración no cambia el aislamiento entre cátedras ni las diez sesiones automáticas del ensayo de carga.

## User Scenarios & Testing *(mandatory)*

Las prioridades ordenan la implementación. Todas las historias forman parte del cierre; P2 no significa opcional. Cada historia puede probarse con cuentas y recursos de referencia preparados, independientemente de las demás. Las reglas se aplican por cualquier vía de acceso, aunque no exista un botón que permita solicitar la acción.

### User Story 1 - Operar únicamente sobre cátedras autorizadas (Priority: P1)

Como responsable de una o varias cátedras, quiero que mis pedidos, servicios, accesos y métricas solo puedan ser consultados y modificados por personas autorizadas.

**Why this priority**: El aislamiento es condición previa al uso compartido del portal; se encontraron operaciones y lecturas sobre recursos ajenos.

**Independent Test**: Preparar dos titulares distintos y una persona con varias cátedras; consultar y operar recursos propios y ajenos, tanto desde el portal como mediante solicitudes directas.

**Acceptance Scenarios**:

1. **Given** dos responsables distintos, **When** uno intenta consultar o modificar pedidos, historial, servicios, accesos o métricas del otro, **Then** se deniega el acceso sin devolver contenido ni producir cambios.
2. **Given** un pedido que requiere aclaración, **When** su titular actual responde, **Then** puede reenviar únicamente el pedido propio a solicitado, sin hardware ni decisión de aprobación; un pedido ajeno o la cancelación docente se deniegan sin cambios.
3. **Given** una persona con varias cátedras, **When** solicita y consulta recursos, **Then** puede operar en todas sus cátedras actuales sin incluir las ajenas.
4. **Given** una reasignación de titularidad, retiro, desactivación o cambio de rol que quite acceso, **When** administración lo solicita, **Then** se bloquean inmediatamente en el portal las acciones afectadas y el cambio queda pendiente hasta acreditar la revocación nativa, incluida una consola ya abierta; después, ni la sesión anterior ni una URL guardada acceden al recurso retirado, se conserva el acceso legítimo a otras cátedras y el historial académico. Si infraestructura falla, el cambio no se anuncia completado ni se entrega al nuevo titular.
5. **Given** una persona con rol cátedra que altera sus datos locales de sesión, **When** intenta aprobar, rechazar, asignar recursos o administrar cuentas, **Then** el sistema rechaza la operación.

---

### User Story 2 - Completar el acceso y conservar administración (Priority: P1)

Como usuario quiero operar con mi contraseña definitiva y decidir si activo un segundo factor; si lo activo, quiero que se exija y pueda recuperarlo de forma segura. Como administrador quiero que el alta inicial y los cambios de cuentas no permitan perder el control del portal.

**Why this priority**: El segundo factor elegido por la persona y el cambio inicial deben ser protecciones efectivas; no activar 2FA no debe impedir operar. Eliminar al último administrador impide gestionar el sistema.

**Independent Test**: Usar cuentas nuevas, existentes sin segundo factor y con segundo factor activo; comprobar permisos en cada paso y degradar al último administrador.

**Acceptance Scenarios**:

1. **Given** una cuenta con segundo factor activo, **When** presenta solo contraseña, código incorrecto, desafío vencido o ya finalizado, **Then** no obtiene acceso operativo.
2. **Given** contraseña provisoria pendiente de cambiar, **When** se intenta operar, incluso mediante una solicitud directa o tras recargar, **Then** únicamente se permite completar la habilitación propia o cerrar sesión, independientemente de la elección de 2FA.
3. **Given** un segundo factor activo, **When** se intenta reemplazarlo, **Then** se exige una comprobación reforzada de identidad y conocer únicamente la contraseña no alcanza.
4. **Given** una instalación nueva o reiniciada en modo de operación, **When** se habilita el portal, **Then** no aparecen cuentas con credenciales conocidas de demostración y las cuentas existentes mantienen su estado.
5. **Given** el último administrador activo, **When** se intenta degradarlo, desactivarlo o retirarlo, incluso con acciones simultáneas, **Then** no se permite un resultado sin administración activa.
6. **Given** cinco fallos de autenticación de una cuenta dentro de quince minutos, **When** se reintenta durante la espera temporal, **Then** no se habilita acceso y se comunica que podrá reintentarse, sin revelar si la cuenta existe ni bloquearla permanentemente.
7. **Given** una cuenta con contraseña definitiva y 2FA desactivado, **When** presenta su contraseña válida, **Then** puede operar según su rol sin configurar ni presentar segundo factor.
8. **Given** una configuración de 2FA iniciada pero no confirmada, **When** la persona la cancela o vuelve a ingresar, **Then** el factor permanece desactivado y su cuenta sigue usando contraseña; la activación solo se completa tras comprobar un código válido y entregar los códigos de recuperación.
9. **Given** una cuenta con 2FA activo que perdió el teléfono, **When** presenta contraseña válida y un código de recuperación vigente, **Then** ese código se consume una sola vez y solo habilita restablecer el factor; no concede una sesión operativa antes de completar la reconfiguración.
10. **Given** un código de recuperación ya utilizado, **When** se intenta reutilizarlo incluso simultáneamente, **Then** no permite una segunda recuperación; generar otro juego o desactivar 2FA invalida los códigos anteriores.
11. **Given** una persona que desea desactivar 2FA, **When** confirma su contraseña y demuestra posesión del factor activo o de un código de recuperación vigente, **Then** se registra la desactivación deliberada y los siguientes ingresos vuelven a exigir solo contraseña, manteniendo el cambio inicial obligatorio si corresponde.

---

### User Story 3 - Comprometer capacidad real sin perder reservas (Priority: P1)

Como administrador quiero aprobar y volver a encender servicios considerando los destinos reales y todos los compromisos en curso, para evitar asignaciones sobre saldos ficticios.

**Why this priority**: Existen caminos que evitan reservas y una ventana de despliegue sin contabilización que perjudica a todas las cátedras.

**Independent Test**: Con capacidad para una sola asignación, ejecutar aprobaciones, inicios, despliegues y liberaciones simultáneos; contrastar compromiso y consumo durante cada transición.

**Acceptance Scenarios**:

1. **Given** un pedido solicitado, **When** se aprueba por cualquier camino, **Then** se verifica capacidad, se reserva y se registra la decisión, sin aprobación aislada ni reserva incoherente.
2. **Given** un pedido aprobado en despliegue o con resultado incierto, **When** aún no existe un servicio confirmado, **Then** conserva su capacidad comprometida hasta convertirla en consumo o liberar tras reconciliación.
3. **Given** dos decisiones simultáneas y saldo para una sola, **When** se confirman, **Then** solo una consume ese saldo; la otra informa el conflicto, salvo sobreasignación administrativa deliberada y justificada.
4. **Given** un servicio detenido o pausado cuya capacidad se reutilizó o cuya vigencia terminó, **When** se solicita encenderlo por cualquier vía, **Then** se comprueban permiso, vigencia y saldo antes de actuar y se explica por qué debe permanecer detenido si corresponde.
5. **Given** opciones avanzadas de una asignación, **When** se prepara el recurso, **Then** no pueden alterar silenciosamente identidad, recursos autorizados ni aislamiento.
6. **Given** saldo agregado pero destino elegible insuficiente, **When** se evalúa la asignación, **Then** se informa la limitación real sin usar el disco del anfitrión como almacenamiento del servicio ni duplicar capacidad compartida.
7. **Given** una reserva caducada, **When** se intenta desplegar antes o después de su revisión automática, **Then** se exige una nueva decisión de capacidad vigente.
8. **Given** un pedido aprobado para un inicio futuro, **When** transcurren veinticuatro horas desde su aprobación pero aún no llegó ese inicio, **Then** su reserva continúa comprometida y no caduca antes de tener oportunidad de desplegarse; ambas partes ven la fecha habilitada y el límite de la reserva.

---

### User Story 4 - Confirmar resultados y recuperar operaciones (Priority: P1)

Como administrador y docente quiero que los estados describan resultados reales y que un fallo se pueda recuperar sin multiplicar recursos ni perder datos.

**Why this priority**: Una tarea aceptada puede fallar después; anunciar éxito anticipado rompe disponibilidad, historial y capacidad.

**Independent Test**: Preparar tareas exitosas, fallidas y de resultado incierto e interrumpir el portal después de una creación simulada; comprobar resultado, compromiso y reintento.

**Acceptance Scenarios**:

1. **Given** una creación, inicio, pausa o baja pendiente, **When** se acepta su orden, **Then** se muestra la operación en curso y no un resultado exitoso sin confirmar.
2. **Given** un apagado automático que falla al terminar, **When** se conoce el fallo, **Then** no se declara liberada capacidad de un recurso que sigue corriendo y se informa el incidente.
3. **Given** un recurso creado antes de una interrupción del portal, **When** se recupera o reintenta, **Then** se reconoce el recurso propio, se completa su registro y no se duplica ni se adopta uno ajeno.
4. **Given** un tipo de recurso no soportado, **When** se solicita su aprovisionamiento, **Then** se rechaza antes de dejar el pedido en despliegue y se explica cómo corregirlo.
5. **Given** infraestructura o correo lentos, **When** otras personas realizan tareas independientes, **Then** el portal sigue respondiendo y un fallo de correo no revierte operaciones ya confirmadas.
6. **Given** una acción o vencimiento ya aplicado, **When** se vuelve a procesar, **Then** no se duplica el recurso, la liberación ni el mismo evento histórico.

---

### User Story 5 - Solicitar y aprobar datos y vigencia coherentes (Priority: P2)

Como docente quiero crear y consultar solicitudes y responder aclaraciones propias sin arrastrar datos incompatibles; como administrador quiero evaluarlas, pedir aclaraciones, corregirlas o cancelarlas y revisar el costo y las fechas que efectivamente autorizo.

**Why this priority**: Los formularios actuales mezclan modelos/plantillas, conservan fechas anteriores o impiden justificar aumentos de recursos.

**Independent Test**: Alternar modelos y cerrar/reabrir solicitudes; devolver un pedido con aclaraciones, comprobar ambos avisos y responder como titular actual sólo en ese estado. Denegar reenvíos ajenos, cancelación docente y selección de hardware. Modificar recursos durante la aprobación como administrador y contrastar lo pedido, autorizado y entregado.

**Acceptance Scenarios**:

1. **Given** una solicitud nueva tras cerrar otra, **When** se abre el formulario, **Then** comienza coherente entre modelo, plantilla y cátedra, sin valores incompatibles de la anterior.
2. **Given** una plantilla retirada o incompatible, **When** se intenta pedirla como nueva, **Then** se rechaza la combinación tanto desde el formulario como por otra vía.
3. **Given** un pedido que requiere ajustes, **When** administración corrige y reenvía cambiando entre vigencia personalizada y académica, **Then** permite editar sus fechas y elimina o recalcula las que ya no correspondan; el docente consulta las observaciones y comunica las correcciones por el canal institucional, sin mutar ese pedido. Administración también puede cancelarlo con motivo registrado.
4. **Given** una modificación administrativa que supera capacidad, **When** se revisa, **Then** se muestra su costo efectivo y puede justificarse antes de confirmar; si el saldo cambió se exige una nueva revisión.
5. **Given** datos obligatorios faltantes, recursos inválidos o fechas incoherentes, **When** se guarda o aprueba, **Then** se señalan las correcciones sin perder los datos válidos ni asignar silenciosamente otro período.
6. **Given** un servicio disponible y su renovación, **When** se consulta su vigencia o se aplica la renovación, **Then** las fechas coinciden con lo aprobado y se conserva el servicio y sus datos.
7. **Given** un calendario lectivo configurado para un año, **When** se elige primer cuatrimestre, segundo cuatrimestre o anual, **Then** se muestran sus fechas reales; si ese período no está configurado se informa qué falta y no se inventan fechas.
8. **Given** un pedido aprobado con inicio futuro, **When** se intenta desplegar desde cualquier control o solicitud directa antes de ese inicio, **Then** se conserva en espera sin crear ni encender recursos; al llegar el inicio se habilita el despliegue autorizado, y al terminar la vigencia deja de admitirse.
9. **Given** un calendario corregido después de aprobar un pedido, **When** se consulta o despliega ese pedido, **Then** mantiene las fechas autorizadas; cambiarlas exige una nueva decisión registrada y revisión de la reserva, sin afectar silenciosamente otros servicios.
10. **Given** un calendario sin configurar o un año distinto del actual, **When** se solicita una vigencia académica, **Then** se exige un período configurado de ese año; una solicitud personalizada con rango válido sigue disponible.
11. **Given** un servicio vigente con renovación aprobada para un período posterior y separado, **When** termina la vigencia actual, **Then** se confirma su pausa y se conserva el contenido; ninguna solicitud de inicio durante el intervalo permite encenderlo por haber sido aprobada esa renovación.
12. **Given** ese servicio pausado y un período renovado ya iniciado, **When** se solicita reactivarlo, **Then** conserva identidad y datos y se enciende solo si existe capacidad; si no la hay, informa el conflicto, permanece pausado y permite reintentar mientras el período siga vigente.

---

### User Story 6 - Recibir una plataforma o aplicación utilizable (Priority: P2)

Como responsable quiero recibir lo ofrecido con una dirección y un acceso comprobados, para que los alumnos puedan utilizarlo desde la red prevista sin administrar infraestructura.

**Why this priority**: Crear un contenedor no acredita por sí solo el resultado PaaS/SaaS comprometido para la práctica.

**Independent Test**: Preparar desde cero las definiciones de PostgreSQL y BookStack siguiendo la guía, solicitar dos instancias independientes de cada una y usar sus funciones de referencia desde un equipo distinto del servidor del portal. La preparación inicial técnica se distingue del despliegue cotidiano desde el catálogo.

**Acceptance Scenarios**:

1. **Given** un servicio de referencia aprobado, **When** se comprueba su función y disponibilidad, **Then** la cátedra recibe dirección, método de acceso y vigencia reales, sin datos inventados.
2. **Given** un contenedor encendido con aplicación caída o acceso inválido, **When** se evalúa su entrega, **Then** no se anuncia como utilizable y se informa a administración qué falta resolver.
3. **Given** un alumno en la red autorizada con los datos distribuidos por su docente, **When** usa el servicio, **Then** completa la tarea de referencia sin entrar al portal ni recibir una cuenta administrativa.
4. **Given** software solicitado sin preparación soportada, **When** el administrador evalúa el pedido, **Then** puede ajustarlo o rechazarlo con motivo sin prometer una instalación automática arbitraria.
5. **Given** una plantilla renombrada, corregida o retirada, **When** se consulta un servicio anterior, **Then** conserva identidad, modelo, recursos y acceso sin reinterpretar su historia a partir del catálogo actual.
6. **Given** PostgreSQL del catálogo, **When** el usuario autorizado se conecta con los datos entregados, crea una tabla e inserta/consulta un registro de prueba, **Then** la tarea funciona en su instancia y no permite acceder a otra cátedra ni a los datos internos del portal; el registro persiste tras detener e iniciar.
7. **Given** BookStack del catálogo, **When** el docente crea un libro con una página y un alumno ingresa con su cuenta individual de lectura, **Then** puede leerla sin recibir permisos de edición/administración y el contenido persiste tras reiniciar.
8. **Given** una definición de servicio validada, **When** un administrador despliega una segunda instancia desde el catálogo, **Then** no necesita instalar paquetes o editar código para ese despliegue, y las dos instancias tienen identidad, credenciales y datos independientes.
9. **Given** que todavía no se realizó la entrevista sobre el libro virtual, **When** se presenta la demostración BookStack, **Then** se identifica como referencia provisional de publicación de contenidos y no como aceptación del producto final del cliente; quedan registradas las preguntas para adaptar o sustituir esa definición.
10. **Given** dos cuentas individuales de alumnos creadas por el docente dentro de su BookStack, **When** se prueba lectura, edición, administración y revocación, **Then** ambos pueden leer, ninguno puede editar ni administrar usuarios, y revocar uno no impide el acceso del otro ni concede acceso a otra instancia; no se crean cuentas de alumnos en NAP.

---

### User Story 7 - Comprender estado, alertas y acciones accesibles (Priority: P2)

Como docente o administrador quiero distinguir ausencia de datos de una falla, recibir avisos útiles y completar tareas con teclado para decidir sin interpretar información engañosa.

**Why this priority**: Errores silenciosos, filtros incorrectos y métricas mal interpretadas afectan operación, disponibilidad y accesibilidad.

**Independent Test**: Usar observaciones controladas, interrumpir consultas, provocar alertas y completar formularios/diálogos usando solo teclado.

**Acceptance Scenarios**:

1. **Given** una consulta fallida o datos anteriores, **When** se muestra el listado, **Then** se informa el fallo o antigüedad y se ofrece reintento, sin presentar vacío como resultado confirmado.
2. **Given** servicios de infraestructura, plataforma y aplicación, **When** se filtran, **Then** aparecen por modelo ofrecido aunque compartan tecnología de ejecución.
3. **Given** contadores de red constantes o reiniciados, **When** se evalúa inactividad, **Then** se considera el tráfico de la ventana sin sumar tráfico histórico ni producir incrementos negativos.
4. **Given** observaciones faltantes o muchas capturas concentradas en poco tiempo, **When** se decide una pausa, **Then** no se confunde cantidad de filas con cobertura temporal suficiente.
5. **Given** caída o consumo sostenido confirmado, **When** se evalúa la condición, **Then** se avisa a personas autorizadas y no se repite la misma apertura en cada revisión del incidente.
6. **Given** pausa o vencimiento programados, **When** se aproxima su ejecución, **Then** la cátedra conoce motivo y plazo de reacción; un fallo de notificación queda visible para administración.
7. **Given** una persona que usa teclado, **When** opera diálogos, formularios, métricas o copia un acceso, **Then** alcanza controles, mantiene foco predecible y recibe un resultado verdadero de cada acción.

---

### User Story 8 - Operar y entregar un prototipo verificable (Priority: P2)

Como administrador y responsable de la práctica quiero instalar, actualizar, respaldar y restaurar el portal conservando datos y contar con manuales y evidencia coherentes para entregar un sistema mantenible.

**Why this priority**: Una demostración local y las simulaciones no acreditan por sí solas integración real, recuperación y entregables finales.

**Independent Test**: Seguir la guía desde otro equipo, actualizar y restaurar una copia de los datos internos del portal, y ejecutar el procedimiento externo de restauración sobre una instancia de cada aplicación de referencia en un entorno de prueba, comparando sus datos con los cortes respaldados.

**Acceptance Scenarios**:

1. **Given** configuración operativa documentada, **When** se instala o actualiza, **Then** funciona desde otra computadora sin editar datos manualmente ni usar direcciones locales del visitante.
2. **Given** datos históricos, **When** se actualiza su organización o reduce detalle antiguo de métricas, **Then** se conservan pertenencia, autoría, recursos asignados y reconstrucción del consumo por período.
3. **Given** un respaldo identificado de los datos internos del portal, **When** se restaura en un entorno de prueba, **Then** se recuperan y verifican cuentas, pedidos, registros de servicios, historial y consumo del corte respaldado.
4. **Given** las comprobaciones de entrega, **When** se revisan, **Then** verifican política vigente y regresiones de los hallazgos, sin mantener expectativas antiguas contradictorias ni exigir clúster real para simulaciones.
5. **Given** infraestructura de validación disponible, **When** se prueba el recorrido real con ambos roles, **Then** se conserva evidencia de accesos de alumno, concurrencia, fallos/reintentos y dependencias pendientes.
6. **Given** una persona ajena al desarrollo, **When** recibe informe, manuales, modelo de datos y guía operativa, **Then** identifica qué se entregó y cómo usarlo, mantenerlo y recuperarlo, distinguiendo responsabilidades de infraestructura.
7. **Given** las vulnerabilidades verificadas en el análisis, **When** se prepara la entrega, **Then** cada una tiene una corrección o mitigación comprobada y documentada, y los recorridos afectados siguen cumpliendo sus resultados de aceptación.
8. **Given** respaldos de una instancia PostgreSQL y una BookStack de referencia, **When** se ejecuta con infraestructura el procedimiento externo en un entorno de prueba, **Then** se recuperan el registro de base de datos y el libro/página del corte correspondiente y se verifica su uso con los accesos previstos, sin requerir un módulo de respaldos dentro del portal.

### Edge Cases

- Identificadores adivinados, sesión alterada, cuenta retirada o titularidad reasignada durante una sesión: comprobar los permisos efectivos actuales. Reenvío/cancelación docente se deniega aun sobre lo propio.
- Consola nativa ya abierta al reasignar, retirar, desactivar o cambiar rol: revocar acceso y terminar las sesiones afectadas antes de completar el cambio; una falla externa conserva el bloqueo y el trámite pendiente, sin entregar recursos al nuevo titular.
- Referencia de evidencia inexistente, alterada, de otra instancia/preparación o simulada: impedir validación/publicación/entrega real; un checksum no demuestra por sí solo que ocurrió una prueba de red.
- Cuenta nueva o antigua con contraseña provisoria pendiente: acceso limitado al cambio inicial; no haber elegido 2FA no agrega un bloqueo operativo.
- Configuración de 2FA abandonada antes de confirmarla: conservar el acceso por contraseña y no tratar el factor como activo.
- Pérdida del segundo factor del único administrador: contraseña y código de recuperación de un solo uso permiten restablecerlo; si también se pierden los códigos, recuperación asistida documentada con identidad comprobada, sin reactivar credenciales conocidas de prueba.
- Dos intentos simultáneos con el mismo código de recuperación, juego regenerado o 2FA desactivado: no reutilizar códigos consumidos o invalidados.
- Doble aprobación del mismo pedido; aprobación simultánea con reversión o expiración; dos inicios sobre el mismo saldo: una decisión válida y contabilidad coherente.
- Reserva que vence durante creación, respuesta externa tardía o reinicio del portal: reconciliar antes de crear otra vez o liberar compromisos.
- Reserva de un pedido aprobado con semanas de anticipación: no caduca a las veinticuatro horas de aprobación; su espera futura permanece visible y comprometida.
- Recurso ya ausente o recurso ajeno con identidad parecida: confirmar existencia y pertenencia antes de adoptar o eliminar.
- Falta de infraestructura o métricas: datos sin confirmar, nunca saldo libre o inactividad supuestos por ausencia de observación.
- Calendario académico ausente, cambio de año o edición posterior a una aprobación: no inventar períodos ni cambiar fechas ya autorizadas.
- Intento de despliegue anterior al inicio, en el instante de habilitación o después del fin inclusivo: aplicar los mismos límites desde cualquier vía, sin sustituirlos por 180 días.
- Renovación y vencimiento simultáneos, revisión repetida de un servicio vencido: resultado coherente sin duplicar la misma transición.
- Renovación aprobada o pendiente para un período futuro separado: no extender por ese motivo el período actual ni cubrir el intervalo. Conservar los períodos autorizados y el disco persistente, liberando cómputo solo tras confirmar la pausa.
- Inicio del período renovado sin cómputo disponible: no encender anticipadamente ni reconstruir el servicio; mantener datos y explicar que se puede reintentar dentro de la vigencia.
- Plantilla corregida/retirada y opciones avanzadas incompatibles: conservar interpretación histórica e invariantes del recurso autorizado.
- Contadores reiniciados, muestras duplicadas o lecturas manuales frecuentes: tráfico y cobertura determinados por períodos observados.
- Correo caído, portapapeles denegado o sesión local dañada: resultado verdadero de la acción y recuperación de acceso sin bloqueo permanente.
- Configuración operativa incompleta o con secretos de ejemplo: impedir habilitación operativa e indicar lo que debe corregirse.
- Imagen o preparación de servicio con cuentas predeterminadas, datos de prueba ajenos o credenciales repetidas: no publicar ni entregar esa instancia como utilizable.
- Copia interna del portal restaurada sin los datos de una aplicación: no presentarla como respaldo de esa aplicación; sus datos y configuración necesarios deben recuperarse por el procedimiento externo identificado y probado, sin sobrescribir instancias de uso real durante la aceptación.

## Requirements *(mandatory)*

### Functional Requirements

**Autorización y acceso**

- **FR-001**: El sistema DEBE comprobar pertenencia y permiso vigente antes de consultar u operar pedidos, servicios, accesos, métricas e historiales, por todas las vías habilitadas.
- **FR-002**: El rol cátedra DEBE limitarse a sus cátedras actuales; una denegación NO DEBE revelar contenido ni producir cambios o transiciones exitosas.
- **FR-003**: Aprobar, rechazar, cancelar, asignar capacidad y administrar personas, cátedras o plantillas DEBE exigir administración. Las excepciones docentes son crear pedidos, responder/reenviar aclaraciones de pedidos propios únicamente en `requiere_ajuste`, solicitar renovaciones y operar servicios propios. Responder no concede aprobación ni selección de hardware.
- **FR-004**: El 2FA DEBE ser voluntario para ambos roles. Las cuentas con 2FA desactivado DEBEN poder operar con contraseña válida una vez completado el cambio inicial; las cuentas que lo activen DEBEN completar también el segundo factor antes de obtener acceso operativo. Iniciar su configuración NO DEBE activarlo hasta confirmar un código válido.
- **FR-005**: El cambio inicial pendiente DEBE limitar el acceso a completar la habilitación propia, consultar la información mínima necesaria para hacerlo o cerrar sesión, aun tras recargas o solicitudes directas.
- **FR-006**: Cada desafío de segundo factor DEBE vencer a los cinco minutos, finalizar una sola vez y pertenecer al ingreso que lo originó. La sustitución/recuperación del factor DEBE acreditar identidad y quedar registrada.
- **FR-007**: El sistema DEBE aplicar espera temporal tras los fallos definidos en US2.6 sin revelar existencia de cuentas ni permitir eludir el control alternando cuentas desde un mismo origen.
- **FR-008**: La habilitación operativa NO DEBE crear cuentas/secretos conocidos de demostración ni datos de prueba; un reinicio NO DEBE restablecer credenciales o modificar cuentas existentes.
- **FR-009**: Cambios de rol, retiros y desactivaciones DEBEN preservar al menos un administrador activo, incluso ante acciones simultáneas.

**Capacidad y resultado de operaciones**

- **FR-010**: Toda aprobación DEBE aplicar las mismas validaciones, compromiso de capacidad e historial; NO DEBE poder reemplazarse por un cambio aislado de estado.
- **FR-011**: El compromiso DEBE mantenerse desde aprobación hasta consumo confirmado o liberación reconciliada, incluyendo despliegue y resultado incierto, sin períodos sin contabilizar ni doble consumo.
- **FR-012**: Aprobar, encender y reactivar DEBE decidirse indivisiblemente frente a otras decisiones sobre el mismo saldo. Reconfirmar un pedido NO DEBE duplicar reserva ni historial de aprobación.
- **FR-013**: El saldo DEBE corresponder a destinos elegibles reales, considerar compromisos y consumo externo, reservar margen del anfitrión y no duplicar capacidad compartida. Una disponibilidad no verificable NO DEBE asumirse libre.
- **FR-014**: La configuración final DEBE respetar identidad, recursos autorizados y aislamiento; ninguna opción avanzada DEBE modificarlos silenciosamente.
- **FR-015**: La sobreasignación DEBE ser exclusivamente administrativa, advertida y justificada con valores/motivo registrados; la evaluación mostrada DEBE corresponder a la selección que se confirma.
- **FR-016**: Una autorización caducada NO DEBE permitir despliegue sin nueva decisión vigente, aunque su revisión automática aún no se haya ejecutado.
- **FR-017**: Encender cualquier servicio detenido o pausado DEBE comprobar permisos, vigencia y capacidad; si no cumple, DEBE mantenerse detenido y explicarse el siguiente paso.
- **FR-018**: Renovar DEBE conservar servicio, identidad, datos y fechas de cada período autorizado, sin reservar otra vez los recursos que ya consume. Una renovación para un período separado NO DEBE extender silenciosamente la vigencia actual hasta el nuevo fin ni impedir la pausa del intervalo; su posterior encendido requiere comprobar cómputo disponible.
- **FR-019**: Crear, iniciar, pausar y dar de baja DEBE informar efectos confirmados; aceptar una orden externa NO DEBE presentarse como haber completado su efecto.
- **FR-020**: Un fallo o resultado incierto DEBE dejar motivo, estado identificable y recuperación posible, conservando el compromiso necesario hasta reconciliar el recurso real.
- **FR-021**: Reintentar o recuperar DEBE reconocer identidad y pertenencia, evitar duplicados y no adoptar ni eliminar recursos ajenos.
- **FR-022**: Toda acción humana/automática DEBE registrar actor, instante, motivo y resultado; repetir una acción ya aplicada NO DEBE duplicar su efecto ni el mismo evento histórico.

**Solicitudes, oferta y vigencia**

- **FR-023**: Cada solicitud nueva DEBE iniciar coherente entre modelo, plantilla y cátedra, sin valores incompatibles arrastrados de otro formulario. DEBE conservar nombre y justificación pedagógica. En PaaS/SaaS, «Otro» permite describir un servicio fuera del catálogo sin plantilla ni reserva inicial; administración prepara y publica la oferta y selecciona su perfil compatible al aprobar el pedido original. IaaS requiere plantilla publicada.
- **FR-024**: Las nuevas solicitudes DEBEN exigir plantilla disponible y compatible con el modelo, también fuera de la interfaz.
- **FR-025**: Pedir aclaración DEBE devolver el pedido con observaciones y avisos por portal/correo. Su titular actual DEBE poder responder y reenviar sólo el pedido propio en `requiere_ajuste`, editando la información de solicitud y vigencia sin hardware. Cambiar modalidad elimina o recalcula fechas incompatibles. Administración recibe aviso de la respuesta, conserva la decisión de aprobación y puede corregir/reenviar; cancelar sigue siendo administrativo.
- **FR-026**: Administración DEBE revisar costo y fechas efectivos tras cambiar la asignación y poder justificar el nuevo costo sin quedar bloqueada por la evaluación anterior.
- **FR-027**: Guardar por cualquier control DEBE validar campos obligatorios, correo, recursos positivos y fechas, indicando correcciones concretas sin perder datos válidos.
- **FR-028**: Pedidos/servicios DEBEN conservar identidad, modelo y recursos históricos frente a correcciones o retiros de plantillas.
- **FR-029**: Los filtros DEBEN distinguir infraestructura, plataforma y aplicación por modelo ofrecido, independientemente de la tecnología de ejecución.
- **FR-030**: La vigencia autorizada DEBE tener inicio/fin efectivos, coherentes y visibles para ambas partes; NO DEBE sustituirse silenciosamente por otro período.
- **FR-031**: Altas nuevas DEBEN rechazar rangos incompletos, invertidos o con fin vencido, y presentar fechas locales inequívocas conservando un instante de referencia común.
- **FR-032**: Avisos previos y renovaciones DEBEN informar el plazo efectivo y conservar datos cuando se detenga por vencimiento.
- **FR-033**: Un tipo no soportado DEBE rechazarse antes del aprovisionamiento; la oferta visible DEBE coincidir con capacidades disponibles.
- **FR-034**: Esta entrega DEBE soportar el aprovisionamiento y ciclo de vida completos de contenedores LXC. QEMU queda fuera de alcance y NO DEBE ofrecerse para solicitudes nuevas; las referencias históricas existentes DEBEN conservarse sin presentarlas como nuevas capacidades disponibles.

**Servicios utilizables y avisos**

- **FR-035**: Un servicio del catálogo mínimo NO DEBE anunciarse utilizable hasta comprobar su función de referencia y entregar dirección, puerto y acceso reales desde la red prevista. La comprobación DEBE referenciar evidencia inmutable previamente registrada por administración, con autor institucional, integridad, identidad de instancia/preparación, origen, instante y resultados; se rechazan referencias desconocidas, simuladas o de otro recurso para la aceptación real.
- **FR-036**: Los accesos DEBEN corresponder a servicio/cátedra autorizados y distinguir uso de alumno de administración; los secretos NO DEBEN aparecer en consultas generales que no los necesiten.
- **FR-037**: Software sin preparación soportada DEBE poder evaluarse, ajustarse o rechazarse con motivo sin prometer instalación automática arbitraria; los servicios elegidos DEBEN tener preparación reproducible.
- **FR-038**: El catálogo mínimo DEBE incluir PostgreSQL como plataforma de base de datos y BookStack como aplicación de publicación de libros/páginas. Su aceptación DEBE comprobar respectivamente conexión y escritura/lectura de un dato persistente, y creación de un libro/página por el docente y lectura por un alumno. Ambas preparaciones parten de cero, con instancias aisladas; BookStack es referencia provisional de demostración y no una definición acordada del libro virtual del cliente.
- **FR-039**: El sistema DEBE detectar caída confirmada y consumo sostenido, diferenciarlos de falta de observaciones y registrar apertura/recuperación sin repetir el mismo incidente en cada evaluación.
- **FR-040**: Los avisos DEBEN mostrarse con alcance por cátedra y notificarse por correo a destinatarios autorizados; un fallo de envío DEBE quedar visible para administración sin revertir la operación principal.
- **FR-041**: Las modalidades primer cuatrimestre, segundo cuatrimestre y anual DEBEN resolver fechas desde un calendario lectivo configurable por administración para el año seleccionado. Antes de la fecha inicial NO DEBE permitirse crear ni encender el recurso solicitado, incluso por vías alternativas; desde el inicio se habilita el despliegue autorizado y después de la fecha final no se admite una nueva activación sin renovación válida. La opción personalizada conserva fechas explícitas validadas.

**Métricas y experiencia**

- **FR-042**: La inactividad DEBE evaluarse con tráfico de la ventana, reinicios de contadores y cobertura por intervalos; repetir capturas en un intervalo NO DEBE reemplazar observación faltante.
- **FR-043**: Consumo y máximos DEBEN corresponder al recurso y fecha observados; cualquier referencia usada por falta de confirmación DEBE identificarse como tal.
- **FR-044**: La interfaz DEBE distinguir carga, vacío confirmado, error y datos anteriores, ofreciendo reintento y antigüedad del último dato conocido.
- **FR-045**: Diálogos y tareas principales DEBEN admitir teclado, foco inicial/retorno predecibles, nombres accesibles, campos identificados y bloqueo de navegación accidental al fondo.
- **FR-046**: Restaurar sesión DEBE comprobar habilitación/permisos actuales; datos locales dañados DEBEN permitir volver a autenticarse sin bloquear la aplicación.
- **FR-047**: Copiar, guardar y confirmar DEBE informar éxito solo si ocurrió; una acción en curso DEBE impedir confirmaciones duplicadas accidentales.
- **FR-048**: Infraestructura o correo lentos NO DEBEN impedir consultas y acciones independientes; el portal DEBE cumplir los resultados de rendimiento acordados.
- **FR-049**: Consultar NO DEBE causar capturas ilimitadas ni multiplicar la cadencia por visitante. El historial DEBE poder acotarse por período/cantidad.
- **FR-050**: Reducir detalle antiguo DEBE conservar resúmenes que permitan reconstruir consumo por cátedra/período; bajas o cambios de titular NO DEBEN borrar el historial académico.

**Operación y entrega**

- **FR-051**: El portal DEBE funcionar desde otra computadora con direcciones operativas documentadas y conexiones verificadas, sin depender de direcciones locales del visitante ni secretos de ejemplo.
- **FR-052**: Credenciales de infraestructura DEBEN mantenerse fuera del código y con permisos mínimos; la consola propia DEBE conservar pertenencia verificada e aislamiento por cátedra, también mediante sesiones o URLs nativas previas. Reasignar o retirar permisos DEBE bloquear las acciones afectadas en el portal y quedar pendiente hasta comprobar la revocación de permisos y sesiones de consola nativas; solo después se hace efectivo el cambio y se habilita al nuevo titular, conservando los accesos legítimos restantes. Sin capacidad institucional demostrada de revocación no se habilita consola.
- **FR-053**: Actualizar datos DEBE ser reproducible/versionado, preservar relaciones e historial y rechazar recursos negativos, fechas incoherentes e identidades de infraestructura vigentes duplicadas.
- **FR-054**: Instalación nueva y actualización DEBEN admitir las mismas reglas y datos válidos; retirar una regla antigua DEBE reflejarse coherentemente en documentación y pruebas.
- **FR-055**: El portal DEBE contar con respaldo y restauración comprobada de sus datos internos y guía de actualización/reinicio que no regenere cuentas ni pierda datos del corte respaldado. Los datos de las aplicaciones PostgreSQL y BookStack DEBEN tener un procedimiento externo documentado y probado de respaldo/restauración, coordinado con infraestructura, que identifique datos y configuración necesarios, responsables y evidencia de recuperación. Esta entrega NO DEBE incorporar un módulo del portal para programar o gestionar copias y restauraciones de cada aplicación.
- **FR-056**: Vulnerabilidades de dependencias identificadas y aplicables a los flujos operativos DEBEN corregirse o tener mitigación comprobada/documentada, conservando el comportamiento acordado.
- **FR-057**: La entrega DEBE incluir regresiones de los hallazgos, concurrencia en decisiones de capacidad y al menos un fallo externo simulado al modificar orquestación; las simulaciones DEBEN poder ejecutarse sin infraestructura real.
- **FR-058**: La evidencia DEBE distinguir simulación, integración real, recuperación y limitaciones dependientes de terceros.
- **FR-059**: Informe técnico, manual docente, manual administrador, modelo de datos y guía operativa DEBEN reflejar lo entregado y vincular objetivos/hallazgos con resultados de aceptación.
- **FR-060**: Los documentos DEBEN distinguir el trabajo individual del de infraestructura, actualizar inventario/decisiones vigentes y registrar capacidades e integraciones postergadas.

**Preparación reutilizable de servicios y calendario**

- **FR-061**: Cada servicio publicable DEBE tener una definición identificada y versionada con producto, preparación reproducible, recursos, parámetros permitidos, dependencias, comprobación funcional, datos persistentes y forma de entregar acceso. Solo una definición validada DEBE habilitarse para nuevas solicitudes.
- **FR-062**: El despliegue cotidiano de una definición validada DEBE completarse mediante la selección y aprobación en el portal, sin repetir instalaciones manuales ni editar código. La preparación inicial DEBE disponer de instrucciones reproducibles y distinguir los pasos técnicos de las acciones ordinarias del administrador.
- **FR-063**: Cada instancia DEBE recibir identidad y credenciales propias y comenzar sin datos de otra cátedra ni cuentas predeterminadas utilizables. La plataforma de datos entregada DEBE ser independiente de los datos internos de gestión del portal.
- **FR-064**: El administrador DEBE poder configurar y corregir fechas inicial/final de los tres períodos académicos para años desde 2026. La selección del año en solicitudes y calendarios DEBE rechazar años anteriores a 2026; los períodos de calendario y los rangos personalizados nuevos NO DEBEN admitir fechas anteriores al 01/01/2026. El sistema DEBE validar rangos, identificar el año elegido y explicar la ausencia de un período sin reemplazarlo por una duración fija. NO DEBE exigir fechas académicas predefinidas por el desarrollador.
- **FR-065**: La aprobación DEBE conservar las fechas efectivas y la definición de servicio autorizadas. Corregir el calendario o publicar otra versión de una definición NO DEBE modificar pedidos aprobados o servicios existentes sin una nueva decisión explícita y trazable.
- **FR-066**: Un pedido de alta aprobado para inicio futuro DEBE reservar capacidad desde su aprobación y mantenerla visible durante la espera. El plazo ordinario de veinticuatro horas para concretar el despliegue DEBE comenzar en el momento posterior entre aprobación e inicio autorizado; si antes termina la vigencia, ese fin prevalece. Cancelar/revertir DEBE liberar el compromiso según las reglas comunes, y un despliegue en curso conserva la protección de FR-011. Las renovaciones conservan las reglas diferenciadas de FR-018 y FR-072, sin una segunda reserva de alta.
- **FR-067**: La documentación DEBE enseñar a preparar, validar, publicar, desplegar, comprobar, mantener y retirar los servicios de referencia y a incorporar otra definición compatible sin reescribir el flujo de solicitudes/aprobaciones. La entrevista posterior sobre libro virtual DEBE registrarse como relevamiento del producto final, sin bloquear el catálogo básico delegado para esta entrega.
- **FR-068**: La habilitación por fecha DEBE comprobarse en el momento de actuar y no solo al mostrar botones. Esperar un inicio futuro NO DEBE crear un recurso anticipado ni comunicarlo como disponible; el portal DEBE distinguir fecha habilitada, despliegue pendiente, operación en curso y servicio confirmado.

**Segundo factor voluntario y recuperación**

- **FR-069**: Activar 2FA DEBE entregar diez códigos de recuperación individuales de un solo uso para guardar fuera del portal. El sistema DEBE permitir generar un nuevo juego tras una comprobación reforzada de identidad, invalidando el anterior; los códigos completos NO DEBEN volver a mostrarse como información ordinaria de cuenta ni incluirse en registros o correos.
- **FR-070**: La combinación de contraseña válida y código de recuperación vigente DEBE permitir únicamente restablecer el segundo factor. Consumir un código DEBE ser indivisible frente a intentos simultáneos y el acceso operativo DEBE requerir completar el nuevo factor. Si se perdieron teléfono y códigos, DEBE existir recuperación asistida con identidad comprobada y registro de actor/motivo, también para el único administrador.
- **FR-071**: Desactivar voluntariamente 2FA DEBE exigir contraseña y prueba del factor activo o un código de recuperación vigente, registrar la decisión e invalidar los códigos anteriores. La elección de no activarlo NO DEBE afectar permisos del rol ni imponer inscripción obligatoria; las cuentas que ya lo tengan activo DEBEN conservarlo hasta una desactivación autorizada.

**Renovación entre períodos separados**

- **FR-072**: Si el período renovado comienza después de terminar el actual, el sistema DEBE aplicar la pausa al vencer el actual, previo aviso y confirmación del resultado, conservando datos y disco. La renovación futura NO DEBE autorizar uso durante el intervalo, aun si ya está aprobada; desde su inicio solo habilita solicitar reactivación con comprobación de capacidad. Falta de cómputo DEBE mantener el servicio pausado, informar el motivo y permitir reintento dentro del período autorizado, sin recrear el recurso ni garantizar capacidad retenida durante el receso.

**Acceso de alumnos a la aplicación de referencia**

- **FR-073**: En cada instancia BookStack de referencia, el docente DEBE poder crear y revocar cuentas individuales de alumnos con permisos únicamente de lectura mediante la administración de esa aplicación. La entrega DEBE proporcionar al docente acceso para publicar contenido y gestionar esos lectores, limitado a su instancia y sin facultades administrativas sobre NAP o infraestructura. Los alumnos NO DEBEN necesitar cuentas en NAP; la demostración NO DEBE usar una cuenta compartida ni lectura anónima como sustituto de las cuentas individuales. No se exige sincronización de usuarios, inscripción automática ni administración de lectores desde NAP.

**Preparación de pools por cátedra**

- **FR-074**: Antes de crear el primer contenedor de una cátedra, el despliegue DEBE verificar o crear el pool determinista `catedra-{id}`, comprobar los permisos del portal y reutilizarlo en futuros despliegues. La repetición o pérdida de respuesta NO DEBE duplicar pools ni contenedores. Un pool con miembros sin pertenencia comprobada NO DEBE adoptarse ni modificarse. La preparación no establece cuotas ni concede ACL automáticamente. Administración DEBE ver el ID como primera columna de Cátedras y disponer de una consulta sin efectos «Verificar infraestructura», que muestre el estado del pool y sus problemas. Los pools existentes no se eliminan por limpiar la base del portal.

### Key Entities *(include if feature involves data)*

- **Cuenta y habilitación**: persona, rol vigente, estado activo, cambio inicial, elección de segundo factor desactivado/en configuración/activo y desafíos temporales; determina los pasos de ingreso exigibles sin confundir inscripción voluntaria con cambio inicial obligatorio.
- **Cuenta de aplicación**: identidad propia de una instancia BookStack, administrada dentro de ella; distingue al docente que publica y gestiona lectores del alumno con lectura únicamente. No equivale a una cuenta de NAP ni autoriza acceso a otras instancias.
- **Código de recuperación**: credencial de respaldo individual de una cuenta con 2FA activo, perteneciente a un juego vigente y con estado disponible/consumido/invalidado; su uso permite recuperar el factor y no una entrada operativa alternativa permanente.
- **Cátedra y titularidad**: unidad de aislamiento e historia, con responsable actual; una persona puede tener varias y los recursos sobreviven a la reasignación.
- **Pedido y decisión**: necesidad, modelo, fechas efectivas, asignación, justificación y estado; conserva quién autorizó y bajo qué condiciones.
- **Compromiso de capacidad**: recursos y destino elegible autorizados, validez y situación durante despliegue; se convierte en consumo o se libera tras confirmación.
- **Operación de infraestructura**: acción, recurso propio, resultado pendiente/confirmado/fallido/incierto y recuperación; distingue orden aceptada de efecto terminado.
- **Servicio**: recurso entregado a una cátedra con identidad estable, modelo, asignación, disponibilidad, vigencia y acceso; conserva historia aunque cambie el catálogo.
- **Plantilla/oferta**: preparación y recursos disponibles para solicitudes nuevas; retirarla o corregirla no reinterpreta lo ya entregado.
- **Definición de servicio**: producto y versión de su preparación validada, parámetros, requisitos y verificación funcional; permite entregar instancias independientes desde el catálogo.
- **Calendario lectivo**: año académico y fechas configuradas de sus cuatrimestres y período anual; ofrece referencias para solicitudes nuevas sin alterar compromisos existentes.
- **Vigencia**: modalidad, año seleccionado y copia de fechas de cada período autorizado del servicio; distingue cobertura actual, renovaciones futuras e intervalos sin cobertura, y fundamenta habilitación, reserva y vencimiento.
- **Observación/resumen de consumo**: medición fechada, cobertura temporal y agregado histórico por servicio/cátedra; fundamenta actividad y recuperación de capacidad.
- **Incidente/aviso**: condición, alcance, apertura, recuperación, destinatarios y resultado de entrega, sin duplicar el mismo problema persistente.
- **Historial/evidencia**: registro inmutable de actor institucional y registrante, instante, origen, identidad, integridad y resultados de comprobaciones; distingue pruebas reales de simuladas.
- **Cambio de acceso a consola**: solicitud administrativa duradera con permisos anteriores/propuestos, bloqueo preventivo, estado de revocación y evidencia; coordina el cambio académico con la retirada del acceso nativo sin perder historia.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con al menos tres personas y tres cátedras de referencia, el 100 % de accesos ajenos o acciones de rol superior se deniega sin contenido expuesto ni cambios, incluidos reenvío/cancelación docentes de pedidos propios. Tras reasignación o retiro se comprueba denegación con sesión nativa de consola previa y URL guardada, conservación del acceso legítimo restante y cambio pendiente sin entrega al nuevo titular cuando falla la revocación.
- **SC-002**: Ninguna cuenta obtiene acceso operativo sin completar el cambio inicial. Con 2FA desactivado se admite la contraseña válida sin inscripción adicional; con 2FA activo se rechaza el 100 % de ingresos que omitan el factor y de desafíos incorrectos, vencidos o reutilizados del conjunto de aceptación.
- **SC-003**: En diez repeticiones de cada caso concurrente de aprobación, inicio y liberación no hay compromisos duplicados ni sobreasignación injustificada; el compromiso permanece visible en todos los estados intermedios observados.
- **SC-004**: Cada fallo/interrupción de referencia evita anunciar éxito sin confirmar y, al recuperar/reintentar, deja exactamente un recurso propio con registro e historial coherentes.
- **SC-005**: En dos instancias independientes de PostgreSQL y dos de BookStack se completan las tareas de US6.6–US6.7 desde otro equipo, con aislamiento entre cátedras, credenciales distintas y persistencia tras reiniciar; el alumno lector no recibe permisos administrativos.
- **SC-006**: En pruebas de ambos cuatrimestres, anual y personalizado de dos años configurados coinciden fechas mostradas, aprobadas y aplicadas; se rechazan períodos ausentes y rangos inválidos, y reenvíos/renovaciones no arrastran fechas incompatibles ni destruyen datos.
- **SC-007**: El responsable de una cátedra de prueba envía un pedido y consulta su estado sin ayuda del desarrollador; completar el formulario ordinario requiere como máximo tres minutos, excluyendo decisión administrativa y espera externa. Administración completa una asignación modificada y justificada sin bloqueos de formulario.
- **SC-008**: Con 100 servicios, noventa días de observaciones y diez sesiones simultáneas en el entorno documentado, al menos el 95 % de consultas ordinarias muestra resultado en tres segundos o menos, incluso con un despliegue en curso; los fallos no se presentan como vacío confirmado. Se mide por recorrido desde la navegación o cambio de filtro hasta que el listado o gráfica y su alternativa textual están visibles y utilizables en el navegador, incluyendo solicitud, transferencia y renderizado; la latencia de la API es solo un diagnóstico complementario. Cada recorrido debe cumplir el umbral, con fallos y timeouts incluidos en el total.
- **SC-009**: Caída/consumo sostenido de referencia genera aviso en no más de dos ciclos de evaluación; por incidente persistente hay una apertura y una recuperación, sin repetir aperturas en cada ciclo.
- **SC-010**: El 100 % de recorridos principales de formularios, diálogos, consulta de métricas y accesos es ejecutable mediante teclado con foco visible y resultado identificable.
- **SC-011**: Actualizar y restaurar el portal conserva el 100 % de cuentas, relaciones, pedidos, registros de servicios e historial del corte de referencia; reducir detalle mantiene consultable el consumo histórico por cátedra/período. El procedimiento externo recupera una instancia PostgreSQL y una BookStack de prueba, conservando el dato y el libro/página del corte respaldado y acreditando su acceso funcional.
- **SC-012**: La entrega incluye resultados de las ocho historias, evidencia real del recorrido completo e informe/manuales que permiten a una persona ajena al desarrollo usar y operar el prototipo sin corregir datos a mano.
- **SC-013**: Un administrador que sigue la guía puede desplegar desde el portal dos instancias de cada definición ya validada, sin intervención del desarrollador, instalación manual por instancia ni cambios de código, y comprobar que no comparten credenciales ni datos.
- **SC-014**: El 100 % de intentos de despliegue previos al inicio o posteriores al fin de referencia se rechaza sin crear recursos. En el inicio se habilita el despliegue autorizado; corregir luego el calendario no cambia sus fechas aprobadas, y las reservas futuras no caducan prematuramente.
- **SC-015**: En las cuentas de ambos roles se comprueba activación voluntaria, cancelación previa a confirmar, recuperación por código y desactivación autorizada. Cada código admite como máximo una recuperación, incluso ante dos usos simultáneos; ninguno de los juegos consumidos o invalidados permite nuevos accesos, y el único administrador puede recuperarse por el procedimiento definido.
- **SC-016**: Una renovación de referencia con intervalo sin cobertura conserva los dos períodos aprobados y los datos del mismo servicio, confirma su pausa al terminar el primero y rechaza el 100 % de inicios durante el intervalo. En el nuevo período, el caso con capacidad se reactiva sin recreación y el caso sin capacidad permanece pausado con explicación y posibilidad de reintento; el disco se mantiene contabilizado en ambos casos.
- **SC-017**: En cada una de las dos instancias BookStack de referencia, el docente crea dos cuentas individuales de lectura sin intervención del desarrollador. Ambas leen el contenido y se rechaza el 100 % de sus intentos de edición, administración de usuarios y acceso a otra instancia con esas credenciales. Revocar una impide su siguiente acceso sin afectar a la otra; ninguna requiere un alta de alumno en NAP.

## Assumptions

**Alcance y límites**

- Se especifica una única iniciativa sobre el portal existente, planificable en incrementos por historia, conservando lo que ya cumple lo acordado.
- Rige la [constitución 4.0.0](../../.specify/memory/constitution.md): capacidad al aprobar sin cuotas fijas, historial preservado, autenticación propia con segundo factor voluntario y exigible cuando está activo, y excepción de consola propia aislada. La enmienda de autenticación incorpora la corrección explícita del usuario en esta sesión.
- Q1 resuelta: LXC completo en esta entrega; QEMU queda fuera. Q2 resuelta por delegación: preparar desde cero servicios básicos con un mecanismo reutilizable y guía; se eligen PostgreSQL y BookStack como referencias iniciales. Q3 resuelta: calendario lectivo configurable y despliegue habilitado recién desde el inicio.
- BookStack se usa para demostrar publicación y lectura de contenidos; no se presume que cubra interactividad, evaluaciones o el producto exacto denominado libro virtual. Esos requisitos se relevarán en la entrevista; la sustitución del ejemplo debe conservar el mecanismo de catálogo y sus reglas de acceso/disponibilidad.
- Los alumnos de la demostración ingresan con cuentas individuales de lectura en BookStack, creadas y revocadas por su docente dentro de esa aplicación. Son identidades separadas de NAP: no se añade un rol alumno al portal ni se exige sincronización, registro automático o acceso anónimo. La gestión docente queda limitada a su instancia.
- Quedan fuera instalación automática de software arbitrario, administración general automática de red/almacenamiento, nueva consola embebida, rediseño total y reemplazo del conjunto tecnológico existente.
- Mikrotik, autenticación institucional, nuevas plataformas de infraestructura y evaluación pedagógica global siguen fuera salvo acuerdo posterior; documentar su evaluación y dependencia sí integra la entrega.
- Validar integración no convierte responsabilidades de los compañeros sobre clúster, red y almacenamiento en funcionalidades nuevas obligatorias del portal.
- El respaldo del portal cubre sus datos internos. Las copias y restauraciones de datos de las aplicaciones se realizan con herramientas externas coordinadas con infraestructura, con procedimiento y prueba incluidos en la entrega; queda fuera un módulo del portal para su gestión o programación.

**Valores iniciales y dependencias**

- No existen imágenes PaaS/SaaS preparadas: su preparación reproducible, validación y guía forman parte de esta entrega. Se distingue plantilla de recursos, definición de producto e instancia de una cátedra; incorporar un producto nuevo requiere preparación y validación técnica antes de ofrecerlo.
- Las fechas inicial y final se interpretan en la zona horaria institucional: se habilita desde el comienzo del día inicial y se admite el día final completo. No se fijan meses o duraciones académicas sin configuración del administrador.
- La vigencia se materializa al aprobar y los cambios posteriores del calendario no la reescriben. Un pedido futuro permanece aprobado en espera; llegar al inicio habilita el despliegue por los controles autorizados existentes, sin exigir en esta entrega una nueva función de inicio automático al llegar la fecha.
- La espera futura de un alta reserva desde ahora: se elige esta política conservadora para mantener el principio de compromiso al aprobar, sin introducir una agenda de préstamos de capacidad por franjas. El plazo de despliegue empieza en el posterior entre aprobación e inicio y se limita por el fin de vigencia; nunca vence una reserva por no desplegar antes de que esté permitido.
- Una renovación discontinua conserva por separado el período actual y el nuevo: durante el intervalo el servicio se pausa, preserva datos/disco y libera cómputo confirmado. Su aprobación no garantiza retener CPU/RAM durante el receso; desde el nuevo inicio la cátedra puede solicitar reactivación sujeta a capacidad. La renovación futura, aprobada o pendiente, no justifica prolongar el servicio durante ese intervalo sin cobertura.
- El 2FA es opcional para todos los usuarios, incluidos administradores. La contraseña provisoria sí exige cambio antes de operar. Activar 2FA entrega diez códigos de recuperación; el juego completo se presenta al generarlo para que la persona lo guarde. La recuperación asistida es el último recurso si se pierde también ese juego, con identidad comprobada y sin cuenta de prueba.
- La espera por intentos fallidos dura quince minutos desde el quinto fallo; se limita también el origen para evitar alternar cuentas. Se registra el motivo sin exponer contraseñas ni códigos.
- Regla inicial de alerta: caída en dos observaciones consecutivas separadas al menos un minuto; CPU o memoria superior al 90 % de lo asignado durante quince minutos con observaciones suficientes. Recuperación tras dos observaciones normales separadas al menos un minuto. Falta de observación es falta de confirmación, no caída.
- Administración ve todas las alertas y cada responsable solo las propias. El correo se dirige al titular y administradores activos suscritos, sin secretos; su fallo no elimina el aviso del portal.
- Se conserva el aviso de vencimiento siete días antes y la gracia vigente para inactividad. Ambos deben hacerse visibles y notificarse con el plazo de reacción correspondiente.
- Se propone conservar noventa días de detalle de métricas y resúmenes diarios históricos sin caducidad, manteniendo historial de decisiones. No se autoriza perder reconstrucción académica.
- Los resultados de rendimiento se miden con inventario, recursos y red documentados. Se distingue respuesta del portal de la duración física de un aprovisionamiento externo.
- Pruebas reales requieren acceso coordinado a clúster, almacenamiento, red alumno y correo. Su falta queda como validación pendiente; no se reemplaza por una afirmación basada solo en simulación.
- La guía distingue respaldo interno del portal y respaldo externo de las aplicaciones. Frecuencia, destino institucional y herramientas se precisan en la planificación con infraestructura; la validación debe conservar evidencia de restauración de ambos ejemplos en un entorno de prueba.
- Se mantienen decisiones compatibles de specs 001–008. La expectativa antigua de límite de disco debe ajustarse a la política vigente; no se reintroduce por una prueba desactualizada.
- Índices, organización de persistencia, coordinación interna, contratos y versiones concretas se definen en el plan técnico, preservando los resultados exigidos aquí.
- Orientación y preparación conceptual de los ejemplos: [guía de servicios de referencia](guia-servicios-referencia.md). La guía distingue las referencias elegidas de los requisitos aún no relevados del cliente; no constituye un plan técnico ya ejecutado.

**Trazabilidad del análisis**

| Hallazgo o área | Cobertura |
|---|---|
| A01: pedidos ajenos | US1; FR-001–FR-003; SC-001. |
| A02: aprobar sin reserva | US3; FR-010–FR-012; SC-003. |
| A03: segundo factor/cambio inicial | US2; FR-004–FR-007, FR-069–FR-071; SC-002, SC-015. |
| A04: cuentas y configuración de desarrollo | US2/US8; FR-008, FR-051–FR-052; SC-002, SC-012. |
| A05: reservas en despliegue y caducidad | US3/US4; FR-011, FR-016, FR-020–FR-021, FR-066; SC-003–SC-004, SC-014. |
| A06: capacidad del destino real | US3; FR-013; SC-003. |
| A07: inicio evita controles | US3/US5; FR-012, FR-017–FR-018, FR-072; SC-003, SC-016. |
| A08: overrides cambian invariantes | US3; FR-014, FR-027; SC-003–SC-004. |
| A09: servicio/accesos no comprobados | US6; FR-035–FR-038, FR-061–FR-063, FR-065, FR-067, FR-073; SC-005, SC-013, SC-017. |
| A10: vigencia incompleta | US5; FR-025, FR-030–FR-032, FR-041, FR-064–FR-066, FR-068, FR-072; SC-006, SC-014, SC-016. |
| A11: lentitud bloquea el portal | US4/US7; FR-048; SC-008. |
| A12: pausas sin confirmar | US4; FR-019–FR-022; SC-004. |
| A13: contadores/cobertura | US7; FR-042, FR-049; SC-009, SC-011. |
| A14: métricas ajenas/último admin | US1/US2; FR-001–FR-002, FR-009; SC-001–SC-002. |
| A15: oferta incompatible/estado transitorio | US4/US6; FR-033–FR-034; SC-004–SC-005. |
| A16: dependencia vulnerable | US8; FR-056–FR-058; SC-012. |
| UI: formularios, filtros, errores, foco/sesión | US5/US7; FR-023–FR-029, FR-044–FR-047; SC-007, SC-010. |
| Rendimiento/crecimiento de métricas | US7/US8; FR-043, FR-048–FR-050; SC-008, SC-011. |
| Integridad/consistencia del esquema | US8; FR-028, FR-050, FR-053–FR-055; SC-011. |
| Despliegue/documentación/evidencia | US8; FR-051–FR-060; SC-012. |
