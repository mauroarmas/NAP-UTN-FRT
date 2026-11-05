# Modelo de datos — feature 009

Diseño para SQLAlchemy 2.0/Alembic/PostgreSQL 16. Amplía el modelo existente; no contiene migraciones ejecutables. Relaciones de cátedra, pedido y servicio se conservan. [Requisitos](spec.md) · [Decisiones](research.md) · [Contratos](contracts/operations.md).

## Convenciones e invariantes

- Identificadores existentes continúan como enteros. Sesiones, desafíos, operaciones e identidades externas usan UUID/identificadores aleatorios; códigos y autorizaciones se almacenan como hash.
- Instantes nuevos: TIMESTAMPTZ y UTC. Fechas del calendario: DATE con zona institucional IANA. API entrega instantes ISO 8601 con zona y fechas YYYY-MM-DD.
- Recursos de interfaz: vCPU enteras, RAM MiB y disco GiB. Cálculo interno de almacenamiento: bytes BIGINT, conversión 1 GiB = 2^30 bytes sin redondear a favor de la disponibilidad.
- JSON contiene snapshots y metadatos validados; no sustituye FK, restricciones o campos usados para concurrencia. JSONB puede utilizarse en PostgreSQL manteniendo variante JSON en las pruebas SQLite.
- Historia y evidencia son append-only. Ninguna cascada borra pedidos, servicios, períodos o consumo al retirar personas/cátedras/plantillas.
- Un único servicio operativo corresponde a cada pedido de alta. Una renovación apunta al servicio original y nunca crea otro.
- Compromisos, operaciones y vigencias son autoridades de sus respectivos dominios; los campos antiguos de reserva/vencimiento son snapshots o proyecciones, nunca segundos contadores mutables.

## 1. Usuario y autenticación

### usuarios — existente, extendida

Se conservan username único, email único opcional, nombre, password_hash, rol, activo, debe_cambiar_password y recibir_notificaciones_email.

| Campo nuevo o modificado | Tipo / regla |
|---|---|
| revision_admin | INTEGER >=1; control optimista de persona/cátedra al cambiar permisos; catedras también incorpora revision_admin. |
| identidad_consola / inventario_consola | TEXT nullable UNIQUE / enum desconocido, sin_identidad, asignada; usuario PVE individual verificado por operador y referencia institucional. Migración marca desconocido, nunca presume ausencia. Solo el importador institucional registra el vínculo; cambiar uno asignado exige revocar primero la identidad anterior mediante el trámite, sin borrar su historia. |
| auth_version | INTEGER >=1; invalida sesiones al cambiar credenciales, recuperar o retirar cuenta. |
| totp_secret_encrypted | TEXT nullable; cifrado autenticado con versión de keyring. Sustituye totp_secret tras migración comprobada. |
| totp_habilitado | BOOLEAN; nunca pasa a true por iniciar setup. Una inscripción pendiente vive en desafío. |
| totp_last_step | BIGINT nullable; último paso temporal aceptado; consumo indivisible. |
| recovery_generation | INTEGER >=0; solo la generación actual admite códigos. |
| habilitacion_inconsistente | BOOLEAN default false; marca factores activos sin secreto recuperable para recuperación asistida. No desactiva MFA. |

El rol de la cookie no es autoridad. Toda petición recupera usuario actual y titularidades desde catedras.titular_id. Toda mutación que pueda retirar el último administrador activo usa el mismo advisory lock administrativo y cuenta dentro de la transacción.

### sesiones_autenticacion — nueva

id aleatorio, usuario_id FK, proposito, auth_version, creada_at, expira_at, revoked_at, mfa_verified_at nullable. Propósitos: mfa_pending, onboarding, recovery, operativo. Secreto de sesión solo en cookie protegida; JWT incluye sid/sub/version/exp y se contrasta con esta fila.

Expiración inicial: operativo 60 minutos, onboarding 15 minutos, mfa_pending y recovery 5 minutos. Cambiar propósito rota sid y revoca el anterior. GET /auth/csrf deriva token ligado a sid; no hace falta almacenar el token completo. Índice usuario_id/expira_at; limpiar sesiones vencidas conforme a política de auditoría, separada de historia académica.

