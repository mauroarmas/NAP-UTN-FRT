# Investigación y decisiones técnicas — feature 009

Fecha: 2026-10-18. Base: [spec.md](spec.md), constitución 4.0.0 y código del repositorio. La investigación define el diseño; no acredita instalaciones, correcciones ni pruebas de aceptación ejecutadas.

## Incógnitas resueltas

| Incógnita inicial | Decisión |
|---|---|
| Acceso restringido, TOTP voluntario y recuperación | Sesiones revocables por propósito, cookie protegida, desafío de cinco minutos, códigos y recuperación asistida acotada. |
| Exclusión entre decisiones de capacidad | PostgreSQL, lock transaccional global existente, releer filas y un único registro de compromisos por destino. |
| Almacenamiento, recursos externos y doble conteo | Inventario por identidad/volumen; separación de capacidad lógica y espacio físico de cada storage elegible. |
| Reinicio y tareas externas inciertas | Registro duradero de operaciones, UPID, propiedad verificable, leases y reconciliación antes de repetir. |
| Calendario y renovaciones discontinuas | Períodos aprobados independientes, fechas locales copiadas e intervalos UTC con fin exclusivo. |
| Preparar PaaS/SaaS sin imágenes existentes | Construir rootfs LXC saneados; personalizar con runner de infraestructura de operaciones fijas. |
| Red, credenciales y entrega | Perfiles institucionales permitidos; descubrir/verificar dirección real; secretos cifrados y acceso autorizado separado. |
| Alertas, inactividad y volumen histórico | Captura por minuto independiente de lectores, deltas/cobertura, incidentes y resúmenes diarios. |
| Herramientas y responsabilidad de respaldo | Copias lógicas externas, archivos/claves necesarios, ejecución institucional y restauración separada comprobada. |
| UI, despliegue y validación | SPA existente, sesión consultada al servidor, diálogos accesibles y pruebas PostgreSQL además de dobles. |

No quedan decisiones funcionales pendientes. Versión real del clúster, capacidad disponible, rutas, DNS, certificados y destino institucional de copias son requisitos de habilitación del entorno, con comprobaciones concretas en [quickstart.md](quickstart.md); no se sustituyen por datos inventados.

## R01. Mantener el conjunto tecnológico y separar ejecución de respuesta HTTP

**Decisión:** conservar Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Alembic, proxmoxer 2.2, APScheduler 3.11 y React 19/Vite 8. El despliegue incorpora un proceso worker del mismo backend, activado por configuración; API y worker comparten PostgreSQL, sin Redis ni Celery. APScheduler del worker dispara reconciliación, captura y avisos; la API solo admite comandos y consulta resultados.

**Fundamento:** hoy los routers y servicios llaman código síncrono dentro de funciones async y las tareas largas están vinculadas a procesos HTTP. Pasar llamadas proxmoxer/SMTP/OpenSSH a ejecución acotada fuera del event loop, con timeout real del transporte, libera consultas. Cada tarea abre su propia AsyncSession; nunca se envía una sesión ORM a un hilo.

**Alternativas:** solo BackgroundTasks no asegura persistencia tras caída; agregar un broker introduce operación innecesaria para cien servicios. Un timeout de coroutine tampoco detiene un hilo que ya envió una orden: el resultado se reconcilia.

