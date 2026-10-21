# Análisis del proyecto y pendientes de la práctica

Fecha: 18 de octubre de 2026. Revisión del árbol de trabajo actual, incluidos backend, frontend, migraciones, pruebas, `docs/`, especificaciones y constitución vigente. No se modificó código de aplicación ni se operó sobre Proxmox, SMTP o la base de datos reales. Se conservaron las eliminaciones previas de los dos documentos de seguimiento.

**Evaluación general.** El portal tiene un núcleo avanzado: roles, titularidad por cátedra, pedidos con historial, catálogo administrable, reservas al aprobar, reintentos, bajas lógicas, métricas, vencimientos y recuperación de capacidad. La arquitectura por servicios permite corregir lo encontrado sin una reescritura. Para cerrar la práctica faltan principalmente controles consistentes en todas las rutas, un servicio PaaS/SaaS realmente utilizable, validación integrada y entregables finales. No corresponde convertir el cierre en una ampliación general del proyecto NAP.

**Verificaciones realizadas.**

| Comprobación | Resultado |
|---|---|
| Backend: `./venv/bin/python -m pytest -q` | **320 aprobadas y 1 fallida**, 147,77 s. La prueba fallida es `test_escenario_5_abm_templates_y_limite_constitucional`, en `backend/tests/test_quickstart_e2e.py:206`: esperaba rechazar una plantilla de 10 GB, pero recibió 201. |
| Frontend: `npm run build` | Correcto; JavaScript principal de **792,10 kB**, **233,72 kB gzip**, con advertencia de tamaño. |
| Frontend: `npm run lint` | Correcto con **16 advertencias**, entre ellas dependencias de hooks e imports/variables sin uso. |
| Dependencias Python: `pip check` | Sin requisitos incompatibles. Esto comprueba compatibilidad declarada, no ausencia de vulnerabilidades. |
| Alembic: `alembic heads` | Una cabeza: `8b9c0d1e2f3a`. No equivale a ejecutar las migraciones sobre PostgreSQL. |
| Reproducciones adicionales | Pedidos/métricas ajenos, login sin TOTP, operaciones antes del cambio inicial de contraseña, aprobación sin reserva, inicio de servicio vencido, overrides de configuración, degradación del último administrador, reserva durante despliegue y contadores de inactividad. |

El sandbox bloqueó la comunicación entre hilos usada por aiosqlite. La suite completa pudo ejecutarse fuera de él, con las fixtures existentes de SQLite en memoria, Proxmox simulado y correo capturado. Las reproducciones adicionales usaron SQLite síncrono con una adaptación async. El login con TOTP se comprobó invocando su función; en la prueba de inicio se sustituyó únicamente la espera de la tarea simulada. Estas reproducciones comprueban lógica y permisos, no concurrencia real ni integración física.

La prueba fallida parece **desactualizada respecto del comportamiento vigente**: `backend/tests/test_templates_admin.py:33` y `backend/tests/test_templates_edicion.py:80` esperan aceptar discos grandes, y la constitución actual no mantiene ese límite por plantilla. Resolver la contradicción contra el alcance acordado; no reintroducir un límite antiguo solo para poner la suite en verde. El límite de disco del propio portal es un asunto distinto.

**Prioridades.** P0: corregir antes de habilitar uso compartido por cátedras. P1: resolver antes de aceptar el prototipo y demostrarlo. P2: mejoras acotadas de operación, eficiencia o experiencia. Son prioridades del proyecto, no puntuaciones CVSS.

**A01 · P0 · Una cátedra puede modificar pedidos ajenos.**