### desafios_autenticacion — nueva

id UUID, token_hash único si aplica, usuario_id FK, sesion_id FK nullable solo para autorización asistida aún no aceptada, tipo, secreto_pendiente_cifrado nullable, creado_at, expira_at, consumido_at, intentos y referencia de auditoría. Tipos: login_totp, enrollment, replacement, assisted_recovery.

Duración cinco minutos, un consumo, máximo una inscripción pendiente por cuenta/tipo. Reemplazar mantiene secreto activo hasta confirmación. Desafío de login exige la sesión mfa_pending que lo originó. Bloqueo de fila de usuario/desafío antes de validar último paso TOTP y consumir.

### codigos_recuperacion — nueva

id, usuario_id FK, generacion, codigo_hash, creado_at, consumido_at, invalidado_at. UNIQUE(usuario_id,generacion,codigo_hash). Diez por generación; valores completos solo en respuesta de generación con no-store. Consumir actualiza exactamente una fila disponible bajo el mismo bloqueo de usuario usado para regenerar/desactivar.

Recuperación por código consume el presentado y revoca sesiones previas; los restantes permiten reintento si vence la sesión recovery. Confirmar nuevo factor invalida todo el juego anterior. Recuperación asistida aceptada invalida también los códigos previos.

### intentos_autenticacion / eventos_seguridad — nuevas

- intentos_autenticacion: clave HMAC de cuenta normalizada u origen, clase, fallos_recientes con instantes de los últimos quince minutos, bloqueado_hasta y updated_at; UNIQUE(clase,clave) estable. Bloquear esa fila, descartar instantes fuera de la ventana móvil y comprobar el nuevo fallo dentro de una transacción; conservar hasta el umbral necesario, sin buckets fijos eludibles. Cuentas inexistentes tienen el mismo tratamiento y mensajes.
- eventos_seguridad: id, usuario_objetivo_id nullable, actor_usuario_id nullable, actor_institucional nullable, accion, resultado, motivo, referencia, creado_at, request_id. Sin contraseña, OTP, tokens o secretos. Recuperación CLI exige actor y referencia.

### cambios_acceso_consola — nueva

id UUID, accion (reasignar/retirar/desactivar/cambiar_rol), usuario_id FK, catedra_id FK nullable, revision_esperada, identidad_nativa, scopes_anteriores/propuestos JSON validado, cambio_propuesto JSON limitado a titular/rol/actividad/retiro, estado (pendiente/revocacion_fallida/completado), solicitada_por FK, solicitada_at, ultimo_error_seguro, evidencia_id UUID FK nullable, completada_at. No guarda tickets, cookies ni claves. Identidad nativa puede ser NULL solo si el inventario acredita que nunca tuvo acceso nativo.

Índice único parcial por usuario afectado para trámites abiertos y exclusión de cambios concurrentes sobre la misma cátedra. Los guards consultan bloqueos por alcance; retirar/desactivar/cambiar_rol bloquea toda la cuenta en el portal y revoca sus sesiones al admitir el trámite. El cambio académico/rol/actividad se aplica solo en la transacción final que verifica evidencia y revisión actual. No mantener locks DB esperando al operador. Revalidar último admin al admitir y completar, contando al admitir también las degradaciones/retiros pendientes para no bloquear simultáneamente a todos; ninguna mutación elude el trámite. Ver [protocolo](contracts/console-access.md).

### evidencias — nueva

id UUID opaco, tipo (acceso_instancia/validacion_definicion/revocacion_consola), schema_version=1, documento_canonico TEXT inmutable, sha256 CHAR(64), registrada_por FK usuario, registrada_at TIMESTAMPTZ. El documento incluye operador_institucional, observado_at, entorno real/simulado y el resultado tipado del [schema](contracts/evidence.schema.json). Máximo 64 KiB UTF-8; sin secretos ni archivos binarios. Cada consumidor usa FK al registro y comprueba hash, tipo, alcance y vigencia al consumirlo. No se borra en cascada ni admite PATCH/DELETE.