**Evidencia:** backend/app/services/orquestacion_service.py, proxmox_client.py, scheduler.py y main.py. Referencias: [FastAPI async](https://fastapi.tiangolo.com/async/), [BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/), [asyncio.to_thread](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread), [sesiones async y concurrencia](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks).

## R02. Autenticación propia, sesión revocable y factor opcional

**Decisión:** conservar verificación bcrypt compatible, rechazando nuevas contraseñas que excedan 72 bytes UTF-8 para evitar truncamiento silencioso. Separar cuatro propósitos de sesión: mfa_pending, onboarding, recovery y operativo. Cookie JWT HttpOnly/Secure/SameSite=Lax con sid, sub, versión y vencimiento; los permisos se consultan desde el usuario y titularidades actuales. No entregar JWT a JavaScript ni conservarlo en Web Storage.

La contraseña válida con factor activo inicia solo mfa_pending. TOTP confirmado habilita onboarding si falta cambio inicial, u operativo si está completo. Sin factor activo, contraseña definitiva basta. Una inscripción pendiente no sustituye el factor activo ni obliga a confirmar un alta cancelada. Último paso TOTP usado se consume de forma atómica contra replay.

Toda mutación autenticada exige Origin permitido y CSRF ligado a sid. Login exige Origin y cabecera X-NAP-Request; el proxy sirve SPA y API bajo una misma origin. Logout revoca en servidor. Cinco fallos por cuenta en quince minutos provocan espera de quince minutos; origen tiene límite independiente de treinta. La ventana es móvil y se serializa por clave estable en PostgreSQL, sin buckets fijos ni confianza en X-Forwarded-For ajeno al proxy.

**Alternativas:** mantener JWT operativo después de validar solo contraseña reproduce el hallazgo; bearer persistido en localStorage deja el secreto accesible a scripts; imponer 2FA contradice la decisión del usuario.

**Evidencia:** backend/app/routers/auth.py, utils/security.py; frontend/src/App.jsx, services/api.js. Referencias: [OWASP sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [PyOTP](https://pyauth.github.io/pyotp/), [almacenamiento de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## R03. Códigos, recuperación y secretos

**Decisión:** diez códigos aleatorios de alta entropía por generación, almacenados como hash y consumidos una sola vez. Contraseña más código concede recovery, limitado a sustituir TOTP; el secreto anterior sigue activo hasta confirmar el nuevo. Desactivar es una acción expresa diferente. Los cambios de contraseña/factor invalidan las sesiones anteriores. La recuperación asistida la autoriza un operador institucional desde CLI con actor, motivo y referencia de identidad: autorización opaca de 256 bits, cinco minutos y un uso, combinada con contraseña del titular; no crea cuentas auxiliares.

Secretos TOTP, credenciales de instancias y cargas que requieran reentrega se cifran con Fernet y keyring versionado externo a la base. JWT y cifrado utilizan claves distintas. Se declara cryptography como dependencia directa. El respaldo incluye custodia separada de las claves; sin ellas un dump no restaura accesos.

**Alternativas:** desactivar MFA por soporte o crear admin conocido convierten recuperación en bypass; guardar códigos reversibles no es necesario. Perder también la contraseña no autoriza resetearla como efecto colateral de recuperar el factor.

**Referencias:** [OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html), [Fernet y rotación](https://cryptography.io/en/latest/fernet/). La política voluntaria de la spec prevalece sobre recomendaciones generales de obligatoriedad.

## R04. Autorización y conservación de administración

**Decisión:** ampliar acceso_service como frontera común de pertenencia y permisos, aplicada antes de consultas sensibles, cambios y llamadas externas. Solo las acciones nombradas cambian pedidos; retirar PATCH de estado. Dentro del servicio transaccional, aprobar llama la misma transición central, reserva y registra historial. Las operaciones docentes permitidas sobre lo propio conservan su alcance.

Todo cambio que pueda quitar un administrador activo toma un advisory lock de administración y vuelve a contar dentro de la transacción. Reasignar una cátedra no mueve datos ni historia a otra persona. La siguiente petición usa titularidad actual.

**Alternativas:** esconder botones, usar rol del JWT como autoridad o proteger solo DELETE no evita llamadas directas ni degradaciones concurrentes.

**Evidencia:** routers/pedidos.py, routers/metricas.py::ultimo_snapshot, routers/usuarios.py, services/acceso_service.py. [OWASP autorización](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## R05. Compromiso atómico por destino, con inventario real

**Decisión:** ledger compromisos_capacidad como autoridad operativa; las cantidades autorizadas del pedido quedan como snapshot histórico. Toda admisión toma pg_advisory_xact_lock(4001), relee pedido/servicio bajo bloqueo de fila, obtiene inventario actual con límite de espera y confirma compromiso, transición, historial y operación en una transacción corta. Sin polling externo dentro de esa transacción.

Elegir nodo y storage elegibles al aprobar. CPU/RAM se evalúan por nodo con margen explícito para anfitrión; discos por pool local o compartido, incluyendo recursos externos, aunque sean QEMU. Un recurso propio contribuye una sola vez mediante la unión de su compromiso y lo observado por identidad; ante diferencia se retiene el máximo necesario hasta reconciliar. Una creación no materializada suma reserva, una pausa confirmada retiene disco y libera cómputo.

Storage exige rootdir, imagen disponible, nodo accesible y margen lógico/físico. El espacio físico libre ya descuenta volúmenes existentes: restarle de nuevo todos los discos propios duplicaría el descuento. Solo se descuenta la parte pendiente aún no representada físicamente. Un storage compartido se contabiliza una vez. Datos incompletos o inaccesibles bloquean la admisión con 502.

Token de evaluación firmado liga pedido/revisión, asignación efectiva, destino, fechas, definición y huella de inventario/compromisos. La confirmación vuelve a validar; cambiar el formulario invalida su evaluación. TTL inicial de evaluación: sesenta segundos. Sobreasignación exige administración y motivo, no saltea compatibilidad ni convierte una imposibilidad física en despliegue exitoso.

**Alternativas:** sumar maxdisk de nodos mide la raíz de anfitriones; sumar totales sin elegir destino oculta fragmentación; descontar únicamente recursos NAP ignora terceros. El lock global existente es suficiente a esta escala; dividirlo por destino agrega riesgo de orden de bloqueos.

**Límite:** el lock serializa decisiones NAP, no escrituras externas de Proxmox. Revalidar antes del envío y detectar deriva; la integración no ofrece transacción distribuida.

**Referencias:** [PostgreSQL 16 locks](https://www.postgresql.org/docs/16/explicit-locking.html), [Proxmox storage](https://pve.proxmox.com/wiki/Storage). Evidencia: capacidad_service.py y tests/conftest.py; SQLite no acredita advisory locks reales.

## R06. Operaciones duraderas y propiedad de recursos

**Decisión:** identidades_infraestructura reserva la identidad global del clúster y una marca UUID/nonce antes de crear; operaciones_infraestructura conserva comando, fase, UPID, actor, clave idempotente y resultado. Cada comando de infraestructura retorna 202 y una URL de operación.

Un worker reclama con SKIP LOCKED y lease/generación; confirma mediante comparación de dueño/generación. Guarda dispatch_started antes del POST externo. Si cae sin guardar UPID, el sucesor inspecciona identidad, marca, tareas y efecto antes de decidir. Nunca vuelve a enviar porque simplemente venció un lease. Un resultado incierto sigue abierto, conserva compromiso y bloquea órdenes incompatibles. El dueño viejo no puede borrar locks nuevos ni confirmar resultados locales. Decisiones sin Proxmox tienen su propio registro idempotente transaccional para reproducir respuestas sin duplicar pedidos, calendarios o períodos.

Crear requiere confirmar tarea y recurso; pausar requiere tarea y stopped; eliminar requiere tarea y ausencia. La salud de la aplicación es una condición adicional de entrega. Una respuesta tardía fuera de vigencia registra el recurso y solicita detención segura antes de liberar. Un fallo de health conserva identidad/datos para reparar sin recrear.

**Alternativas:** hostname coincidente no acredita propiedad; VMID solo tampoco; BackgroundTasks en memoria y liberación por timeout pueden duplicar recursos y capacidad. No se adopta ni elimina un recurso con marca ajena.

**Referencias:** [SELECT/SKIP LOCKED PostgreSQL 16](https://www.postgresql.org/docs/16/sql-select.html), [documentación oficial pct](https://github.com/proxmox/pve-docs/blob/master/pct.adoc). Evidencia: orquestacion_service.py, scheduler.py, vencimiento_service.py.

## R07. Fechas locales y períodos independientes

**Decisión:** calendario configurable por año, tres modalidades académicas y fechas personalizadas. Convertir cada fecha institucional con zoneinfo a UTC: inicio inclusivo y comienzo del día siguiente al fin como límite exclusivo. Copiar fechas y revisión al aprobar; cambios posteriores no mutan el compromiso.

Alta futura reserva ahora y caduca en min(fin_exclusivo, max(aprobación, inicio) + 24 horas). Expiración solo libera automáticamente si no hay dispatch iniciado; en caso contrario reconcilia. Llegar al inicio habilita la acción existente de despliegue, sin introducir inicio automático por fecha.

Cada renovación agrega un período al mismo servicio. Períodos contiguos permiten continuidad; un intervalo sin cobertura exige pausa confirmada al terminar el anterior. Aprobar una renovación registra sus condiciones mediante transición central, sin encender, recrear ni reservar otra alta. Desde el nuevo inicio, reactivación sujeta a capacidad; el disco permanece retenido. Una renovación pendiente nunca extiende cobertura.

**Alternativas:** extender vence_at hasta el nuevo fin cubriría indebidamente el receso; sumar 180 días inventa la decisión; 23:59:59 no expresa bien fin de día.

**Referencias:** [tipos temporales de PostgreSQL 16](https://www.postgresql.org/docs/16/datatype-datetime.html). Evidencia: pedido_service.py, orquestacion_service.py::_ejecutar_renovacion y vencimiento_service.py.

## R08. Definiciones reutilizables e imágenes saneadas

**Decisión:** separar perfil de recursos de definición versionada. Preparar Ubuntu 24.04 LTS para LXC, PostgreSQL 16 y BookStack v26.09.1 con PHP 8.3/MariaDB 10.11. La release BookStack fue publicada el 29-09-2026; el build congela commit, paquetes exactos y SHA-256 de imagen/receta. Actualizar una versión requiere otra validación y publicación.

Construir rootfs tar de aplicación con paquetes instalados y datos privados sin inicializar; sin contraseñas conocidas, APP_KEY, claves host, sesiones ni contenido de cátedras. Crear LXC no privilegiado usando el soporte ya presente de ostemplate. Personalizarlo por runner institucional limitado vía OpenSSH con hostkey fijada, forced-command y comandos fijos; no instalar Docker anidado ni inventar exec de Proxmox API.

El runner solo admite bootstrap/inspect/verify, verifica UUID/nonce, pool, VMID y digest. Entradas tipadas por stdin, sin shell/rutas/scripts arbitrarios. La marca de terminación y los secretos de cada instancia se reutilizan en reintentos; nunca se vacían bases o regeneran claves por repetir.

**Alternativas:** SSH a invitados con hostkey aceptada automáticamente pierde confianza; root SSH general al nodo amplía privilegios; clones dependientes del storage y capacidades nuevas OCI no verificadas agregan restricciones innecesarias.

**Referencias:** [pct oficial](https://github.com/proxmox/pve-docs/blob/master/pct.adoc), [instalación BookStack](https://www.bookstackapp.com/docs/admin/installation/), [release BookStack v26.09.1](https://github.com/BookStackApp/BookStack/releases/tag/v26.09.1). Detalles normativos en [definición](contracts/service-definition.schema.json) y [runner](contracts/guest-runner.md).

## R09. Accesos reales y alcance de BookStack

**Decisión:** red desde perfiles autorizados, dirección verificada mediante inspección y DNS/TLS institucionales. No construir enlaces ficticios. Credenciales por instancia, cifradas y reveladas solo por endpoint autorizado con no-store; listados y avisos no incluyen secretos. Linux crea napadmin con contraseña guest única y sudo local; root queda bloqueado, sin autologin. Su login de consola se prueba antes de entregar IaaS.

PostgreSQL usa base/rol propios sin SUPERUSER/CREATEROLE/REPLICATION, SCRAM y TLS, independiente del portal. BookStack usa MariaDB local y APP_KEY nueva por instancia. Docente administrador de esa aplicación; alumnos con cuentas individuales Viewer gestionadas allí, sin altas NAP, sin registro público ni lectura anónima. Usar almacenamiento local_secure para imágenes y verificar también adjuntos sin sesión.

La comprobación automática confirma conexión autenticada y función mínima. Cada instancia exige además prueba desde red prevista: en esta entrega operador realiza el recorrido y administración registra evidencia/endpoint/identidad mediante POST /servicios/{id}/verificar-acceso. Hasta entonces servicio no_verificada y pedido EN_DESPLIEGUE; la operación infra ya puede estar confirmada, sin quedar abierta por espera humana. La aceptación verifica publicación/lectura, permisos, revocación y persistencia en dos instancias de cada producto. Un /status o pg_isready exitoso no demuestra ese recorrido.

**Alternativas:** entregar credenciales genéricas o anunciar disponibilidad al encender el contenedor reproduce el hallazgo. BookStack permanece ejemplo provisional, sujeto al relevamiento posterior del libro virtual.

**Referencias:** [roles BookStack](https://www.bookstackapp.com/docs/user/roles-and-permissions/), [archivos protegidos](https://www.bookstackapp.com/docs/admin/upload-config/), [comandos BookStack](https://www.bookstackapp.com/docs/admin/commands/), [SCRAM PostgreSQL](https://www.postgresql.org/docs/16/auth-password.html).

## R10. Observaciones, avisos y rendimiento

**Decisión:** captura de estado/salud cada minuto para servicios conocidos, con concurrencia externa máxima inicial cuatro y una muestra válida por servicio/intervalo. GET no captura ni consulta Proxmox por fila. Consultas de últimas muestras por lote con índice compuesto; historial limitado a quinientos puntos y fechas explícitas.

Deltas de contadores BIGINT y uptime separan épocas; un reinicio o hueco no confirmado no genera tráfico negativo ni cobertura ficticia. Inactividad conserva ventana de siete días, 80 % de cobertura, CPU máxima menor a 5 %, tráfico de ventana menor a 1 MB y gracia de 48 horas. Cobertura usa intervalos distintos; si falta observación, no se pausa por inactividad.

Caída requiere dos observaciones negativas separadas al menos un minuto. CPU o RAM >90 % de asignación durante quince minutos exige cobertura completa de la ventana; recuperación tras dos normales separadas un minuto. Un incidente abierto por servicio/tipo y outbox con evento/destinatario/canal únicos impiden duplicar avisos lógicos. SMTP es entrega al menos una vez: Message-ID estable ayuda a identificar un posible duplicado tras respuesta perdida.

Conservar noventa días de detalle y resúmenes diarios sin caducidad, agregados antes de purgar. A un minuto, cien servicios pueden producir 12,96 millones de muestras en noventa días: la prueba de carga debe usar ese volumen, no solo cien filas. Resumen incluye cobertura, tiempos y asignación histórica para reconstrucción por cátedra.

**Alternativas:** quince minutos de cadencia no caracteriza una ventana sostenida de quince minutos; sumar contadores acumulados o contar filas acepta actividad/cobertura falsa; capturar por visitante multiplica costos. No introducir particionado antes de medir índices y consultas.

## R11. UI y operación verificable

**Decisión:** conservar pantallas y componentes, introducir estado explícito carga/vacío/error/anterior, recuperar perfil desde servidor, limpiar almacenamiento local antiguo y manejar JSON dañado. Formularios reinician al abrir y recalculan dependencias; cambiar asignación invalida evaluación. Filtros por modelo copiado en servicio, no por tecnología LXC ni catálogo mutable.

Dialog compartido usa semántica modal, foco inicial/retorno, tabulación contenida, fondo inerte y mensajes accesibles; tareas restringidas de habilitación no permiten navegar al portal operativo. Lazy loading de rutas y gráficas reduce el paquete inicial; medir antes/después. Incorporar Vitest/Testing Library para estados/formularios y Playwright para recorridos críticos y teclado.

**Alternativas:** rediseño completo y una biblioteca UI nueva no son necesarios. La accesibilidad y prueba con el responsable de una cátedra son verificaciones de aceptación, no afirmaciones deducidas del build.

**Referencias:** [WAI patrón modal](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [Vite carga async](https://vite.dev/guide/features.html#async-chunk-loading-optimization), [compatibilidad Node de Vite](https://vite.dev/guide/). Se fija Node 22 >=22.12 para la imagen frontend y se verifica su digest al implementar. Evidencia: components/ui.jsx, NuevoPedidoModal.jsx, AprobarPedidoModal.jsx, pages/Servicios.jsx y Metricas.jsx.

## R12. Migración, respaldos y entrega

**Decisión:** Alembic en etapas aditivas, preflight de duplicados/fechas/propiedad y backfill explícito; no borrar registros históricos ni inventar períodos legacy. Preservar factores activos y secretos con cifrado comprobado antes de retirar columnas en claro; invalidar JWT antiguos sin sid. Probar upgrade desde la revisión actual y creación desde cero en PostgreSQL.

Copias externas diarias con siete diarias y cuatro semanales, cifradas fuera del nodo de origen; backup previo a migración/actualización y ensayo de restauración antes de entrega. Es política inicial operativa, no un módulo NAP. Infraestructura asigna destino y operador en inventario de instalación. PostgreSQL: pg_dump -Fc más roles/configuración necesarios. BookStack: corte consistente MariaDB + .env/APP_KEY + imágenes/adjuntos/temas. Portal: datos y keyring externo necesario para descifrar. Restaurar primero en entorno separado, misma versión de aplicaciones, con automatismos/SMTP real deshabilitados hasta reconciliar.

RPO inicial de copias: hasta veinticuatro horas si el job terminó correctamente. Medir duración de restauración y registrar RTO observado. Comprobar checksum/código de salida; fallos visibles al operador. El portal no administra copias de aplicaciones. Antes de habilitar un portal restaurado, revocar sesiones/desafíos/códigos del corte, conservar factores activos y emitir códigos nuevos tras contraseña+TOTP o asistencia; cancelar bienvenidas pendientes sin reenviar secretos antiguos.

Bienvenida conserva secreto provisional únicamente cifrado y separado de payload/logs, ligado a cuenta y versión. Se elimina al entregar, cambiar contraseña o vencer su intento de entrega. SMTP simulado tampoco imprime cuerpos con contraseñas.

Dependencias se auditan con pip-audit y npm audit en implementación, usando avisos primarios del proveedor para aplicabilidad y pin de versiones corregidas. No se declara seguridad por ausencia de hallazgos en una corrida ni se actualiza todo el stack sin necesidad.

**Alternativas:** dump del portal no contiene libros ni bases PaaS; exportación de contenido BookStack no sustituye copia de configuración/usuarios/archivos; snapshots sin consistencia demostrada no acreditan restauración.

**Referencias:** [dump y restauración PostgreSQL 16](https://www.postgresql.org/docs/16/backup-dump.html), [backup BookStack](https://www.bookstackapp.com/docs/admin/backup-restore/).

## Ajustes posteriores al análisis de consistencia (2026-10-18)

- **R04 / C1**: corregir/reenviar/cancelar pedidos exige administración conforme a la constitución; docente crea/consulta pedidos, solicita renovación y opera servicios propios. Se deniega también una mutación docente de su pedido propio. **R04 / G1**: los guards NAP no revocan sesiones nativas. Se adopta el trámite de [console-access.md](contracts/console-access.md): bloqueo inmediato del alcance en el portal, operador institucional revoca ACL/sesiones y acredita prueba negativa, confirmación con revisión vigente, recién entonces cambio efectivo. Conservar otros pools legítimos; fallos mantienen pendiente sin transferencia. La capacidad efectiva de terminación es un gate previo a habilitar consola; no se supone una API PVE disponible ni se amplía el runner.
- **R09 / A1**: [evidence.md](contracts/evidence.md) define importación administrativa de JSON tipado, registro canónico inmutable en PostgreSQL y UUID/checksum. Evita referencias sin productor o resolución por URL libre. Su hash verifica integridad; el operador y la aceptación real de red siguen siendo declaraciones institucionales auditadas, distinguibles de simulaciones. Catálogo, acceso de instancia y consola comparten el registro.
- **R11 / I1**: SC-008 se acredita con Playwright sobre SPA compilada y diez contextos autenticados; medir desde navegación/filtro hasta resultado visible/utilizable, por recorrido, con errores incluidos. Datos: cien servicios/noventa días a un minuto (12,96M), despliegue simulado de al menos treinta segundos. El benchmark API no sustituye la medición del navegador. Protocolo reproducible y muestras en quickstart.
- **R12 / G2**: backend/pytest.ini solo recolecta backend/tests. Se añade configuración infra/pytest.ini y fixtures infra/conftest.py sin red, comando explícito para ambas suites infra y job CI dedicado. El cierre exige recolección no vacía y ejecución de runner e imágenes, sin clúster real.