Evidencia: [endpoint genérico](../backend/app/routers/pedidos.py#L457) y [permisos de la transición](../backend/app/services/pedido_service.py#L697). `PATCH /pedidos/{id}/estado` exige autenticación, pero `cambiar_estado()` solo restringe ciertos destinos al rol administrador; no comprueba la pertenencia del pedido. Desde `requiere_ajuste`, otra cátedra puede pasar el pedido a `cancelado` o `solicitado`. La respuesta también permite conocer su detalle/historial. Se reprodujo una cancelación ajena con HTTP 200.

Acción: autorizar sobre el objeto dentro del servicio central; limitar la ruta genérica o reemplazarla por las operaciones específicas existentes. Probar dos cátedras distintas y todos los destinos accesibles al docente, incluyendo recursos dados de baja.

**A02 · P1 · Una ruta permite aprobar sin reservar capacidad.**

Evidencia: [transiciones del sistema](../backend/app/services/pedido_service.py#L66), [cambio directo de estado](../backend/app/services/pedido_service.py#L714) y [aprobación con reserva](../backend/app/services/pedido_service.py#L176). `SOLICITADO → APROBADO` no está protegido frente al endpoint genérico. Un administrador puede aprobar sin pasar por el cálculo de capacidad, validación de plantilla ni reserva. Reproducido: HTTP 200 y CPU/RAM/disco reservados en cero.

Acción: permitir esa transición exclusivamente mediante `aprobar_pedido()`. La máquina de estados debe garantizar tanto el destino válido como los efectos obligatorios de cada operación.

**A03 · P1 · El segundo factor y el cambio inicial no se exigen en la API.**

Evidencia: [login](../backend/app/routers/auth.py#L64), [usuario autenticado](../backend/app/routers/auth.py#L26), [activación TOTP](../backend/app/routers/auth.py#L124) y [modal frontend](../frontend/src/App.jsx#L67). El login emite JWT tras verificar únicamente contraseña, aunque `totp_habilitado` sea verdadero. El cambio inicial obligatorio es una barrera de interfaz: una cuenta con `debe_cambiar_password=True` conserva permisos de API completos. Ambos comportamientos se reprodujeron.

Acción: desafío TOTP antes de emitir la sesión completa, autenticación reforzada al sustituir un secreto ya activo y sesión restringida mientras falte cambiar la contraseña. Agregar límites de intentos al login/TOTP; no se encontró un mecanismo en el código revisado. Estas medidas corresponden a la protección de autenticación descrita por [OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

**A04 · P1 · El despliegue conserva valores inseguros de desarrollo.**

Evidencia: [startup](../backend/scripts/startup.sh#L14), [bootstrap del administrador](../backend/scripts/seed_admin.py#L32), [Compose](../docker-compose.yml#L37) y [configuración](../backend/app/config.py#L8). El arranque ejecuta siempre seeds con contraseñas predeterminadas conocidas, sin exigir cambio inicial; además hay claves JWT de respaldo conocidas, TLS de Proxmox deshabilitado y usuario predeterminado `root@pam`. PostgreSQL y Mailpit publican puertos en todas las interfaces por defecto. Esto describe lo que configura el repositorio, no demuestra la exposición del despliegue real ni los privilegios efectivos del token.

Acción: bootstrap único con secreto externo, seeds de prueba condicionados a desarrollo, configuración productiva que rechace secretos de ejemplo, TLS verificado y permisos mínimos de API. Restringir interfaces publicadas. Revisar credenciales fijas de `backend/scripts/setup_usuarios_solicitados.py` y rotarlas si se usaron; sus valores se omiten aquí.

**A05 · P1 · La capacidad desaparece de la contabilidad durante el despliegue.**

Evidencia: [reserva vigente](../backend/app/services/capacidad_service.py#L80), [entrada a despliegue](../backend/app/services/orquestacion_service.py#L585), [commit del cambio](../backend/app/services/pedido_service.py#L733) y [registro del servicio](../backend/app/services/orquestacion_service.py#L498). La reserva cuenta solo mientras el pedido está `APROBADO`. Al pasar a `EN_DESPLIEGUE`, se confirma el cambio antes de que exista el `Servicio`, y ningún componente lo cuenta. Otro worker o una petición que entre durante los commits puede aprobar sobre ese saldo artificialmente libre. Un fallo parcial puede prolongar el problema mientras exista un contenedor sin adoptar.

Reproducción determinista de la consulta real: un pedido aprobado reserva `{vcpus: 2, ram_mb: 512, storage_gb: 4}`; cambiarlo a `EN_DESPLIEGUE`, sin crear servicio, hace que `_reservado()` devuelva ceros. No se midió una carrera contra PostgreSQL.

Acción: conservar el compromiso durante todo el aprovisionamiento y hasta su conversión atómica en consumo; reconciliar los errores parciales antes de liberar. Comprobar también una reserva caducada cuyo job aún no se ejecutó: la consulta deja de contarla, pero el despliegue solo verifica el estado `APROBADO`. Validar estado y vigencia dentro de la operación protegida.

**A06 · P1 · La capacidad física no corresponde necesariamente al destino real.**

Evidencia: [cálculo físico](../backend/app/services/capacidad_service.py#L70) y [distinción de storage que ya reconoce otro router](../backend/app/routers/proxmox.py#L100). La aprobación suma `maxdisk` de nodos, mientras el despliegue elige un almacenamiento como `local-lvm` u otro configurado. El propio router aclara que el disco raíz del host no representa el almacenamiento de los contenedores. También se suma RAM/CPU global y se resta solo lo registrado por el portal: falta representar la carga ajena y el margen del sistema anfitrión. Que el clúster tenga saldo agregado no garantiza que quepa en el nodo elegido por menor CPU.

Acción: usar almacenamiento elegible real y capacidad del nodo de destino, contemplar recursos ajenos al portal y reservar margen operativo. Si hay almacenamiento compartido, contar su capacidad una sola vez. Mostrar al administrador qué fuente y destino sustentan la aprobación.

**A07 · P1 · Encender evita controles que existen en reactivar.**

Evidencia: [inicio](../backend/app/services/orquestacion_service.py#L738) y [reactivación](../backend/app/services/inactividad_service.py#L212). `/start` acepta un servicio pausado, comprueba que no esté ya encendido y lo inicia sin controlar capacidad ni vencimiento. Se reprodujo el arranque de un servicio pausado y vencido con HTTP 200. La vía `/reactivar` revisa capacidad, pero esa verificación tampoco está protegida por el bloqueo común de capacidad.

Acción: unificar inicio y reactivación bajo una sola operación con autorización, vigencia, capacidad, bloqueo y registro histórico. Un servicio detenido también deja de contar CPU/RAM; por eso volver a encenderlo requiere el mismo control. Probar dos inicios concurrentes con capacidad para uno solo.

**A08 · P1 · Los overrides pueden romper identidad, recursos e aislamiento.**

Evidencia: [mezcla de configuración](../backend/app/services/orquestacion_service.py#L289). `config.update(template.config_extra)` ocurre después de fijar VMID, recursos reservados y `unprivileged=1`. Se reprodujo un cambio de VMID, RAM de 512 MB a 65536 MB y contenedor privilegiado. La fila del servicio conserva los valores anteriores, por lo que contabilidad, adopción y baja pueden apuntar al recurso equivocado. Es un problema de integridad accesible mediante configuración administrativa, no una escalada demostrada desde el rol docente.

Acción: lista permitida de opciones y campos de identidad/recursos protegidos. Validar los overrides con un esquema tipado, límites positivos y reglas de red; volver a imponer las invariantes al construir la configuración final.

**A09 · P1 · PaaS/SaaS todavía no asegura un servicio utilizable.**

Evidencia: [creación LXC](../backend/app/services/orquestacion_service.py#L465), [datos de acceso](../backend/app/services/orquestacion_service.py#L495) y [postcondiciones CU01](nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md#L13). El flujo crea un contenedor a partir de `ostemplate`; el código no instala/configura las aplicaciones solicitadas. Una imagen preparada externamente podría cubrir esa instalación, pero debe acreditarse. La URL se fabrica como `http://{hostname}.utn.local` y el supuesto acceso es una frase fija, sin comprobar DNS, cuenta ni aplicación. La IP se descubre posteriormente al capturar métricas; no se entrega como parte garantizada del aprovisionamiento.

Acción de cierre: preparar un catálogo pequeño, idealmente un ejemplo PaaS y uno SaaS si se mantienen ambos modelos, con imágenes/procedimientos reproducibles. Resolver IP/puerto/URL y acceso real; comprobar salud de la aplicación desde la red de los alumnos antes de informar que está disponible. El portal puede aceptar pedidos de software libre, pero su aprovisionamiento debe limitarse a lo que el administrador tenga preparado y validado.

**A10 · P1 · La vigencia prometida no tiene semántica completa.**

Evidencia: [fechas enviadas](../frontend/src/components/NuevoPedidoModal.jsx#L155), [vencimiento desplegado](../backend/app/services/orquestacion_service.py#L490), [valor por defecto](../backend/app/services/vencimiento_service.py#L28) y [CU01](nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md#L39). Si no hay `vigencia_hasta`, el servicio vence a los 180 días, independientemente de primer/segundo cuatrimestre o anual. `vigencia_desde` no programa ni limita la activación. El reenvío ofrece personalizado, pero no campos para sus fechas y el backend conserva las fechas no enviadas.

Acción: una función única que resuelva períodos académicos a fechas explícitas, valide rango y calendario y defina qué ocurre antes del inicio. Al cambiar el tipo, limpiar o recalcular fechas incompatibles. Presentar la fecha efectiva al docente y al administrador.

**A11 · P1 · Aprovisionar puede bloquear todo un worker.**

Evidencia: [espera de creación](../backend/app/services/orquestacion_service.py#L465), [espera de eliminación](../backend/app/services/orquestacion_service.py#L854), [polling síncrono](../backend/app/services/proxmox_client.py#L68) y [SMTP síncrono](../backend/app/services/orquestacion_service.py#L356). Se llama a proxmoxer y a `esperar_task()` desde funciones async; la espera incluye `time.sleep` y puede durar hasta 180 s. Los correos de despliegue también se despachan directamente en ese camino, aunque otros eventos usan `BackgroundTasks`. El impacto potencial alcanza otras peticiones atendidas por ese mismo event loop.

Acción: trasladar I/O bloqueante a hilos o un cliente async, con tiempos límite. Ya existe un ejemplo útil en `esperar_accion()` mediante `asyncio.to_thread`. Para este prototipo no es necesario introducir una cola distribuida: primero corregir las llamadas bloqueantes y, si se necesita sobrevivir al reinicio del proceso, persistir/reconciliar la operación. El comportamiento está respaldado por la [documentación de concurrencia de FastAPI](https://fastapi.tiangolo.com/async/#other-utility-functions).

**A12 · P1 · Los trabajos automáticos informan pausas sin confirmar el apagado.**

Evidencia: [inactividad](../backend/app/services/inactividad_service.py#L161) y [vencimiento](../backend/app/services/vencimiento_service.py#L114). Llaman a `stop_lxc()` y guardan inmediatamente `PAUSED`, pero Proxmox devuelve una tarea cuyo resultado todavía puede fallar. Así puede liberarse capacidad contable sobre un contenedor que continúa ejecutándose. Además, el vencimiento no conserva la misma marca de pausa que inactividad, lo que merece cubrirse al reconciliar estados.

Acción: esperar y verificar la tarea antes de cambiar el estado y liberar capacidad; registrar fallos y reintentar de forma idempotente. Evitar agregar una nueva entrada idéntica de vencimiento cada hora para un servicio ya pausado y vencido.

**A13 · P2 · El cálculo de inactividad suma contadores acumulativos.**

Evidencia: [captura de red](../backend/app/services/metricas_service.py#L55) y [evaluación](../backend/app/services/inactividad_service.py#L60). Se guardan los contadores acumulados de Proxmox y después se suman todas las muestras de siete días como si fueran tráfico de cada intervalo. Reproducción: 672 muestras con contador constante de 400000 bytes y CPU 0 producen 268800000 bytes de supuesto tráfico y se clasifican `con_uso`, aunque el incremento real sea cero.

Acción: calcular deltas con tratamiento de reinicios del contador y usar cobertura por intervalos temporales. Contar filas permite que capturas manuales o desde la UI inflen artificialmente la cobertura.

**A14 · P2 · Fuga puntual de métricas y pérdida del último administrador.**

Evidencia: [último snapshot](../backend/app/routers/metricas.py#L162) y [edición de rol](../backend/app/routers/usuarios.py#L185). La última métrica de un servicio se devuelve sin `es_visible()`, a diferencia de su historial; se obtuvo HTTP 200 para una cátedra ajena. La protección del último administrador solo cubre desactivación/retiro, no cambiarle el rol; se reprodujo la degradación del único admin y el posterior 403 en administración.

Acción: aplicar autorización uniforme en todas las lecturas de métricas y extender el guard del último administrador a los cambios de rol, dentro de una transacción.

**A15 · P2 · La interfaz ofrece QEMU y el despliegue puede quedar transitorio.**

Evidencia: [selector de plantillas](../frontend/src/components/TemplatesAdmin.jsx#L148), [validación LXC](../backend/app/services/orquestacion_service.py#L409) y [cambio previo de estado](../backend/app/services/orquestacion_service.py#L585). Se puede crear una plantilla QEMU, pero el orquestador solo acepta LXC. La comprobación ocurre después de confirmar `EN_DESPLIEGUE` y fuera del bloque que registra `ERROR`: un intento puede dejar el pedido en ese estado sin operación real en marcha.

Acción: validar compatibilidad antes de cambiar de estado y ofrecer solo capacidades soportadas. Para la práctica, acordar explícitamente prototipo LXC o implementar QEMU si continúa siendo requisito del supervisor.

**A16 · P2 · Dependencia instalada afectada por un aviso de seguridad.**

El entorno resuelve FastAPI 0.115.14 y Starlette 0.46.2. Esta última está afectada por **CVE-2025-54121 / GHSA-2c2j-9gv5-cj73**, de severidad moderada: el procesamiento de archivos multipart grandes puede bloquear el hilo de eventos al trasladar datos a disco. La versión corregida indicada es 0.47.2. [Aviso del mantenedor](https://github.com/Kludex/starlette/security/advisories/GHSA-2c2j-9gv5-cj73).

El login usa formularios y FastAPI ejecuta `request.form()` en ese camino: hay una superficie a revisar aunque no se declaren endpoints de subida. Esto es una inferencia del código y del aviso; no se realizó una prueba de denegación de servicio. FastAPI instalado exige Starlette `<0.47.0`, por lo que no basta con forzar la dependencia transitiva: actualizar la combinación compatible y ejecutar las pruebas. No se realizó un barrido completo de advisories de todos los paquetes ni se afirma que este sea el único aviso aplicable.

**Mejoras concretas de interfaz.** Revisión de código y contratos; no se realizó una inspección visual de una sesión real con datos del clúster.

| Prioridad | Hallazgo y evidencia | Mejora propuesta |
|---|---|---|
| P1 | La evaluación en [AprobarPedidoModal.jsx:62](../frontend/src/components/AprobarPedidoModal.jsx#L62) corresponde al pedido original; cambiar plantilla/overrides no la recalcula. La justificación solo aparece si la evaluación original excedía capacidad. | Evaluar la selección actual o permitir justificación al recibir `excede_capacidad`; mostrar costo efectivo y actualizar token. Hoy puede quedar bloqueado un aumento de recursos que el backend exige justificar. |
| P1 | [NuevoPedidoModal.jsx:52](../frontend/src/components/NuevoPedidoModal.jsx#L52) no reinicia el modelo al reabrir, pero selecciona la primera plantilla IaaS. Backend valida existencia, sin coherencia modelo/plantilla. | Reiniciar el formulario de manera coherente y validar la combinación también en API. |
| P1 | [ReenviarPedidoModal.jsx:37](../frontend/src/components/ReenviarPedidoModal.jsx#L37) permite vigencia personalizada sin fechas. | Reutilizar los controles de vigencia y definir cómo eliminar valores anteriores; conectar con A10. |
| P2 | [Servicios.jsx:72](../frontend/src/pages/Servicios.jsx#L72) y [Pedidos.jsx:215](../frontend/src/pages/Pedidos.jsx#L215) usan el catálogo activo para rotular registros históricos. Retirar una plantilla hace perder nombre/modelo en la UI. | Incluir identificación mínima de plantilla y modelo en las respuestas de servicio/pedido, independientemente del catálogo disponible para solicitudes nuevas. |
| P2 | [Filtro IaaS](../frontend/src/pages/Servicios.jsx#L247) también acepta todo servicio `lxc`/`qemu`; SaaS/PaaS ejecutados sobre LXC aparecen en IaaS. | Separar modelo de servicio lógico de tecnología de virtualización. |
| P2 | [Carga de Servicios](../frontend/src/pages/Servicios.jsx#L65) ignora rechazos de `allSettled`; otros listados solo registran fallos en consola. | Distinguir carga, vacío, error y datos anteriores; ofrecer reintento y hora de última actualización. |
| P2 | [Dialog compartido](../frontend/src/components/ui.jsx#L74) sin semántica de diálogo ni gestión completa del foco; tarjetas de [Métricas](../frontend/src/pages/Metricas.jsx#L191) solo responden al clic. | `role=dialog`, `aria-modal`, título asociado, foco inicial/restauración y navegación de teclado; usar botones semánticos. Asociar labels a campos. |
| P2 | Guardar en Usuarios/Cátedras llama al handler fuera del formulario y puede esquivar validación HTML. Copiar acceso muestra éxito sin esperar Clipboard. | Usar submit asociado al formulario y esperar el resultado de la copia antes de confirmar. |

Conviene concentrar el trabajo visual en formularios fiables, estados de error claros, acciones en curso y accesibilidad compartida. No se encontró una necesidad que justifique rediseñar todo el portal antes de entregar.

**Rendimiento y esquema de base de datos.**

| Prioridad | Problema observado | Cambio acotado recomendado |
|---|---|---|
| P1 | Bloqueo de event loop durante creación/baja/consultas de infraestructura y correo. | A11; corregir antes de intentar escalar con más workers. |
| P2 | [Métrica](../backend/app/models/metrica.py#L9) sin índices de consulta. Historial y última muestra filtran por servicio y ordenan por fecha; resumen ejecuta una consulta adicional por servicio. | Índice compuesto `(servicio_id, timestamp DESC)` y última muestra por servicio en una consulta, mediante ventana o `DISTINCT ON` en PostgreSQL. |
| P2 | Crecimiento indefinido de snapshots y capturas desde GET en [servicios.py:204](../backend/app/routers/servicios.py#L204). No se encontró retención/compactación. | Separar lectura de captura, fijar cadencia y conservar detalle por un plazo definido con agregados históricos. A 15 minutos, 100 servicios generan unos **3,5 millones de filas/año**, sin contar capturas adicionales. No destruir el historial académico al definir retención. |
| P2 | Listados de pedidos/servicios sin paginación; cátedras consulta titulares por fila. [Resumen de métricas](../backend/app/routers/metricas.py#L105) tiene patrón N+1. | Paginación y filtros en servidor; cargar titulares relacionados en lote; consultar métricas en conjunto. Confirmar con `EXPLAIN ANALYZE` en PostgreSQL antes/después. |
| P2 | [Servicios](../frontend/src/pages/Servicios.jsx#L65) consulta cinco endpoints cada 10 s, incluyendo catálogo, cátedras y configuración estables. | Refrescar solo estado/métricas; cargar referencias al entrar o invalidarlas tras cambios; evitar acumulación de peticiones lentas. |
| P2 | Todas las páginas se importan al inicio en [App.jsx:3](../frontend/src/App.jsx#L3); bundle principal cercano a 792 kB. | Carga diferida por ruta y de las gráficas, sin reemplazar la biblioteca visual. |
| P2 | [Resumen](../backend/app/routers/metricas.py#L110) compara valores de estado con `RUNNING`/`STOPPED`, pero el enum devuelve `running`/`stopped`. | Comparar con miembros del enum. Hoy no se consulta `maxdisk` real y se conserva el máximo asignado. |

Para el esquema recomiendo una migración pequeña de integridad y consultas, no cambiar de motor ni normalizar todos los JSON:

| Área | Recomendación y fundamento |
|---|---|
| Índices operativos | Además del índice de métricas, considerar pedidos `(catedra_id, created_at DESC)` y servicios `(catedra_id, deployed_at DESC)` filtrados por vigentes; historiales `(pedido_id, created_at)` y `(servicio_id, created_at)`. Los índices actuales sobre `deleted_at IS NULL` no ordenan por cátedra/fecha. Elegir según consultas y volumen. PostgreSQL [no crea automáticamente índices en el lado referenciante de una FK](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-FK). |
| Invariantes | Validación Pydantic de CPU/RAM/disco positivos, reserva no negativa, fechas ordenadas y relaciones requeridas según tipo. Añadir `CHECK` en BD para lo representable. Hoy los diccionarios de opciones admiten valores sin esquema y los modelos no contienen esas restricciones. |
| Identidad de infraestructura | Evaluar unicidad parcial de VMID para servicios vigentes y no nulos; si se admiten varios clústeres, la clave es `(cluster_id, vmid)`. La unicidad actual de `pedido_id` evita doble servicio por pedido, pero no dos registros para el mismo recurso físico. Acompañarlo con reconciliación; una constraint por sí sola no coordina la creación externa. |
| Fechas | Guardar y serializar instantes en UTC con zona y convertir en UI; distinguir una fecha lectiva de un instante. Los `DateTime` sin zona y `utcnow()` generan ambigüedad y numerosas advertencias. Introducir la conversión con migración y revisar los datos existentes. |
| Modelo lógico | Persistir/exponer `modelo_servicio` del servicio o una instantánea coherente, sin depender de una plantilla mutable para reinterpretar el historial. Mantener separados el pedido de alta original y los pedidos posteriores de renovación; no eliminar relaciones distintas solo porque conectan las mismas tablas. |
| Datos de acceso | `credenciales_acceso` está declarado JSON en BD/modelo, pero se llena y expone como cadena. Definir un contrato consistente para URL, puerto, usuario y método de acceso. Si se incorporan secretos reales, limitar su exposición a lecturas necesarias y proteger su almacenamiento; no devolverlos automáticamente en cada listado. |
| Migraciones | `EstadoPedido`/`TipoPedido` usan `native_enum=False` en modelos, mientras la cadena histórica crea enums nativos. Las etiquetas coinciden y no se demostró una falla operativa, pero `create_all()` de tests y Alembic no producen el mismo esquema. Unificar la decisión y probar el upgrade real en PostgreSQL vacío y desde una revisión anterior. |

**Qué exige la documentación y qué falta para la práctica.** El plan individual de PS, el CU01 y las decisiones posteriores deben leerse juntos. Las listas de tareas marcadas como hechas no sustituyen una comprobación de comportamiento, y las ideas del paper no son automáticamente requisitos del portal.

| Compromiso y fuente | Estado del repositorio | Pendiente concreto de cierre |
|---|---|---|
| Pedidos, catálogo, historial y roles: [plan, objetivos](planDeTrabajo2.md#L37), [CU01](nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md#L32) | Implementados, con fallos A01–A03 y A14. | Corregir rutas alternativas y demostrar ajuste, reenvío, rechazo y aprobación con dos roles. |
| Entornos por cátedra y capacidad | Implementados con reservas y titularidad; el modelo cambió explícitamente. | Corregir A05–A08 y sincronizar documentos. La [constitución vigente](../.specify/memory/constitution.md#L159) prohíbe cuotas fijas por cátedra: **no reintroducirlas** para satisfacer un plan antiguo. |
| VM y LXC: [plan](planDeTrabajo2.md#L44) | Aprovisionamiento LXC; QEMU no soportado. | Acordar prototipo LXC o completar VM si sigue siendo obligatorio. Eliminar oferta de capacidades que no funcionan. |
| Servicios PaaS/SaaS: [pruebas prometidas](planDeTrabajo2.md#L100), [CU01](nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md#L23) | Formularios/categorías y contenedor; acceso y aplicación no garantizados. | Catálogo mínimo utilizable con acceso comprobado desde un cliente alumno; resolver A09. |
| Vigencia y renovación: [CU01](nuevaDoc/solicitudes-catedras/CU01_solicitud_recursos.md#L39) | Renovación/vencimiento existen; períodos lectivos incompletos. | Resolver A10 y probar renovación aceptada/rechazada, vencimiento y conservación de datos. |
| Monitoreo y alertas: [plan](planDeTrabajo2.md#L89) | Métricas y visualizaciones existen. Hay avisos de pausa/vencimiento en [Servicios](../frontend/src/pages/Servicios.jsx#L583). No se encontró evaluador de umbrales ni alerta operativa por caída de aplicación. | Añadir una alerta básica real, con umbral, destino y recuperación definidos; corregir A12–A13. Correo de eventos de pedidos no cubre por sí solo alertas de recursos/caída. |
| Portal independiente desplegado: [plan](planDeTrabajo2.md#L70), [capacidad del contenedor](implementation_plan.md#L20) | Docker/Compose y documentación técnica existentes; configuración de desarrollo. | Registrar despliegue productivo en LXC, URL/DNS/TLS, arranque, actualización, backup/restauración y espacio ocupado. Resolver A04 y configuración del frontend. |
| Integración Proxmox/TrueNAS: [plan](planDeTrabajo2.md#L98) | Las pruebas automatizadas usan fakes; no se identificó acta final de validación real. | Ejecutar y documentar pruebas con PostgreSQL y clúster real. La ausencia de actas en el repo no demuestra que nunca se hayan hecho pruebas externas. |
| Informe individual, manual docente, manual administrador y arquitectura: [plan](planDeTrabajo2.md#L104) | Hay planes, paper, specs, README y guía Docker; faltan entregables finales identificables con ese alcance. `docs/diagrama_bd.md` está vacío. | Preparar esos entregables y esquema actualizado con entidades, relaciones, restricciones y migraciones. No hace falta un generador nuevo. |
| Red, pools, HA y almacenamiento: [paper](paper.md#L47) | La configuración real no es verificable desde este repo; gran parte corresponde al equipo de infraestructura. | Obtener inventario, mapa de red/storage, permisos de consola y prueba de recuperación de los compañeros. No atribuir al software todo el proyecto de nube. |
| Mikrotik y autenticación institucional: [plan](planDeTrabajo2.md#L47) | Integraciones condicionadas a viabilidad, no encontradas en código. SMTP institucional es una capacidad distinta del SSO. | Documentar evaluación y postergación; no hacerlas bloqueantes si se conserva el alcance condicional. |
| Ceph, Kubernetes, OpenTofu, Prometheus/Grafana y evaluación pedagógica | Referencias/estado del arte o alcance más amplio del paper. | Trabajo futuro salvo acuerdo nuevo. No se encontró QoS como requisito de esta PS. |

La constitución v3 admite una **excepción explícita para la consola Proxmox del contenedor propio**, delimitada por permisos/pool de cátedra. No corresponde declarar incumplimiento por el mero enlace a Proxmox ni volver a implementar el relay de consola abandonado. Sí corresponde acreditar el aislamiento de esas identidades en la infraestructura.

Hay documentación contradictoria para cerrar: plan/implementation plan todavía hablan de cuotas fijas y de evitar toda interacción con Proxmox, frente a decisiones posteriores; el paper describe tres nodos de 64 GB y el plan de implementación cinco de aproximadamente 8 GB. Usar inventario y alcance reales en la entrega. El DOCX `Paper NAP - v1.0.docx`, leído por su contenido XML, coincide sustancialmente con `docs/paper.md` y no reemplaza el informe individual de PS.

**Detalle de despliegue frontend a corregir.** [api.js:3](../frontend/src/services/api.js#L3) usa `import.meta.env.VITE_API_URL` o `localhost:8001`. [frontend.dockerfile:25](../frontend.dockerfile#L25) compila sin recibir esa variable como argumento de build; Compose la define al ejecutar el contenedor. En la imagen estática eso no modifica el JavaScript compilado, que puede terminar apuntando al localhost de cada visitante. Preferir `/api` bajo el mismo origen con proxy, o pasar configuración explícita al compilar/arrancar mediante un mecanismo diseñado para ello. Probar desde otra computadora, no solo desde el host del proyecto.

**Orden de trabajo recomendado.**

1. **Cerrar controles centrales:** autorización por objeto, rutas de aprobación/inicio, autenticación, reservas durante despliegue y overrides. Añadir regresiones para los escenarios reproducidos. Resultado esperado: ninguna ruta alternativa evita las mismas reglas.
2. **Conseguir una demostración funcional completa:** templates PaaS/SaaS preparados, acceso real, salud y vigencia efectiva. Resolver los tres formularios que pueden bloquearla y limitar QEMU si sigue fuera de alcance.
3. **Asegurar operación del prototipo:** espera de tareas automáticas, I/O sin bloquear el worker, capacidad del storage/nodo real, alerta básica y configuración de despliegue. Añadir índice de métricas y corregir la inactividad.
4. **Validar y dejar evidencia:** suite coherente con política actual; integración real y concurrencia en PostgreSQL; recorrido de aceptación con docente. Registrar resultado y limitaciones, no solo capturas de pantallas.
5. **Entregar documentación:** informe, manuales, modelo de datos, despliegue/mantenimiento y decisiones de alcance. Completar datos personales todavía vacíos del plan formal cuando corresponda a la presentación.

Como planificación orientativa, reservar varios bloques cortos de corrección y al menos una sesión coordinada con infraestructura; la duración del aprovisionamiento real depende de la disponibilidad de imágenes, DNS y accesos. No es defendible dar un porcentaje de avance ni una fecha cierta de finalización solo a partir de las tareas marcadas.

**Criterios mínimos de aceptación para la entrega.**

- Dos cátedras no pueden consultar ni modificar datos de la otra, usando tampoco endpoints alternativos.
- Una aprobación compromete capacidad válida y la mantiene contabilizada hasta servicio confirmado o liberación reconciliada; dos operaciones concurrentes no consumen el mismo saldo.
- Solicitud → ajuste/reenvío → aprobación → despliegue → acceso real → métricas → reinicio → renovación/vencimiento → baja conserva trazabilidad y datos según corresponda.
- Un fallo de tarea Proxmox no se comunica como éxito; un reintento recupera el recurso propio sin duplicarlo.
- Un alumno puede usar el servicio de ejemplo desde la red prevista con los datos entregados, sin necesitar acceso administrativo al portal.
- La alerta básica funciona, el portal se puede reiniciar/actualizar y una copia de la BD se puede restaurar.
- Pruebas, límites conocidos, cambios de alcance y manuales quedan vinculados al informe final.

Las decisiones a confirmar con el supervisor son concretas: alcance LXC frente a VM, catálogo mínimo PaaS/SaaS, calendario lectivo y aceptación del modelo vigente de capacidad. El resto de los hallazgos descritos son correcciones del comportamiento ya pretendido.