SHA-256 se calcula sobre JSON UTF-8 con claves ordenadas, sin espacios, ensure_ascii=false, enteros (sin floats), sin claves duplicadas, sin BOM y sin salto final; se conserva exactamente ese texto para recalcularlo. Los metadatos de registro del servidor quedan fuera del digest y no pueden ser enviados por el cliente. FK nullable de evidencias a destinos no se necesitan: la vinculación tipada está en el documento y se valida contra los registros de destino bajo lock; los consumidores mantienen FK evidencias.id. Así se evita un ciclo de creación entre definición, trámite y evidencia. El documento solo admite identificadores de instancias de laboratorio ajenas a NAP para validación inicial de definiciones.

Índices evidencias(tipo,registrada_at), cambios_acceso_consola(usuario_id,estado) y cambios_acceso_consola(catedra_id,estado). Migración aditiva compartida crea ambas tablas y FK del trámite a evidencias después de crear las tablas; conserva referencias legacy sin inventar evidencias de aceptación. Un hash acredita integridad, no el hecho de la prueba ni la identidad del operador: la autoridad es la declaración institucional auditada.

## 2. Oferta, definiciones y snapshots

### definiciones_servicio — nueva

id UUID, codigo, version, modelo_servicio, tipo_recurso=lxc, producto, manifest JSON, manifest_sha256, estado, validada_at, validada_por, evidencia_validacion UUID FK a evidencias.id nullable, retirada_at y created_at. El borrador admite manifest parcial; validar/publicar exige el [schema completo](contracts/service-definition.schema.json), artefactos y evidencia reales.

UNIQUE(codigo,version). Estados: borrador → validada → publicada → retirada; una validada puede publicarse después de superar compuertas reales. El contenido de una versión validada es inmutable; cambios generan otra versión. Retirada impide altas nuevas y no altera servicios ni aprobaciones previas. No se publican versiones que contengan credenciales.

### recurso_templates — existente, extendida

Agregar definicion_version_id FK nullable para ofertas legacy/IaaS hasta regularización; conservar modelo_servicio y tipo histórico. Nuevas ofertas publicables requieren definición validada/publicada compatible. CHECK de defaults positivos; eliminación del límite antiguo de 8 GiB y justificación coherente con política vigente.

config_extra se limita a parámetros permitidos de la definición. vmid, nodo, almacenamiento, unprivileged, privilegios, montajes, recursos y ejecutables no se aceptan como overrides libres. QEMU sigue representable en registros históricos, excluido de publicaciones y pedidos nuevos.

### pedidos — existente, extendida

Conservar FK y máquina de estados actual. Agregar revision INTEGER, anio_lectivo nullable, definicion_version_id FK, asignacion_snapshot JSON, destino_snapshot JSON y decision_snapshot JSON. Snapshot incluye nombre/modelo/producto/versión, recursos efectivos, mínimos, nodo/storage/scope, parámetros permitidos, fechas y revisiones usadas; no secretos.

La revisión final 009_13 retira reserva_vcpus/reserva_ram_mb/reserva_disk_gb/reserva_expira_at de modelos, respuestas y esquema. Conserva cantidades históricas positivas en asignacion_snapshot cuando faltaba, sin copiar el perfil actual; una bitácora registra cantidades/caducidad originales incluso cuando no son válidas para una nueva asignación. No crea capacidad, identidad ni vigencia a partir de ellas. El saldo y la caducidad se calculan exclusivamente con compromisos_capacidad e inventario. La API expone compromiso_capacidad como proyección de esa autoridad, sin duplicar columnas. Revertir crea evento y libera compromiso sin sobrescribir el snapshot autorizado.

revision cambia al editar datos relevantes. Evaluación/confirmación debe coincidir con ella. CHECK coherencia tipo/servicio_id: renovación exige servicio destino; alta admite NULL antes de materializar y conserva el vínculo al servicio creado después. La pertenencia a la misma cátedra se valida en las decisiones de dominio. 009_14 corrige también la definición inicial demasiado restrictiva de 009_13.

### servicios — existente, extendida

