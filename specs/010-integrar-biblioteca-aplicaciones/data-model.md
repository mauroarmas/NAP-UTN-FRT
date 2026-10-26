# Modelo de datos: biblioteca de aplicaciones

Diseño propuesto; las tablas y campos nuevos todavía no existen. UUID para entidades nuevas, fechas UTC con zona horaria, presentación en zona institucional. Cambios mediante Alembic; no alterar historia de 009.

## IncorporacionAplicacion — nueva

Borrador administrativo independiente del manifiesto técnico.

| Campo | Regla |
|---|---|
| id | UUID, PK |
| proveedor / identidad_externa | `community-scripts` y ruta canónica `ct/drawio.sh`; clave de aplicación independiente de alias |
| revision_fuente / comando_sha256 | Revisión completa y digest de comando de procedencia |
| comando_origen / url_origen | Texto informativo y URL HTTPS permitida; nunca ejecución |
| version_externa | Nullable; no inventar semver si se desconoce |
| origen_clave | Versión externa si se conoce; si no, revisión fuente + marcador explícito `desconocida` |
| nombre / descripcion / categorias / aliases | Datos editables, separando fuente externa y etiquetas NAP |
| datos_origen | Snapshot de datos observados, acotado, sin secretos |
| faltantes | Lista calculada de información requerida, no flags de validación ficticios |
| revision / creado_por / created_at | Control optimista, autor y fecha |
| definiciones | Relación 1:N derivada de `DefinicionServicio.incorporacion_id`; ninguna FK singular que impida versiones posteriores |

Unique `(proveedor, identidad_externa, origen_clave)`. Reimportar devuelve el registro existente incluso con otra Idempotency-Key y no sobrescribe ediciones. Con versión conocida, otra revisión de fuente no crea otra incorporación de esa misma versión ni sobrescribe la procedencia original; puede registrarse como observación histórica. Con versión desconocida, otra revisión crea una candidata vinculada al antecedente, sin afirmar que sea otra release. No hay garantía de identidad de release si el proveedor sólo entrega un comando móvil; la versión efectiva se determina durante resolución y se fija antes de construir. La misma incorporación puede originar varias revisiones NAP, aun sin cambio del comando externo; reimportar no crea revisiones técnicas automáticamente.

## EnsayoPreparacion — nueva

Un intento durable de preparar una definición, con resultado independiente de limpieza.

| Campo | Regla |
|---|---|
| id / incorporacion_id / definicion_id | UUID PK y FKs; definición `borrador` para iniciar |
| estado | `pendiente`, `resolviendo`, `esperando_confirmacion`, `construyendo`, `ensayando`, `lista_para_comprobar`, `comprobada`, `fallida`, `incierta`, `descartada`, `vencida` |
| revision / creado_por / creado_at | CAS y auditoría |
| execution_generation / cancelada_at / cierre_remoto_confirmado_at | Generación monotónica por ensayo, cierre irreversible y constancia de cancelación remota; independientes de la generación del lease por operación |
| expires_at / aviso_at / avisado_at | Plazo configurado; se persiste al admitir |
| entradas_resueltas / entradas_sha256 | Versiones exactas, paquetes, base, WAR/Tomcat, receta/revisión; ninguna credencial |
| confirmada_por / confirmada_at | Aprobación de entradas fijadas antes del build |
| artefacto_id / evidencia_id / publicacion_id | FKs; nullable hasta producir/verificar |
| limpieza_estado | `no_solicitada`, `pendiente`, `en_curso`, `confirmada`, `fallida` |
| motivo_cierre / error_codigo / error_detalle_seguro | Sin shell, secretos ni trazas del proveedor |

Índice único parcial de ensayo no terminal por definición; un ensayo `incierta` sigue abierto. Un reintento continúa el mismo ensayo con operaciones nuevas; no crea otro recurso mientras no se reconcilie su propiedad/ausencia.

Transiciones centralizadas en `ensayo_service`, con eventos append-only:

- `pendiente → resolviendo → esperando_confirmacion → construyendo → ensayando → lista_para_comprobar → comprobada`.
- Fallo cierto en fase de trabajo → `fallida`; pérdida de confirmación → `incierta`.
- `fallida →` fase segura de reintento tras conciliación; `incierta →` fase observada por reconciliación, o `fallida` si ausencia/fallo confirmado.
- Descartar o expirar un ensayo no publicado → `descartada` o `vencida`; cancelación/fencing de trabajo y limpieza durable.
- Publicar exige `comprobada` y definición validada; no cambia un ensayo a otro estado funcional, registra `publicacion_id` y solicita limpieza. Descartar un ensayo ya publicado no retira la oferta: requiere acción independiente de retiro.
- Vencer uno publicado sólo limpia sus recursos efímeros. Limpieza nunca borra evidencia, artefactos conservados ni referencias históricas.

