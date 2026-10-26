# Data model: configuraciones, instancias e historial de consola

Diseño propuesto; las tablas y migraciones aún no existen. Mantener PostgreSQL/SQLAlchemy/Alembic.
Nombres físicos sugeridos para generar tareas; no hay DDL ni cuerpos de implementación en este documento.

## 1. ConfiguracionDespliegue — nueva, inmutable

`configuraciones_despliegue`:

| Campo | Tipo / regla |
|---|---|
| id | UUID, PK |
| codigo, revision | Identidad de familia y entero positivo; UNIQUE(codigo, revision) |
| origen | `imagen_docker` o `community_scripts` |
| modelo_servicio | `paas` o `saas`; las bases IaaS siguen su camino actual |
| documento | JSON validado por `nap-deployment/1`; contrato discriminado en `contracts/configuracion.md` |
| sha256 | Hash canónico del documento no sensible |
| perfil_id, perfil_revision, perfil_sha256 | Perfil institucional exacto de base/runtime/instalador/acceso |
| estado | `validada` o `retirada`; sólo se inserta tras validación automática satisfactoria |
| validaciones | Tipos de comprobación realizados, fecha y resultados seguros; no afirmar una instalación |
| creado_por, creado_at, retirada_at | Autor y fechas; referencias a Usuario donde corresponda |

No modificar una revisión validada. Editar su configuración crea otra revisión; cambiar nombre o
texto de oferta no cambia su instalación. La retirada es lógica. No reutilizar `DefinicionServicio`
ni su manifiesto histórico como si una imagen Docker fuera una imagen LXC preparada.

## 2. Relaciones con entidades existentes

- `RecursoTemplate.configuracion_despliegue_id`: FK nullable e indexada. La configuración nueva y
  `definicion_version_id` histórica son mutuamente excluyentes. Las bases Linux históricas pueden
  mantener ambas nulas y su marca actual. No borrar/recrear templates existentes.
- `Pedido.configuracion_despliegue_id` y `Servicio.configuracion_despliegue_id`: FK nullable para
  preservar la configuración efectiva, sin reinterpretar filas de 009/010.
- `asignacion_snapshot` conserva selección, configuración aprobada completa no sensible y su hash,
  perfil/base exactos, digest de imagen o fuentes fijadas, red/acceso, requisitos y referencias de
  secretos por instancia. Las revisiones del catálogo no mutan snapshots aprobados.
- `IdentidadInfraestructura` conserva cluster, nodo, VMID, resource UUID, pool y nonce. Para el
  nuevo protocolo `definition_sha256` corresponde al hash de configuración y `bundle_sha256` al
  paquete de política/ejecución identificado. Su significado discriminado se registra en snapshot;
  no modificar el marcador ni los significados de invitados históricos.
- `CompromisoCapacidad` sigue siendo la contabilidad única. Incluir runtime, imágenes, escritura,
  volúmenes y logs dentro del tamaño LXC; ningún volumen Docker es un recurso invisible externo.

La FK y hash de configuración entran en la huella de evaluación. Al aprobar se bloquean oferta,
configuración vigente, pedido y capacidad según el orden actual. La renovación conserva la
configuración de la instancia original, aunque cambie la oferta; no reinstala ni cambia secretos.

### Programación

Agregar a Pedido `despliegue_solicitado_at`, `despliegue_programado_at`,
`despliegue_revision_programada` y `despliegue_solicitado_por` (nullable; defaults históricos nulos).
La intención corresponde a la revisión aprobada y no crea una operación nativa ni un invitado
antes de la fecha inicial. Su admisión usa clave estable por pedido/revisión y autor `sistema`.
La expiración de reserva programada se calcula con la gracia vigente a partir de
`max(aprobacion_at, inicio_vigencia)`; una nueva resolución, cancelación o baja invalida la agenda.
No agregar otra máquina de estados de pedidos.

## 3. SecretoDespliegue — nueva, por pedido/instancia

`secretos_despliegue`: UUID PK; pedido_id FK; configuracion_id FK; nombre permitido; revision;
origen `generado` o `aportado`; valor_cifrado; creado_at. UNIQUE(pedido_id, nombre, revision).

- Contexto autenticado de cifrado incluye pedido, nombre y revisión; no hay valor en snapshots,
  `contexto_seguro`, mensajes, idempotencia de respuesta ni esquemas de lectura ordinarios.
- Declaraciones de secreto pertenecen a la configuración; valores efectivos se crean por pedido
  antes del dispatch y nunca se regeneran al consultar o reintentar el mismo despliegue.
- Credenciales nativas de acceso se generan por instancia. No se permiten contraseñas de acceso
  predeterminadas compartidas dentro de una oferta; si una aplicación necesita un valor aportado,
  se solicita para ese pedido mediante un campo sensible sólo cuando sea necesario.
- Los valores institucionales de registry pertenecen a la configuración privada de infraestructura,
  no a esta tabla ni al software de la cátedra.
- Las ramas nuevas de acceso consultan esta fuente de secretos tras autorizar. Los campos cifrados
  históricos de Servicio conservan su contrato; no duplicar en ambas fuentes un secreto nuevo.

## 4. Operaciones e intentos efectivos

Añadir `OperacionInfraestructura.operacion_raiz_id` FK nullable a la misma tabla, con raíz efectiva
`coalesce(operacion_raiz_id, id)`. Sin backfill de efectos ni cambios de estado de registros antiguos.

`intentos_despliegue`:

| Campo | Regla |
|---|---|
| id | UUID PK |
| operacion_id | FK a operación nativa; UNIQUE para ejecución nueva de 011 |
| operacion_raiz_id, numero | FK raíz + entero positivo; UNIQUE(raiz, numero) |
| execution_id | UUID UNIQUE; deduplicación externa independiente del lease |
| identidad_infraestructura_id | FK a identidad concreta del intento |
| configuracion_sha256 | Configuración aprobada |
| estado | `preparado`, `ejecutando`, `confirmado`, `fallido`, `incierto` |
| runner_job_id, node_boot_id | Trabajo correlacionado; un PID no demuestra identidad |
| creado_at, iniciado_at, observado_at, terminado_at | Fechas UTC |
| ultimo_source_seq | Cursor de ingesta confirmado |
| error_codigo, error_detalle_seguro | Resumen sin valores sensibles |

El contador existente `OperacionInfraestructura.intento` continúa como reclamaciones históricas;
no se muestra como número de instalación ni se resetea. La UI usa `numero` del intento efectivo.
Un takeover/reconexión continúa el mismo execution_id. El reintento de un fallo confirmado crea
una operación `reparar`, otro intento y el enlace a la raíz; una operación terminal no se reabre.
Las restricciones existentes de operación abierta por pedido/servicio/identidad siguen vigentes.

Estados: preparado → ejecutando → confirmado/fallido; preparado o ejecutando → incierto si se
pierde prueba de ejecución. Incierto → ejecutando/confirmado/fallido sólo con observación probada.
Un código de salida no confirma por sí solo la entrega: deben pasar las comprobaciones de acceso.

## 5. ConsolaOperacion y ConsolaFragmento — nuevas

`consolas_operacion`, una fila por raíz lógica: operacion_raiz_id PK/FK; next_seq;
first_retained_seq; last_seq; retained_bytes; dropped_bytes; dropped_messages; last_captured_at;
last_ingested_at; truncated; expired; ultimo_resultado_seguro. Guardar esta cabecera tras purgar texto.

`consola_fragmentos`: PK(operacion_raiz_id, seq); intento_id FK; execution_id; source_seq;
captured_at; ingested_at; fase; stream(`sistema`, `stdout`, `stderr`); texto_depurado; utf8_bytes.
UNIQUE(execution_id, source_seq), índices por raíz/secuencia y fecha de captura.

Insertar, deduplicar, numerar y avanzar cursor en una transacción corta bloqueando la cabecera.
ACK del nodo sólo después de commit. Un hueco debido a descarte en origen se conserva como dato y
aviso, nunca se inventan líneas. El orden es de captura observada entre streams, no una cronología
más precisa que la que obtuvo el productor.

Límites: fragmento <=8 KiB, respuesta <=64 KiB, texto retenido <=10 000 000 bytes por raíz sumando
intentos; purgar lo más antiguo al excederlo. Retención 30 días desde captura; no purgar estado,
resultado, motivos, eventos de seguridad ni historial académico. El spool de nodo está depurado,
acotado y elimina fragmentos confirmados; no es una segunda retención permanente.

## 6. Perfiles institucionales — archivos privados y paquetes, no pantalla nueva

- Runtime Docker: base Ubuntu 24.04, arquitectura, versiones verificadas de runtime, features LXC
  exactas, filesystem, mínimos medidos y capacidades permitidas.
- Community: script y Core fijados, manifest de archivos/hashes, harness/política, base Debian 13,
  snapshot APT y descargas verificadas, respuestas cerradas, acceso/probe y secretos esperados.
- Red: reserva de IP/MAC/DNS, ingreso por gateway o cliente permitido, egress controlado y bloqueo
  de administración/otras cátedras. No adoptar el perfil histórico de un producto por coincidencia.
- Registry: host/CA/repository scope/credencial de lectura, fuera de los documentos públicos.

Estado técnico de un perfil: `pendiente_validacion`, `habilitado`, `bloqueado`. Registrar revisión,
plataforma comprobada, resultados y motivo. Cambiar perfil/base/runtime exige nueva revisión;
no habilitarlo automáticamente por éxito de una prueba simulada.

## 7. ReservaRedAplicacion — asignaciones reutilizables sin reciclar identidades

El pool histórico usa resource UUIDs predefinidos como slots y no se convierte retroactivamente.
Para el camino genérico, declarar slots institucionales con IP/MAC/DNS y generar un resource UUID
nuevo por asignación. `reservas_red_aplicacion`: UUID PK; identidad_id FK UNIQUE; cluster_id;
perfil_id/revision; slot_id; address; mac; host; creada_at; liberada_at; snapshot no sensible.
UNIQUE parcial (cluster_id, address) y (perfil_id, slot_id) mientras liberada_at sea nula.

Admitir bajo bloqueo de capacidad y con validación de que slots nuevos no se superponen con pools
legacy ni administración. Liberar sólo tras ausencia confirmada del recurso y su almacenamiento.
Una asignación siguiente puede reutilizar el slot, nunca el resource UUID o los secretos anteriores;
certificado/clave de instancia nuevos. No se mantiene una reserva de red sólo por existir una oferta.

## 8. Migración y reglas transversales

- Migraciones aditivas desde `010_06_acceso_aplicacion`; no borrar datos ni introducir JSON de
  evidencia en formularios. No editar manifiestos o revisiones históricas para hacerlos genéricos.
- Entidades públicas no contienen secretos, rutas del nodo o valores de variables sensibles.
- UUID/versión/hash son internos. El administrador selecciona nombres y tamaños, no gestiona FK.
- La lógica de autor y pertenencia permanece en pedido/cátedra; el cambio de titular no cambia
  el dueño histórico y sí cambia quién puede acceder hoy.
- Rama de validación nueva explícita en perfiles/evaluación/admisión/preparación/acceso; los
  caminos legacy y raw IaaS continúan usando sus verificaciones actuales.
- Probar unicidad, exclusión, orden de locks, recuperación, migración y conservación con PostgreSQL;
  SQLite cubre contratos, no demuestra concurrencia real.