Agregar modelo_servicio persistido, nombre_snapshot, definicion_version_id FK, asignacion_snapshot JSON, identidad_infraestructura_id FK UNIQUE, disponibilidad_aplicacion, acceso_metadata JSON, credenciales_encrypted TEXT nullable, verificado_at y observado_at.

Estados de infraestructura existentes running/stopped/paused/error representan resultado confirmado; una operación pendiente se informa separada. Disponibilidad de aplicación: no_verificada, preparando, utilizable, degradada, error. LXC running no equivale a utilizable: Linux también exige bootstrap de cuenta guest propia y prueba de consola. Agregar evidencia_acceso_id UUID FK a evidencias.id y acceso_red_verificado_at; el registro de evidencia es inmutable y no se elimina en cascada. La operación infra puede confirmarse tras bootstrap/health local, mientras servicio sigue no_verificada y pedido EN_DESPLIEGUE hasta la prueba individual desde red prevista registrada por administración; no se mantiene una operación abierta esperando una persona.

credenciales_acceso JSON/texto anterior se migra al cifrado tipado y después deja de serializarse. Datos que eran meras descripciones o enlaces ficticios se marcan no verificados, sin transformarlos en credenciales reales. Un servicio dado de baja conserva modelo/recursos históricos, acceso revocado e historia; por defecto no aparece en listados operativos.

Cuenta de alumno BookStack **no** se replica como entidad NAP. El portal solo guarda la cuenta inicial docente/administración local entregada a la cátedra; alumnos y permisos se administran dentro de esa instancia.

## 3. Identidad externa y capacidad

### identidades_infraestructura — nueva

id UUID, cluster_id estable configurado, vmid INTEGER, nodo, pool_catedra, resource_uuid, nonce_cifrado, pedido_alta_id FK nullable, servicio_id FK nullable, estado, claimed_at, ausencia_confirmada_at y ownership_verificada_at.

UNIQUE(cluster_id,vmid) parcial para identidades retenidas (ausencia_confirmada_at IS NULL). VMID es global al clúster, no por nodo. UNIQUE(resource_uuid). La identidad se reclama antes de enviar create y se vincula al servicio tras materializar. Marca UUID/nonce y pool se contrastan contra infraestructura; hostname nunca prueba propiedad.

Estados: reclamada, materializada, incierta, retirada. Solo ausencia confirmada permite retirar la exclusividad para reutilización; se conserva la fila histórica y una nueva reclamación usa otro UUID/nonce.

### compromisos_capacidad — nueva

id UUID, pedido_id FK, servicio_id FK nullable, identidad_infraestructura_id FK nullable, nodo, storage_id, storage_scope, vcpus_retenidos, ram_mb_retenida, disk_bytes_retenidos, estado, revision, creado_at, expira_at nullable, liberado_at y justificacion_sobreasignacion nullable.

Estados: reservado, materializado, incierto, liberado. Cantidades >=0. Liberado exige todas las cantidades retenidas en cero; snapshots históricos de autorización no se eliminan. Índice por estado/nodo/storage_scope, y único compromiso no liberado por alta o servicio según su vínculo. Materializar vincula la misma fila, no agrega otra reserva.

| Suceso | CPU/RAM | Disco |
|---|---|---|
| Aprobar alta, incluso futura | Retiene desde aprobar | Retiene desde aprobar |
| Desplegar / respuesta incierta | Conserva | Conserva |
| Recurso materializado running | Una contribución unida a inventario | Una contribución unida a volumen real |
| Orden de pausa/detención enviada | Conserva hasta confirmar stopped | Conserva |
| Pausa/detención confirmada | Cero | Conserva |
| Inicio admitido antes del envío | Retiene incremento atómicamente | Sin nueva reserva del disco existente |
| Baja enviada | Conserva hasta confirmar efecto | Conserva hasta confirmar ausencia |
| Cancelar alta sin dispatch / ausencia confirmada | Libera | Libera |
| Renovación del mismo recurso | Sin segunda reserva | Sin segunda reserva |

El inventario externo no se copia como servicios NAP. El cálculo normaliza CPU/RAM configurados de recursos en marcha y volúmenes por identidad, y une observación con compromiso propio para no sumar dos veces. Storage scope local: node:nodo:storage; compartido: shared:storage, con identificador institucional que no confunda pools distintos.