## RecursoEnsayo — nueva

Dos filas por ensayo, roles `funcional_a` y `funcional_b`, para despliegue repetible y aislamiento. Campos: `id`, `ensayo_id`, `rol`, `identidad_infraestructura_id`, snapshot de destino/red, bootstrap y acceso de ensayo, secretos cifrados con contexto propio, `ausencia_confirmada_at`. Unique `(ensayo_id, rol)` y FK de identidad única. El acceso de ensayo sólo se revela al administrador por endpoint explícito auditado; nunca entra en el artefacto.

## OperacionEnsayo — nueva

Separada de `OperacionInfraestructura` académica; reutiliza sus primitivas, no su vínculo obligatorio de negocio. Campos: UUID, ensayo/recurso opcional, `tipo` (`resolver`, `construir`, `distribuir`, `crear`, `bootstrap`, `inspeccionar`, `eliminar`, `cancelar_builder`, `limpiar_builder`), `estado` (`pendiente`, `en_curso`, `confirmada`, `fallida`, `incierta`), fase, actor usuario/sistema, clave/hash de petición, identificador remoto/UPID, `dispatch_started_at`, lease owner/until/generation, intento, next_poll/deadline, resultado seguro. Índice de una operación abierta por recurso y por trabajo de construcción; Idempotency-Key por actor y acción. Persistir intención/identidad antes del I/O; commit del resultado sólo si coinciden la generación de lease y `execution_generation` del ensayo. Al reclamar ejecución/reintento, incrementar la generación de ensayo bajo lock; una cancelación la incrementa y cierra el ensayo antes del dispatch remoto. No confirmar limpieza PVE mientras haya dispatch/tarea de creación o bootstrap de estado incierto: conciliar tareas en vuelo, preservar reservas y evitar otro envío de creación. Para builder, confirmar primero el cierre durable remoto y la terminación de procesos; un worker antiguo nunca reabre un ensayo cerrado.

`EventoEnsayo`: ensayo, operación, secuencia, anterior/nuevo, actor, motivo, timestamp y metadata segura. Unique `(ensayo_id, evento_clave)`, append-only. Expiración/limpieza identifican al sistema como autor.

## ArtefactoPreparado — nueva

Campos: UUID, definición, entradas_sha256, estado (`construyendo`, `disponible`, `bloqueado`), raíz de registro institucional, volumen PVE, imagen SHA-256/tamaño, bundle SHA-256/tamaño, versión efectiva Draw.io/Tomcat/JRE, inventario, saneamiento y fecha. Sólo IDs institucionales en API; rutas reales y credenciales quedan en configuración. `ReplicaArtefacto`: artefacto, nodo/storage, hashes observados y fecha de verificación; unique `(artefacto_id, nodo, storage_id)`.

El registro es independiente del ensayo y de sus LXC. Después de validar, contenido inmutable. Mantener original mientras haya publicaciones, pedidos aprobados o servicios referenciándolo, aunque la publicación se retire. Artefactos fallidos/quarantena conservan trazabilidad; la limpieza de temporales nunca apunta al directorio de artefactos final. No hay borrado automático de artefactos históricos en el piloto.

## PresupuestoBuilder — nueva

Fila durable con PK `scope_id` (disco físico institucional canónico), `revision_config`, `limite_bytes`, `habilitado` y fecha de actualización. Los hosts configurados apuntan a un scope; hosts que comparten builder/registro o disco comparten esta fila, no presupuestos independientes. La capacidad libre se observa, no se toma de la ficha externa. No almacenar secretos.

Antes de la primera reserva, ejecutar `INSERT ... ON CONFLICT DO NOTHING` desde configuración institucional validada y después `SELECT ... FOR UPDATE` en la misma transacción. Así dos primeras admisiones bloquean la misma fila existente incluso cuando la tabla estaba vacía. Revalidar revisión/límite configurado bajo lock; un cambio incompatible no reinicia ni elimina reservas. Para varios scopes, bloquear por ID ordenado; si se combina con capacidad PVE, adquirir primero lock 4001 y después scopes en ese orden. Todos los caminos de admisión/ajuste/liberación usan la misma fila.

## ReservaEspacioBuilder — nueva

UUID, ensayo_id, host_id institucional, scope_id FK a `PresupuestoBuilder`, bytes_temporales, bytes_finales_previstos, estado y fecha de liberación; cantidades no negativas e índice de reservas retenidas por scope. Admitir trabajos bajo bloqueo de fila por scope, contra presupuesto configurado y espacio físico observado; persistir reserva antes del dispatch. Tamaños máximos por trabajo y por host se configuran, no provienen de la ficha externa. Al producir artefacto, convertir su tamaño real en ocupación retenida del registro, sin sumarlo de nuevo como temporal. Sólo confirmar liberación temporal tras cleanup del builder; trabajo incierto mantiene presupuesto. Los bytes finales siguen ocupados mientras exista el artefacto, independientemente de limpiar el ensayo. Si builder y registro comparten disco, usar un mismo scope físico para no admitir dos veces el espacio libre.