Disponibilidad física de disco descuenta únicamente incrementos pendientes no representados; disponibilidad lógica usa provisión total de volúmenes. Margen de anfitrión y perfiles de destinos/red proceden de inventario institucional versionado, montado como configuración, sin añadir administración general de infraestructura.

## 4. Operaciones e historia

### decisiones_idempotentes — nueva

id UUID, actor_tipo, actor_id_normalizado, idempotency_key, metodo, ruta_canonica, target_tipo, target_id nullable, request_hash, response_status, resultado_referencia JSON seguro, creado_at. UNIQUE(actor_tipo,actor_id_normalizado,idempotency_key). Incluye mutaciones sin Proxmox: crear pedido, aprobar renovación, corregir calendario y verificar acceso.

Insertar/verificar clave y efectuar decisión/resultado en la misma transacción; una colisión concurrente espera el commit y reproduce resultado si coincide método/ruta/hash, o devuelve 409 si difiere. No dejar claves confirmadas sin efecto ni duplicar historia. Conservar referencias/resultados seguros para reproducir 200/201/202, nunca contraseñas/códigos. Auth conserva consumos propios de un uso, sin exigir estas claves. Operaciones de infraestructura referencian la decisión y conservan también su clave para reconciliar.

### operaciones_infraestructura — nueva

id UUID, tipo, pedido_id FK nullable, servicio_id FK nullable, identidad_infraestructura_id FK nullable, actor_usuario_id FK nullable, actor_tipo (usuario/sistema), motivo, idempotency_key, request_hash, estado, fase, upid nullable, intento, error_codigo, error_detalle_seguro, creado_at, updated_at, next_poll_at, lease_owner UUID nullable, lease_until y lease_generation INTEGER.

Tipos canónicos: desplegar, iniciar, detener, reiniciar, pausar, eliminar, reparar. El verbo crear de infraestructura se persiste como desplegar; alias HTTP se normalizan. Estados: pendiente → en_curso → confirmada/fallida/incierta; incierta → en_curso para reconciliación → confirmada/fallida. Incierta sigue abierta. Fase conserva preparación/dispatch_started/tarea/bootstrap/verificacion/reconciliacion.

UNIQUE(actor_tipo,actor_id_normalizado,idempotency_key) con request_hash; índice único parcial de operación abierta por pedido/servicio/identidad según vínculo. No permitir operaciones simultáneas que apunten al mismo recurso a través de vínculos diferentes: bloquear la identidad y comprobar los tres vínculos antes de crear. El sistema genera claves deterministas por evento.

SKIP LOCKED reclama; lease/generación protege escritura y liberación. Dispatch_started se persiste antes de la llamada. Takeover con dispatch iniciado sin UPID es reconciliación, no reenvío automático. No existe garantía de exactly-once de Proxmox; se logra efecto único por identidad, verificación y deduplicación.

### pedidos_historial / servicios_historial / job_locks — existentes

- Historia incorpora operacion_id nullable, evento_clave nullable UNIQUE por entidad, actor_tipo y metadatos de decisión seguros. usuario_id nulo con actor_tipo=sistema distingue automatismos; conservar autorías existentes.
- Solo pedido_service.transicionar cambia estado de pedido, también al aplicar renovación. Renovación aplicada puede resolver el pedido como ACTIVO, presentada como “Renovación registrada”; no afirma que el contenedor esté encendido.
- job_locks agrega owner UUID, lease_until, heartbeat_at y generation. Renovar/liberar requiere owner y generación actuales; nunca DELETE solo por nombre después de perder la propiedad.

## 5. Calendario y vigencias

### calendarios_lectivos / periodos_calendario — nuevas

calendarios_lectivos: id, anio UNIQUE, zona_horaria IANA, revision, actualizado_por FK, created_at, updated_at. Zona inicial de instalación: America/Argentina/Tucuman, parametrizable institucionalmente.

periodos_calendario: id, calendario_id FK, tipo, desde DATE, hasta DATE. UNIQUE(calendario_id,tipo), CHECK(desde<=hasta); tipos primer_cuatrimestre, segundo_cuatrimestre, anual. Un calendario incompleto puede guardarse, pero no resuelve modalidades ausentes. No exigir que anual sea disjunto de cuatrimestres.

### vigencias_autorizadas — nueva

id UUID, pedido_id FK, revision_decision INTEGER, servicio_id FK nullable hasta alta, modalidad, anio_lectivo nullable, calendario_id nullable, calendario_revision nullable, desde_local DATE, hasta_local DATE, zona_horaria, inicio_at, fin_exclusivo_at, aprobado_por FK nullable, aprobado_at, origen (nuevo/legacy/regularizacion), sustituye_id FK nullable y revocada_at nullable con evento de historia. UNIQUE(pedido_id,revision_decision) conserva reaprobaciones sin sobrescribir períodos anteriores.

CHECK(inicio_at<fin_exclusivo_at). Intervalo operativo [inicio_at,fin_exclusivo_at). Contenido de períodos aprobados inmutable; modificación explícita crea revisión que sustituye la anterior con historia y reevaluación. Filas sustituidas/revocadas no otorgan cobertura. Revertir alta sin dispatch revoca decisión/período y libera compromiso; reaprobación usa revision_decision nueva. Bloqueo de servicio serializa renovaciones/modificaciones y vencimiento.

Renovación requiere mismo servicio/cátedra; no aceptar duplicado o solapamiento del período ya autorizado, salvo modificación explícita. Esta crea un pedido de renovación con pedidos.sustituye_vigencia_id FK y motivo; al aprobar crea el nuevo período y excluye al anterior en la misma transacción. Contiguos permiten continuidad; separados conservan el intervalo vacío. Cobertura ignora pedidos pendientes/cancelados y períodos sustituidos/revocados. Si corregir acorta cobertura actual, se advierte su efecto y se programa pausa con aviso/resultado confirmado.

servicios.vence_at continúa como proyección del final de cobertura actual, no como máximo de todos los períodos futuros. Al aprobar futuro no extiende cobertura presente. Se conserva disco durante intervalos. No hay inicio automático por llegar la fecha.

### Datos legacy sin fechas confiables

No inventar un período. Marcar servicio como pendiente_regularizacion en metadatos, preservar el estado real y no ejecutar pausa por una fecha fabricada. Administración debe decidir vigencia por flujo auditado antes de nuevos inicios/reinicios/despliegues. La aceptación final no deja recursos operativos legacy sin fecha conocida. El preflight genera informe para regularizar desde el portal, sin SQL manual.

## 6. Observaciones, agregados e incidentes

### metricas_snapshots — existente, extendida

Conservar servicio_id y timestamp; agregar intervalo_at UTC truncado a minuto, estado_observado, calidad (confirmada/no_confirmada), aplicacion_saludable boolean nullable, uptime_s BIGINT, epoca_contador, ram_max_mb, disk_max_bytes, vcpus_observadas, net_in_bytes/net_out_bytes BIGINT, net_in_delta/net_out_delta BIGINT nullable y duracion_observada_s. aplicacion_saludable conserva True/False solo cuando el probe ligado a identidad confirma éxito/fallo; None representa falta de confirmación, sin inferir salud de que el LXC esté running.

CPU representa porcentaje normalizado de la asignación según campo de Proxmox verificado en integración; no multiplicar otra vez por cantidad de CPU sin evidencia. Registrar máximos de la misma observación; fallback a snapshot autorizado debe identificarse como estimado. Disco/RAM bytes nunca se interpretan como GiB/MB decimales.

UNIQUE(servicio_id,intervalo_at); índice (servicio_id,timestamp DESC). Captura manual comparte la deduplicación de intervalo, no aumenta cobertura. Un contador que retrocede o uptime que reinicia empieza época y marca el intervalo incompleto; no se inventa delta entre reinicios.

La migración 009_11 conserva todos los registros y los Float originales en net_in_legacy/net_out_legacy. Solo copia a BIGINT enteros no negativos dentro del rango exacto seguro del Float; valores imprecisos quedan NULL. Las muestras anteriores conservan timestamp UTC, intervalo_at NULL y calidad no_confirmada, sin fabricar cobertura ni eliminar duplicados.