## Entidades existentes ampliadas

### DefinicionServicio

Agregar `incorporacion_id` FK nullable para origen 1:N y `base_definicion_id` FK nullable al antecedente; no alterar definiciones anteriores ajenas a biblioteca. Una revisión posterior mantiene incorporación/código/producto del antecedente y aumenta versión NAP por comparación semántica. Conservar `(codigo, version)` e inmutabilidad tras validación. `version` es revisión NAP semver, distinta de versión externa observada. Nuevo producto `drawio`, modelo `saas`; ampliar esquema 1.1 con componentes y receta/probes cerrados. Incorporación/ensayo/artefacto se relacionan por FK externas al manifiesto, que sigue sin comandos/URLs ejecutables ni secretos.

### RecursoTemplate y PublicacionOferta

`RecursoTemplate` sigue siendo la oferta estable y su ID se conserva al publicar una nueva versión. Mantener `definicion_version_id`, `revision`, `activo` y mínimos compatibles. Publicar desde el nuevo asistente crea un perfil o mueve el perfil explícitamente seleccionado; no cambia otros perfiles del mismo producto.

Nueva bitácora `PublicacionOferta`: UUID, template_id, definicion_id, ensayo_id, revisión del perfil, snapshot de recursos/descripción, autor, fecha. Unique `(template_id, revision)`. El puntero vigente es el del perfil, no una inferencia por fechas. Bloquear perfil y definición al publicar; validar, actualizar puntero, registrar bitácora y encolar limpieza en una transacción. Retirar definición deshabilita selección de perfiles cuyo puntero sigue sobre ella; no reactivarlos automáticamente ni volver a otra versión.

### Pedido / decisión / historial

Nuevo `seleccion_oferta_snapshot` al enviar o reenviar: ID/revisión del perfil, definición seleccionada, versión y nombre mostrados. Conservarlo aunque `template_id`/`definicion_version_id` cambien al aprobar. Para altas de ofertas de biblioteca: evaluación resuelve el puntero vigente y devuelve comparación solicitada/efectiva. La confirmación verifica el token/revisión vigente y fija asignacion/decision_snapshot, historial y notificación transaccional con ambas versiones. No se requiere confirmación docente. «Otro» puede vincular perfil explícitamente; conservar descripción original. Renovaciones mantienen snapshot original del servicio.

### CompromisoCapacidad

Hacer `pedido_id` nullable y agregar `recurso_ensayo_id` FK. Check de propietario exclusivo: exactamente uno de esos campos no nulo. Conservar servicio/identidad opcionales y estados actuales. Unique parcial de compromiso abierto por recurso de ensayo, además de índices existentes. Cada uno de los dos recursos de ensayo tiene una reserva independiente, admitidas juntas bajo lock `4001`. Expirador de reservas académicas filtra `pedido_id IS NOT NULL`; expiración de ensayos la atiende su propio ejecutor.

`panorama` integra ambas clases con la misma unión por identidad y scope; migrar cálculo de fingerprint para incluir propietario de ensayo. Reservado/materializado/incierto siguen ocupando hasta ausencia confirmada. CPU/RAM/disco de LXC no incluyen almacenamiento retenido de imagen; éste ya figura como uso de storage y requiere contabilidad separada en host builder si no es storage PVE.

### IdentidadInfraestructura

Agregar pertenencia opcional a recurso de ensayo, excluyente de pedido/servicio académico. `pool_catedra` conserva nombre físico por compatibilidad; para ensayos contiene el pool institucional autorizado. Validadores distinguen clase de propietario y nunca conceden pertenencia docente a un ensayo. Misma unicidad global `(cluster_id, vmid)` mientras no haya ausencia confirmada. No relajar ownership para permitir limpieza.

## Migración y consistencia

1. Crear tablas nuevas, FKs/índices y extensiones nullable; conservar valores y referencias existentes.
2. Generalizar ledger y comprobar exclusividad; todos los compromisos históricos conservan dueño académico.
3. Activar escritores nuevos tras actualizar worker, schema/registro y permisos DML institucionales; runtime sin DDL.
4. No rellenar snapshots históricos con la oferta vigente: los desconocidos quedan explícitos y conservan rutas actuales de regularización.
5. Probar migración desde revisión Alembic real del checkout al implementar y restauración con tablas nuevas. La retirada operativa deshabilita la feature; no borrar datos para simular rollback.