Una captura de estado también distingue stopped de ausencia de telemetría. Fallar transporte genera calidad no_confirmada, no caída ni CPU cero. Inactividad requiere 80 % de intervalos esperados en siete días y no contar varias muestras por minuto.

### metricas_resumen_diario — nueva

PK(servicio_id,fecha_local,zona_horaria), catedra_id FK histórica, intervalos_esperados, intervalos_validos, segundos_observados, cpu_integral, cpu_max, ram_integral_mb_s, ram_max_mb, disk_max_bytes, trafico_in_bytes, trafico_out_bytes, segundos_running, vcpu_segundos, ram_asignada_mb_segundos, disk_asignado_byte_segundos, periodo_cerrado y agregado_at.

Guardar integrales/denominadores, no promediar promedios. Asignación y tiempos se reconstruyen con eventos de servicio y muestras con cobertura; huecos se conservan como desconocidos. No atribuir certeza a tiempos sin observar. Upsert determinista por día; purgar detalle >90 días solo después de verificar resumen cerrado y conservar último extremo necesario para delta del siguiente día.

detalle_purgado_at registra la reducción ya realizada: una nueva ejecución no reemplaza un agregado completo por los pocos extremos conservados. Tráfico y disco-byte-segundos usan NUMERIC(30,0), para evitar overflow al sumar contadores/épocas; la API los presenta como enteros. Tiempos de asignación quedan NULL si no existe historia confiable.

### incidentes / notificaciones — nuevas

incidentes: id UUID, servicio_id FK, tipo, estado abierto/resuelto, abierto_at, ultima_observacion_at, resuelto_at, regla_version, evidencia JSON segura. UNIQUE parcial(servicio_id,tipo) WHERE estado=abierto. Tipos iniciales: caida, cpu_sostenida, ram_sostenida, vencimiento_no_aplicado, operacion_incierta.

notificaciones funciona como outbox: id UUID, evento_clave, destinatario_usuario_id FK nullable, destinatario_email_cifrado nullable, canal portal/email, catedra_id FK nullable para bienvenida sin asignación, servicio_id FK nullable, estado pendiente/enviando/enviada/fallida/cancelada, payload seguro, secreto_temporal_encrypted nullable, secreto_expira_at nullable, auth_version_objetivo nullable, intentos, proximo_intento_at, ultimo_error, created_at y enviada_at. UNIQUE(evento_clave,destinatario_normalizado,canal).

Validar destinatarios activos/titularidad al enviar; no revelar datos a quien perdió acceso. Reintentar con backoff/Message-ID estable; fallos visibles admin. No incluir credenciales de servicio ni códigos. Bienvenida usa secreto_temporal_encrypted separado del payload, ligado a cuenta pendiente/auth_version. Solo emisor descifra al construir mensaje; borrar al confirmar envío/cambio de contraseña/reemisión o cancelar por vencimiento (24 horas para entrega, no caducidad silenciosa de contraseña ya entregada). Mock SMTP tampoco registra cuerpo/secretos. Si falta SMTP operativo, preflight informa. No reconstruir secretos ya borrados para reintentar.

### restauraciones / accesos_iniciales_restaurados — T130

`restauraciones`: UUID, referencia única de cada restauración, operador, estado pendiente/habilitada, fecha de preparación y resumen de revocaciones; al habilitar exige actor/fecha/referencia de ensayo/hash de prueba/hash de estado. Índice único parcial permite un solo corte pendiente. El rol runtime sólo lee esta tabla. Una referencia externa nueva en configuración bloquea el arranque incluso antes de preparar la copia.

`accesos_iniciales_restaurados`: UUID, FK restauración/usuario, fecha y metadatos de reemisión autorizada. UNIQUE(restauracion_id,usuario_id). No agrega columnas al usuario ni duplica sus secretos: conserva compatibilidad del backfill sobre revisiones anteriores. Un acceso inicial del corte no habilita login hasta reemplazar su contraseña mediante administración o CLI autorizado; no borra cuentas ni desactiva MFA.

Preparar serializa con 4001/5003, verifica descifrado antes de mutar, revoca SID/desafíos/códigos y cancela correos/secretos antiguos. Las operaciones abiertas quedan inciertas con lease invalidado y capacidad retenida; no se reenvían. Habilitar exige atestación de ensayo separado y comparación actual de configuración/datos/identidad/asignación/ledger/vigencia. No hay una opción de forzar incertidumbres ni un módulo de backups. Migración aditiva 009_14; procedimiento en docs/preparar-restauracion.md.

## 7. Índices, restricciones y orden de migración

Índices operativos adicionales: pedidos(catedra_id,estado,created_at DESC) parcial vigente; servicios(catedra_id,estado) parcial vigente; historial(pedido_id/servicio_id,created_at,id); operaciones(estado,next_poll_at); notificaciones(estado,proximo_intento_at); vigencias(servicio_id,inicio_at,fin_exclusivo_at). Comprobar EXPLAIN sobre volumen de referencia antes de agregar índices redundantes.

Secuencia propuesta:

1. Preflight y copia verificada: head Alembic actual, duplicados VMID/relaciones, fechas legacy, recursos inválidos, factores incompletos, secretos ficticios y pertenencia externa. Informe sin secretos; no corregir borrando historia.
2. Migración aditiva de tablas/campos nullable e índices no dependientes de backfill. Convertir tiempos legacy conocidos como UTC mediante interpretación explícita AT TIME ZONE 'UTC'; no como hora argentina.
3. Backfill idempotente con bitácora: snapshots desde cantidades autorizadas conocidas; períodos solo con fechas confiables; reclamar identidades y compromisos contrastados con inventario. EN_DESPLIEGUE/ERROR incierto se concilia antes de liberar. Activos sin inventario siguen retenidos/no confirmados.
4. Cifrar secretos con keyring ya instalado y comprobar descifrado/restore; conservar MFA activo. Credenciales inválidas se marcan pendientes de nueva entrega. Invalidar JWT anteriores sin sid y version.
5. Regularizar duplicados/fechas mediante decisiones auditadas; crear uniques/CHECK/FK definitivos tras limpiar inconsistencias sin pérdida histórica. Fresh install y upgrade deben llegar al mismo esquema.
6. Cambiar lecturas a nuevas autoridades y retirar serialización/uso de columnas antiguas. Eliminar secretos en claro al concluir la migración y verificar; no mantener doble escritura permanente.

Upgrade se ensaya sobre copia y base vacía; rollback operativo usa backup y versión compatible, no downgrade destructivo de historia. Restore revoca sesiones/desafíos/códigos del corte para no reutilizar credenciales consumidas después; conserva factores activos y exige códigos nuevos tras contraseña+TOTP o asistencia. Cancela bienvenidas pendientes con secretos antiguos y limpia ese material; las cuentas que requieran nueva entrega se regularizan por administración autorizada de personas, sin cuentas predeterminadas. No arrancar workers restaurados contra recursos reales antes de reconciliar y verificar configuración.

## 8. Bitácora de regularización del cierre

`bitacora_cierre` (aditiva009_12): UUID, entidad_tipo/entidad_id, fuente_sha256, resultado_sha256, accion, antes_seguro/despues_seguro, pendientes, legado_cifrado nullable, actor institucional o usuario, referencia y creado_at UTC. UNIQUE(entidad_tipo,entidad_id,accion,fuente_sha256). Registro inmutable; el material legado sólo existe cifrado con contexto cierre:UUID:legado y nunca se serializa en API. El resultado permite reconocer repeticiones sin duplicar eventos y conserva pendientes aunque se repita el ensayo. No constituye evidencia de entrega ni habilita activación.

Backfill sólo recupera vigencias/asignaciones completas de decisión congelada y evento de aprobación coincidente; jamás del calendario actual ni de deployed_at. Cantidades conocidas sin esa prueba forman un snapshot parcial de origen explícito y siguen pendientes de regularización. Retención de capacidad faltante exige marca/nonce/pool de identidad ya ligada y destino observado; se crea incierta/conservadora, sin completar hashes históricos ni liberar recursos.
