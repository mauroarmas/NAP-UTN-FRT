# Contrato de pedidos, operaciones, vigencias y observaciones

**Feature**: 009-remediar-hallazgos-cierre | **Fecha**: 2026-10-18

Este documento define el contrato implementado en la API (`009-remediar-hallazgos-cierre`). Los ejemplos
son datos de aceptación y no crean calendario, infraestructura ni cuentas reales.
La validación con dobles no sustituye la integración real indicada en
[quickstart.md](../quickstart.md).

## Convenciones comunes

- Prefijo: `/api/v1`. JSON UTF-8 y sesión operativa verificada por el backend.
- Cada lectura y escritura aplica rol, cuenta activa, habilitación inicial y
  titularidad **actuales**. Los identificadores enviados por el cliente no prueban
  pertenencia. Listados se filtran; un identificador ajeno conocido devuelve 403
  sin contenido, y uno inexistente devuelve 404.
- `admin`: todas las cátedras; `propio`: administrador o titular vigente de la
  cátedra del pedido/servicio. Aprobar, rechazar, cancelar, asignar y modificar calendarios
  son operaciones administrativas. Reenviar admite al titular actual sólo para un pedido de su cátedra en `requiere_ajuste`.
- Fechas de cursada: `YYYY-MM-DD` en la zona institucional configurada.
  Instantes: RFC 3339 UTC con `Z`. El intervalo efectivo es
  `[inicio_at, fin_exclusivo_at)`: el día final local se admite completo.
- Los números de recursos son enteros positivos; `disk_gb` expresa GiB de
  asignación y el cálculo interno convierte a bytes. Los contadores de red
  usan enteros de bytes, nunca sumas de contadores acumulados.
- No se aceptan campos desconocidos en escrituras. No existe un diccionario
  arbitrario capaz de reemplazar VMID, nodo, recursos, volúmenes, pool de
  pertenencia, marca de identidad o `unprivileged`.
- Respuestas generales no incluyen credenciales, contraseñas, tokens de PVE ni
  comandos sensibles. `GET /servicios/{id}/acceso` entrega solo metadatos;
  `POST /servicios/{id}/acceso/revelar` entrega secretos propios mediante acción
  explícita, permisos actuales y auditoría. Ambos se detallan en
  [catalog-ui.md](catalog-ui.md).
- `Cache-Control: no-store` en decisiones, operaciones y respuestas que incluyen
  información de acceso. Una lectura ordinaria no dispara aprovisionamiento,
  captura de métricas ni envíos de correo.

Error de negocio uniforme:

```json
{
  "detail": {
    "codigo": "sin_capacidad",
    "mensaje": "El servicio sigue pausado. Podés reintentar dentro de su vigencia.",
    "reintentable": true,
    "campos": {},
    "operation_id": null
  }
}
```

`campos` y `operation_id` son opcionales. No se devuelven trazas ni respuestas
crudas con secretos de infraestructura. Los fallos estructurales de validación
utilizan 422 con indicación de campos; el adaptador de errores mantiene un código
y mensaje legibles para la interfaz.

| Estado HTTP | Significado |
|---|---|
| 200 / 201 | Consulta o decisión local terminada / entidad creada. |
| 202 | Operación externa admitida; su efecto todavía no está confirmado. |
| 401 | Sesión ausente, vencida o revocada. |
| 403 | Falta de rol, habilitación o pertenencia; no se ejecuta efecto. |
| 404 | Recurso inexistente o fuera de los listados vigentes solicitados. |
| 405 | Método retirado, incluyendo cambio genérico de estado. |
| 409 | Conflicto de estado, capacidad, vigencia, revisión o idempotencia. |
| 422 | Contenido inválido, incompleto o incompatible. |
| 502 | Dependencia no verificable antes del envío; no se presume disponibilidad. |
| 503 | Copia restaurada pendiente de habilitación, o acceso inicial que requiere reemisión autorizada. |

Durante una restauración pendiente, login/autenticación devuelven `restauracion_pendiente` y `Cache-Control: no-store`. Después de habilitar, una cuenta con contraseña inicial recuperada sigue bloqueada con `acceso_inicial_requiere_reemision` hasta que administración entregue una nueva. No hay endpoint para preparar/habilitar restauraciones: se hace por CLI de mantenimiento sobre una copia explícita, con identidad de operador, referencia y ensayo revisado. Worker/scheduler/outbox usan el mismo bloqueo antes de reclamar trabajo.

## Regularización de registros históricos (T125)

Sólo administración actual puede usar estos POST. Las respuestas llevan `Cache-Control: no-store`; los dos comandos de decisión requieren `Idempotency-Key`.

| Endpoint de servicios | Cuerpo y resultado |
|---|---|
| `POST /servicios/{id}/regularizacion/evaluar` | `{}` o `{ "canonico_id": 123 }`. Devuelve `fuente_sha256`, posibilidad de regularizar/archivar, motivos, conflictos y configuración observada; fechas desconocidas son `null`. Consulta explícita, sin mutar infraestructura. |
| `POST /servicios/{id}/regularizacion` | Huella, `nombre`, `modelo_servicio`, `asignacion` exactamente observada, `desde`, `hasta`, `referencia` y `motivo`. 200 con servicio/bitácora y acceso `no_verificada`; `operation_id` sólo si se solicitó pausa fuera de cobertura, todavía pendiente. |
| `POST /servicios/{id}/regularizacion/archivar-duplicado` | Huella, `canonico_id`, `referencia`, `motivo`. 200 con registro archivado y principal. No elimina el recurso ni libera compromisos. |

La huella cubre datos, pedido, períodos, identidad, compromiso y observación. Una decisión reevalúa antes de escribir y serializa con el bloqueo de capacidad. Rechaza cambios de fuente/propiedad/configuración y operaciones abiertas con 409. No acepta campos libres de acceso, identidad ni recursos. La selección de principal no prueba propiedad. Sólo se archiva un duplicado legacy sin identidad/compromiso frente a principal comprobado de la misma cátedra. Versiones publicadas y modificación de períodos autorizados conservan sus flujos específicos. La evidencia de implementación y sus límites están en [us8-regularizacion.md](../../../docs/evidencia/009/us8-regularizacion.md).

Desde 009_13, los pedidos incluyen `compromiso_capacidad` como proyección opcional del ledger abierto: estado, cómputo/disco retenidos y `expira_at` UTC. Las cantidades autorizadas siguen en `asignacion_snapshot`. Se retiran `reserva_vcpus`, `reserva_ram_mb`, `reserva_disk_gb` y `reserva_expira_at`; no hay un segundo contador ni una caducidad editable en pedidos. `despliegue_habilitado` comprueba período, operación y ese compromiso vigente.

## Idempotencia y concurrencia

Las mutaciones de pedidos, las solicitudes de modificación de vigencias, la
verificación de acceso, las órdenes de infraestructura y `PUT /calendarios/{anio}`
requieren `Idempotency-Key` opaca, de hasta 128 caracteres. El cliente genera una
clave por intención confirmada y la conserva al reintentar una respuesta perdida.
La identidad de la petición incluye actor, método, ruta, recurso destino y hash
del contenido canónico; no se almacenan secretos en el hash ni en la respuesta
reproducible de este contrato.

- Misma clave, actor, destino y contenido: devuelve el resultado previamente
  confirmado, con el mismo identificador de entidad/operación y sin otro
  compromiso, tarea o evento histórico. `Idempotency-Replayed: true` identifica
  la repetición. La autorización actual vuelve a comprobarse antes de responder.
- Misma clave del actor con otra ruta, destino o contenido: 409
  `idempotency_key_reutilizada`. No se recicla para una nueva acción.
- Confirmaciones simultáneas de la misma clave se resuelven como una sola
  transacción; la segunda recibe el resultado registrado.
- Otra clave sobre un recurso con operación abierta: 409 `operacion_en_curso`,
  con `operation_id` y enlace a la operación existente. `incierta` sigue abierta.
  La exclusión se aplica también mediante índice único parcial sobre
  `identidad_infraestructura_id`, para que rutas, alias o pedidos distintos no
  ordenen acciones incompatibles sobre el mismo recurso real.
- Las claves de operaciones y decisiones se conservan junto a su registro
  histórico; su vencimiento no vuelve ejecutable una orden antigua. Una
  validación rechazada antes de cualquier commit no registra un efecto exitoso.

`decisiones_idempotentes` es la autoridad duradera para reproducir respuestas de
mutaciones locales, incluso si no crean operación de infraestructura: altas de
pedidos, ajustes, aprobaciones ordinarias, renovaciones, modificaciones de
vigencia, verificación de acceso y calendarios. Conserva actor/clave, método/ruta,
recurso, hash del contenido, resultado HTTP y referencia de respuesta/entidad,
sin secretos. Se escribe en la misma transacción del efecto. Las operaciones de
infraestructura conservan además su referencia idempotente y vínculo a esta
decisión cuando la admisión procede de una mutación combinada.

El lock transaccional PostgreSQL `4001` precede al lock de fila al aprobar,
iniciar, reactivar, liberar o transformar compromisos. Estado se relee dentro de
esa sección. Se confirma en una transacción el compromiso, la transición central,
el historial, la decisión idempotente y, cuando corresponde, la operación.
Esperar tareas PVE ocurre fuera de esa transacción.

`compromisos_capacidad` es el compromiso operativo. Las filas de
`identidades_infraestructura` reservan de forma única `(cluster_id, vmid)` y
guardan `resource_uuid`, nonce de propiedad, pool y nodo asignado. Permanecen
retenidas hasta confirmar ausencia; ni la baja lógica ni un timeout permiten
asignar ese identificador a otro recurso. La operación referencia esa identidad
central; no se intenta resolver la unicidad con índices independientes en pedidos
y servicios. No se adopta ni elimina un recurso por similitud de nombre.

## Pedidos y decisiones

### Crear, corregir y consultar

#### Preparación del pool de cátedra

`GET /catedras/{id}/infraestructura` exige administración actual y devuelve `Cache-Control: no-store`. Respuesta: `catedra_id`, `pool`, `estado` (`preparada`, `sin_servicios`, `requiere_atencion`), `codigo`, `mensaje`, `verificado_at` y, si corresponde, `permisos_faltantes`. La consulta no crea pools, concede ACL, adopta recursos ni escribe datos. La interfaz muestra **Sin verificar** hasta ejecutar la consulta.

La operación de despliegue prepara `catedra-{id}` después de validar reserva/vigencia y preparación del producto, antes de reclamar identidad y crear el invitado. Comprueba permisos efectivos de la cuenta API en el pool (`Pool.Allocate`, `VM.Allocate`, `VM.Audit`, `VM.PowerMgmt`), crea únicamente ese nombre si falta y vuelve a leer su estado. Si el POST pierde su respuesta o otra operación crea el mismo pool, se reconcilia por nombre; no se generan variantes ni se borra/reemplaza el pool existente. Los miembros existentes deben ser LXC de identidades comprobadas de la cátedra; lo desconocido bloquea sin cambios. Un problema `pool_*` anterior al envío del invitado cede la operación con diagnóstico y conserva la reserva para comprobar de nuevo, sujeto a la expiración ordinaria. No configura cuotas ni sustituye las verificaciones de red, consola o aplicación.

| Método y ruta | Permiso | Resultado y condición |
|---|---|---|
| `GET /pedidos/` | Operativo | 200; filtros de modelo/estado/cátedra e históricos autorizados. |
| `GET /pedidos/{id}` | Propio | 200; detalle e historial de solo agregado. |
| `POST /pedidos/` | Operativo sobre cátedra autorizada | 201; solicitud nueva válida. |
| `POST /pedidos/{id}/reenviar` | Admin o titular actual propio | 200; solo `requiere_ajuste`, vuelve a `solicitado` y avisa a administración. |
| `POST /pedidos/{id}/cancelar` | Admin | 200; solo `solicitado` o `requiere_ajuste`, sin operación externa iniciada. |
| `POST /pedidos/{id}/solicitar-ajuste` | Admin | 200; observaciones obligatorias, transición central; desde alta aprobada sin dispatch revoca la decisión anterior y libera compromiso antes del ajuste. |
| `POST /pedidos/{id}/rechazar` | Admin | 200; motivo obligatorio, transición central. |
| `POST /pedidos/{id}/revertir-aprobacion` | Admin | 200; motivo obligatorio, solo alta aprobada sin dispatch iniciado; libera compromiso atómicamente. |
| `DELETE /pedidos/{id}` | Admin | 200; baja lógica permitida por el flujo y sin recursos/compromisos sin resolver. |
| `PATCH /pedidos/{id}/estado` | Ninguno | 405; no existe una vía genérica para aprobar, cancelar, reenviar o fingir despliegue. |

Solicitud ordinaria:

```json
{
  "catedra_id": 3,
  "modelo_servicio": "paas",
  "template_id": 7,
  "descripcion_requerimientos": "Base de datos para prácticas de consultas",
  "parametros_extra": {"titulo": "Prácticas de consultas", "software_solicitado": null},
  "vigencia": {
    "tipo": "primer_cuatrimestre",
    "anio_lectivo": 2027
  }
}
```

`catedra_id` puede omitirse únicamente si hay una sola cátedra propia activa.
Modelo y plantilla deben ser compatibles, LXC y publicables; QEMU histórico se
conserva como histórico, sin habilitar nuevas solicitudes. La interfaz exige nombre y justificación pedagógica.

**Otro (PaaS/SaaS)**: permite `template_id: null` con `parametros_extra.software_solicitado` y
`descripcion_requerimientos` no vacíos. `parametros_extra` sólo admite `titulo` (máximo 200 caracteres)
y `software_solicitado` (máximo 200); la descripción admite hasta 5000. Se conserva en estado
`solicitado`, sin definición, reserva ni despliegue. Administración prepara y publica una oferta
compatible, y la selecciona en la evaluación/aprobación del pedido original. Se conservan el título,
la necesidad original y la justificación. No se aprueba una instalación arbitraria ni una oferta no validada.
IaaS sigue exigiendo una plantilla publicada. Se mantiene compatibilidad con clientes existentes que
envían un perfil concreto sin `parametros_extra`.

`reenviar` acepta los campos editables de solicitud sin sustituir la decisión separada de asignación. El titular actual puede responder una aclaración únicamente en pedidos de su propia cátedra en `requiere_ajuste`; un pedido ajeno devuelve 403 y un estado distinto devuelve 409. No permite indicar hardware, aprobar, cancelar ni alterar la asignación autorizada. Se conserva la idempotencia y se avisa a administración mediante portal/outbox de correo. `cancelar` sigue siendo administrativo y exige motivo. La interfaz denomina la devolución «Pedir aclaración» y su respuesta «Responder aclaración»; el estado técnico conserva `requiere_ajuste`.
Al cambiar modalidad se envía el objeto `vigencia` completo: las fechas de una
modalidad anterior se eliminan o resuelven de nuevo, no sobreviven por omisión.

La vigencia académica exige año entre 2026 y 9998 y período configurado; consultar o escribir `/calendarios/{anio}` también exige ese rango. Los períodos de calendario y las fechas de solicitudes nuevas no admiten valores anteriores al 01/01/2026. La personalizada exige
`tipo: "personalizado"`, `desde` y `hasta` como fechas completas; no admite rango
invertido ni fin ya pasado. No existe fallback a 180 días.

### Evaluar la selección efectiva

`POST /pedidos/{id}/evaluacion` — admin, 200, sin mutación ni reserva.

```json
{
  "asignacion": {
    "template_id": 7,
    "definicion_version_id": "3a6f39d0-2e5d-4877-a6f9-13c7ec224971",
    "vcpus": 2,
    "ram_mb": 2048,
    "disk_gb": 16
  },
  "destino": {"nodo": "pve1", "storage": "local-lvm"},
  "vigencia": {"tipo": "primer_cuatrimestre", "anio_lectivo": 2027}
}
```

`definicion_version_id` se exige para una plataforma/aplicación; una oferta IaaS
solo requiere su preparación LXC validada. Es UUID de versión inmutable; los IDs
enteros corresponden a entidades existentes, como pedido, servicio o template.
Si se solicita selección automática
de destino, se omite `destino`: la respuesta fija el destino concreto elegido y
este se incluye al aprobar. Los parámetros adicionales de producto se validan
contra su definición; las opciones de red admitidas son tipadas y administrativas.

Respuesta mínima:

```json
{
  "pedido_id": 25,
  "seleccion": {
    "asignacion": {"template_id": 7, "definicion_version_id": "3a6f39d0-2e5d-4877-a6f9-13c7ec224971", "vcpus": 2, "ram_mb": 2048, "disk_gb": 16},
    "destino": {"nodo": "pve1", "storage": "local-lvm"},
    "vigencia": {"tipo": "primer_cuatrimestre", "anio_lectivo": 2027}
  },
  "vigencia_efectiva": {
    "desde": "2027-03-01",
    "hasta": "2027-06-30",
    "zona_horaria": "America/Argentina/Tucuman",
    "inicio_at": "2027-03-01T03:00:00Z",
    "fin_exclusivo_at": "2027-07-01T03:00:00Z",
    "calendario_revision": 2
  },
  "costo_incremental": {"vcpus": 2, "ram_mb": 2048, "disk_gb": 16},
  "libre_antes": {"vcpus": 4, "ram_mb": 6144, "disk_gb": 80},
  "libre_despues": {"vcpus": 2, "ram_mb": 4096, "disk_gb": 64},
  "storage_scope": "node:pve1:local-lvm",
  "excede_capacidad": false,
  "justificacion_requerida": false,
  "capacidad_token": "eval-25-rev8-a7c3",
  "observado_at": "2026-10-18T15:00:00Z"
}
```

También se informan límites físicos, margen del anfitrión, consumo externo,
compromisos y restricciones de storage lógico/físico que causen un exceso; un
único total del clúster no sustituye el destino elegido. Storage compartido se
deduplica por scope y recursos propios materializados no se suman otra vez como
externos o reservas no materializadas. La renovación tiene costo incremental
cero al registrar condiciones; no garantiza cómputo para una reactivación futura.

El token une selección efectiva, revisión del pedido/template/definición y
calendario, destino, inventario y revisión de compromisos. Se recalcula dentro
del lock al aprobar. Una edición de la selección obliga a evaluar otra vez.
`GET /pedidos/{id}/evaluacion` anterior se retira con 405 y `Allow: POST`; los
clientes del repositorio se actualizan en la misma entrega.

### Aprobar

`POST /pedidos/{id}/aprobar` — admin. Cuerpo: la misma `asignacion`, `destino` y
`vigencia` normalizadas de evaluación, más `capacidad_token`,
`justificacion_capacidad?` y `desplegar_inmediatamente` booleano, por defecto false.

- Token obligatorio; ausencia 422, selección/revisiones cambiadas 409
  `evaluacion_desactualizada`, con instrucción de evaluar y confirmar nuevamente.
- Falta de disponibilidad verificable: 502 `capacidad_no_verificable`, sin
  aprobación. Exceso sin justificación administrativa: 409
  `justificacion_capacidad_requerida`, con cifras de la evaluación vigente.
- Alta: copia asignación, producto y fechas autorizadas, fija destino y compromiso
  desde aprobación, registra transición a `aprobado` y devuelve 200.
- Alta futura: `compromiso_capacidad.expira_at = min(fin_exclusivo_at,
  max(aprobado_at, inicio_at) + 24 horas)`. Devuelve `disponibilidad:
  "esperando_inicio"`; no crea LXC ni programa un inicio automático.
- `desplegar_inmediatamente: true` solo es válido para alta ya habilitada por
  fecha y vigente. Antes del inicio: 409 `inicio_futuro`, sin aprobación parcial.
  Si es válido, aprobación, compromiso y operación se admiten juntos y devuelven
  202 con `Location` de operación. La petición no espera la creación física.
- Renovación: registra una nueva vigencia del mismo servicio y las transiciones
  centrales hasta `activo`, con ejecutor real de registro de condiciones e
  historial; devuelve 200. `activo` en **ese pedido de renovación** significa
  condiciones registradas, no recurso encendido. La UI muestra **Renovación
  registrada** y consulta por separado el estado del servicio. No reserva otro
  alta ni enciende recursos. `desplegar_inmediatamente` no se admite en renovación.
- Repetir la decisión con la misma clave no agrega períodos ni historial. Una
  segunda clave tras la resolución devuelve 409 `estado_incompatible`.

Las fechas aprobadas son snapshot. Corregir calendario, plantilla o definición
no cambia compromisos existentes. El cliente no puede sustituir fechas aprobadas
por otras al desplegar.

Una alta aprobada sin dispatch puede volver a ajustes por la acción nombrada:
se revoca su revisión de decisión y se libera el compromiso en la misma
transacción. Reenviar y aprobar nuevamente crea otra `revision_decision` y otro
snapshot; la decisión previa y su vigencia permanecen históricas y no otorgan
cobertura. La unicidad de vigencias es `(pedido_id, revision_decision)`, no una
restricción que impida registrar una segunda decisión del mismo pedido. La
reversión terminal conserva su motivo e historial; una nueva solicitud posterior
no reutiliza su reserva ni su clave idempotente.

## Órdenes de infraestructura

| Método y ruta | Permiso | Condiciones adicionales |
|---|---|---|
| `POST /servicios/desplegar/{pedido_id}` | Admin | Alta aprobada vigente y habilitada, reserva válida, sin operación abierta. |
| `POST /pedidos/{pedido_id}/reintentar` | Admin | Pedido con fallo recuperable, sin resultado abierto; reconciliación previa y decisión/capacidad vigentes. |
| `POST /servicios/{id}/start` | Propio | Recurso detenido/pausado, cobertura actual y admisión indivisible de CPU/RAM. |
| `POST /servicios/{id}/reactivar` | Propio | Alias de negocio para recurso pausado, idénticos controles y ejecutor de `start`. |
| `POST /servicios/{id}/stop` | Propio | Recurso existente en ejecución; conservar compromiso hasta detención confirmada. |
| `POST /servicios/{id}/restart` | Propio | Recurso en ejecución y vigencia actual; confirmar tarea y retorno al estado esperado. |
| `POST /servicios/{id}/reboot` | Propio | Alias de `restart`, misma idempotencia y operación. |
| `DELETE /servicios/{id}` | Admin | Baja física y luego lógica; detener si corresponde, esperar y confirmar ausencia. |

Cuerpo vacío para órdenes sobre un servicio. El reintento puede incluir `motivo`
no sensible, pero no destino/recursos alternativos. La ruta de despliegue recibe
cuerpo vacío: el snapshot aprobado ya contiene destino y asignación; los antiguos
campos libres `node`/`storage` se rechazan con 422. Una reasignación necesita una
nueva decisión trazable, no otro parámetro de despliegue.

Resultado de admisión, sin afirmar efecto completado:

```http
HTTP/1.1 202 Accepted
Location: /api/v1/operaciones/0f59d08c-1094-4e8d-8fa4-ab7b4135c096
Retry-After: 2
```

```json
{
  "operation_id": "0f59d08c-1094-4e8d-8fa4-ab7b4135c096",
  "estado": "pendiente",
  "tipo": "desplegar",
  "pedido_id": 25,
  "servicio_id": null,
  "mensaje": "Despliegue admitido. Todavía no está disponible."
}
```

Errores deterministas antes de dispatch: 409 `inicio_futuro`,
`vigencia_vencida`, `sin_cobertura_actual`, `reserva_caducada`, `sin_capacidad`,
`operacion_en_curso` o `estado_incompatible`; 422 `configuracion_incompatible`;
502 `infraestructura_no_verificable`. No crean recursos ni anuncian éxito.
Sobreasignar en un inicio docente no es una salida alternativa a `sin_capacidad`.

Si una orden ya produjo dispatch y el resultado no se sabe, la operación queda
`incierta` y la API sigue devolviendo 202 para su admisión/repetición. Un timeout
posterior no se transforma en un 502 que sugiera reenviar una orden nueva. La
operación queda consultable y conserva identidad y capacidad necesarias.

Una orden sin efecto necesario confirmado —por ejemplo una baja ya aplicada—
devuelve 200 con `sin_cambios: true`, sin nueva tarea ni segundo evento. Si no
puede confirmarse que el efecto ya está aplicado, se tramita una reconciliación;
no se deduce ausencia de un fallo de red. Un `start` sobre recurso que ya está
confirmado en ejecución no duplica consumo.

### Consultar y recuperar la operación

`GET /operaciones/{id}` — propio; 200 incluso cuando su resultado de negocio es
fallido. `GET /operaciones?pedido_id=25` o `?servicio_id=9` filtra por el recurso
autorizado, con `limit` entre 1 y 100 y cursor opaco.

```json
{
  "id": "0f59d08c-1094-4e8d-8fa4-ab7b4135c096",
  "tipo": "desplegar",
  "estado": "incierta",
  "fase": "verificar_recurso",
  "pedido_id": 25,
  "servicio_id": null,
  "creada_at": "2027-03-01T12:00:00Z",
  "actualizada_at": "2027-03-01T12:03:00Z",
  "confirmada_at": null,
  "mensaje": "No pudimos confirmar el resultado. Estamos comprobando el recurso.",
  "error": {"codigo": "resultado_no_confirmado", "reintentable": false},
  "accion_recomendada": "esperar_reconciliacion"
}
```

Estados: `pendiente`, `en_curso`, `confirmada`, `fallida`, `incierta`. Los datos
internos de UPID, VMID, lease, red y configuración solo se añaden a la proyección
administrativa cuando ayudan al diagnóstico; la cátedra opera con IDs del portal.
El resultado confirmado puede incluir `servicio_id` y resumen del cambio, nunca
secretos generales. Un fallo seguro informa si requiere reintento o nueva aprobación.

Tipos canónicos: desplegar, iniciar, detener, reiniciar, pausar, eliminar y
reparar; los alias HTTP se normalizan antes de persistir.

Para una creación, `confirmada` describe recurso, bootstrap y salud local
comprobados. La operación de infraestructura termina en ese momento: no se
retiene un lease ni una operación abierta esperando a una persona. Hasta registrar
la comprobación de acceso desde la red prevista, el servicio permanece
`disponibilidad_aplicacion: "no_verificada"` y el pedido `en_despliegue`, con
siguiente paso administrativo **Verificar acceso**. El compromiso ya materializado
sigue contando. Consultar una operación confirmada no convierte por sí solo el
pedido en activo ni anuncia que el alumnado puede usar la aplicación. Otra orden
de despliegue sobre ese pedido devuelve 409 `verificacion_acceso_pendiente`, sin
crear un segundo recurso.

El dispatcher persistente reclama trabajo mediante `FOR UPDATE SKIP LOCKED`,
lease y generación; las confirmaciones y liberaciones comprueban dueño. Se
persiste `dispatch_started` antes de enviar y UPID cuando se recibe. Tras un
reinicio se consulta tarea/recurso y marca propia; nunca se repite ciegamente un
POST cuyo envío pudo ocurrir. Un worker anterior no puede confirmar ni borrar el
lock del nuevo dueño. No se requiere Celery ni cola externa.

Timeouts iniciales: 5 s por consulta de inventario, 10 s por conexión/lectura PVE,
60 s de presupuesto de observación de acciones y 180 s para creación. Estos dos
últimos presupuestos limitan la espera, **no cancelan la tarea de PVE** ni liberan
compromisos. Polling inicial cada 2 s y reconciliación al menos por ciclo de un
minuto mientras exista trabajo abierto, con backoff en caída persistente y último
intento visible. Las llamadas síncronas se ejecutan fuera del event loop con
concurrencia limitada; una operación lenta no bloquea consultas independientes.

`GET /admin/jobs` y `POST /admin/jobs/{nombre}` permanecen administrativos. La
ejecución manual utiliza el mismo lock/servicio que el planificador; un job ya
tomado devuelve 409. `reconciliar_operaciones` recupera las abiertas mediante sus
registros duraderos; iniciar manualmente el job no crea otra orden para el recurso.

## Renovaciones y servicio visible

`POST /servicios/{id}/renovar` — propio, 201; recibe `vigencia` con el mismo
formato de solicitud y crea un pedido `tipo: "renovacion"`, asociado al servicio
existente. Una renovación pendiente equivalente devuelve 409
`renovacion_pendiente`; repetir la misma clave recupera el pedido ya creado.

La aprobación preserva períodos distintos. En un intervalo sin cobertura se
rechazan inicio/reactivación/reinicio; una renovación pendiente o futura no
prorroga el período actual. La pausa conserva datos, identidad y disco. En el
inicio del nuevo período se habilita solicitar reactivación sujeta a capacidad;
no se garantiza CPU/RAM retenidas ni se crea otro contenedor.

### Modificar una vigencia autorizada

`POST /servicios/{id}/vigencias/{vigencia_id}/modificaciones` — admin, 201;
requiere `Idempotency-Key`. La vigencia debe corresponder al servicio y no estar
revocada ni sustituida. Crea un pedido de renovación/modificación sin alterar
todavía la cobertura autorizada.

```json
{
  "sustituye_vigencia_id": "7ca96c89-1b93-4b51-b357-f59a24549503",
  "motivo": "Corrección de fechas aprobada por coordinación académica",
  "vigencia": {
    "tipo": "personalizado",
    "desde": "2027-03-01",
    "hasta": "2027-07-15"
  }
}
```

El identificador del cuerpo coincide con el de la ruta y el motivo no puede estar
vacío. El pedido registra `sustituye_vigencia_id`, cátedra, servicio y snapshot
actual de asignación/producto/destino. La respuesta 201 incluye `pedido_id`,
`servicio_id`, `tipo: "renovacion"`, `sustituye_vigencia_id` y estado `solicitado`.
No reserva ni libera capacidad y no sustituye el período mientras espera decisión.

Se evalúa y aprueba mediante las rutas ordinarias de pedido. La evaluación liga
también el período objetivo, revisión de servicio y motivo; no permite reemplazar
recursos, producto, contenedor o destino. Todas las renovaciones de esta entrega
conservan la asignación del servicio, aunque su plantilla/definición histórica se
haya retirado del catálogo. Cambiar recursos no se oculta como corrección de fechas.
El costo incremental de registrar condiciones es cero.

Al aprobar, bajo los bloqueos comunes y de servicio, se agrega una nueva vigencia
que refiere a la sustituida y se registra la decisión/historial. Solo entonces la
nueva revisión concede cobertura y la anterior deja de concederla; no se borran
fechas ni decisiones pasadas. Se comprueba el solapamiento contra las demás
vigencias, excluyendo la que se sustituye. La renovación ordinaria no incluye
`sustituye_vigencia_id` y no modifica otros períodos. Conflicto concurrente o
objetivo ya sustituido: 409 `vigencia_desactualizada`, sin sustitución parcial.
Una modificación no elimina avisos ni controles de pausa/vencimiento aplicables;
la historia conserva la cobertura que autorizaba cada decisión antes del cambio.

Las respuestas `GET /servicios/` y `GET /servicios/{id}` exponen por recurso:

- `modelo_servicio` y asignación históricos, independientemente del template
  actual; `estado`, `confirmado_at`, `observado_at` y estado de confirmación.
- Períodos autorizados, cobertura actual, próximo inicio y fin efectivo; una
  etiqueta que distingue espera de fecha, despliegue pendiente, operación abierta,
  disponibilidad confirmada y pausa sin cobertura.
- `operation_id` abierto, `acciones_habilitadas` calculadas y motivo de bloqueo.
  Cada acción vuelve a validar en servidor aunque el botón estuviera habilitado.
- Antigüedad y fuente de observación: falta de confirmación no se presenta como
  apagado, vacío confirmado ni servicio utilizable. Credenciales no incluidas.

`PATCH /servicios/{id}` conserva `exento_pausado` para propio; no omite
vencimiento. Cambiar el fin mediante el campo libre `vence_at` se retira con 422:
las modificaciones de cobertura se realizan mediante la decisión de renovación,
con períodos e historial. El estado no se cambia directamente desde PATCH.

## Comprobación de acceso real por instancia

`POST /servicios/{id}/verificar-acceso` — admin, requiere `Idempotency-Key`,
200 cuando registra evidencia válida. Es una decisión de validación local del
portal; no crea otra operación de infraestructura ni espera indefinidamente por
una prueba de red. La prueba se realiza primero desde un equipo de la red prevista.
Para realizarla, administración puede revelar el acceso inicial ya preparado
después del bootstrap/health local, con estado de solo validación. La cátedra
recibe el acceso ordinario cuando se confirma la red, según catalog-ui.md.

```json
{
  "evidencia_ref": "01900000-0000-4000-8000-000000000009",
  "endpoint": "https://libros-catedra.example.edu",
  "observado_at": "2027-03-01T12:10:00Z"
}
```

La referencia es el UUID devuelto previamente por `POST /evidencias`, de tipo
`acceso_instancia`, según [registro de evidencias](evidence.md) y su
[schema](evidence.schema.json). No se resuelven URLs ni rutas de archivos.
Identifica evidencia inmutable con checksum y actor, instancia
`resource_uuid`, hash del nonce de esa instancia, punto de prueba/red de origen, endpoint,
instante y resultado de la tarea funcional prevista por la definición. El backend
contrasta esa identidad y hash de nonce con su registro, la preparación/despliegue más
recientes y el acceso observado. No admite una evidencia de publicación genérica,
de otra instancia, anterior a la preparación vigente, ni un simple booleano.
`observado_at` debe coincidir con el artefacto registrado. `endpoint` debe coincidir con el aprobado/resuelto para ese servicio; no autoriza
al backend a navegar una URL arbitraria. La evidencia no incluye contraseñas en
su registro público y la respuesta no revela el nonce.

La prueba acredita, según producto, acceso al LXC propio, conexión y
escritura/lectura persistente PostgreSQL, o publicación docente y lectura por
cuenta individual BookStack desde la red alumno. Las instrucciones y evidencias
controladas se registran en la guía de aceptación; la comprobación manual no
requiere intervención del desarrollador ni cambia la receta de aprovisionamiento.

Se exige infraestructura/health local confirmados, vigencia actual y ninguna
operación incompatible. Evidencia o endpoint inválidos: 422
`evidencia_acceso_invalida`; recurso/preparación cambiados: 409
`verificacion_desactualizada`; vigencia vencida: 409 `vigencia_vencida` y aplicación
del circuito de pausa correspondiente, sin darlo por utilizable.

Tras aceptar la evidencia, una sola transacción actualiza disponibilidad a
`utilizable`, `verificado_at`, la referencia de evidencia y, si estaba pendiente
de entrega, la transición central `en_despliegue → activo`, historial y aviso de
entrega. Responde con `servicio_id`, `pedido_id`, `disponibilidad`, `verificado_at`
y `evidencia_ref`. Repetir la clave no duplica transición ni notificación.
`GET /servicios/{id}/acceso` entonces informa metadatos; revelar credenciales
propias sigue requiriendo la acción explícita del contrato de catálogo.

## Calendario lectivo

| Método y ruta | Permiso | Resultado |
|---|---|---|
| `GET /calendarios/{anio}` | Operativo | 200 con año, zona, revisión y períodos; 404 `calendario_no_configurado` si falta. |
| `GET /calendarios/{anio}/periodos` | Operativo | 200 con los períodos configurados y fechas; no inventa fechas faltantes. |
| `PUT /calendarios/{anio}` | Admin | 201 al crear; 200 al sustituir con revisión vigente; historial de actor/cambios. |

```json
{
  "revision_esperada": 0,
  "periodos": [
    {"tipo": "primer_cuatrimestre", "desde": "2027-03-01", "hasta": "2027-06-30"},
    {"tipo": "segundo_cuatrimestre", "desde": "2027-08-01", "hasta": "2027-11-30"},
    {"tipo": "anual", "desde": "2027-03-01", "hasta": "2027-11-30"}
  ]
}
```

El año de la ruta coincide con el año lectivo seleccionado; `revision_esperada: 0`
significa calendario nuevo. Una corrección requiere la revisión leída: conflicto
409 `calendario_desactualizado`. Cada modalidad aparece como máximo una vez, con
fechas completas y orden válido; los cuatrimestres no se solapan entre sí y la
modalidad anual puede incluirlos. Fechas no se restringen a meses elegidos por el
desarrollador. Un período omitido queda sin configurar; usarlo en una solicitud o
evaluación devuelve 422 `periodo_no_configurado`. Omitirlo no elimina snapshots
aprobados. La zona procede de configuración institucional y se devuelve para
rotular fechas; no la decide el navegador.

## Métricas, resúmenes y alertas

| Método y ruta | Permiso | Contrato |
|---|---|---|
| `GET /capacidad/` | Admin | Panorama por nodo/scope, origen y antigüedad del inventario; 502 si no verificable. |
| `GET /metricas/resumen` | Operativo, filtrado | Última observación por servicio autorizado mediante consulta de conjunto, sin capturas. |
| `GET /metricas/{id}/ultimo` | Propio | Último dato y edad/calidad; nunca expone una métrica ajena. |
| `GET /metricas/{id}/historial` | Propio | Período acotado, hasta 500 puntos y resolución explícita. |
| `GET /servicios/{id}/metricas` | Propio | Lectura de la última observación persistida, con su fecha; no promete tiempo real. |
| `POST /metricas/capturar` | Admin | 200; resumen de captura por el job compartido, deduplicada por intervalo. |
| `POST /metricas/capturar/{id}` | Admin | 200; misma cadencia/deduplicación, sin incrementar cobertura por repetición. |
| `GET /alertas` | Operativo, filtrado | Incidentes abiertos/cerrados propios, paginados, con fechas y resultado de recuperación. |
| `GET /alertas/{id}` | Propio | Detalle seguro y relación a servicio; estado de correo solo para admin. |

Las capturas manuales devuelven `intervalo`, `capturados`, `ya_observados`,
`sin_confirmar` y `errores` sin crear una operación de infraestructura. Un timeout
que impide capturar devuelve 502 `captura_no_confirmada`; no fabrica una muestra
en cero ni borra observaciones anteriores. Una captura parcial devuelve 200 con
cobertura/resultados por intervalo explícitos. Todas las rutas GET de métricas
leen persistencia y nunca invocan PVE, incluso si falta el último dato.

Historial acepta `desde` y `hasta` UTC, `limit` entre 1 y 500 —por defecto 100— y
`resolucion: auto|1m|1d`. Ventana solicitada debe ser completa y ordenada. Detalle
`1m` se limita a noventa días; pedir detalle purgado devuelve 422
`detalle_no_disponible`, con resolución diaria disponible. `auto` devuelve la
resolución adecuada y la informa. Para más de 500 puntos se agrega con resolución
indicada o se ofrece cursor; nunca se devuelve un subconjunto como si cubriera
todo el intervalo. Los resúmenes diarios históricos no caducan.

Ejemplo de metadatos que acompañan los puntos:

```json
{
  "servicio_id": 9,
  "desde": "2027-03-01T03:00:00Z",
  "hasta": "2027-03-01T04:00:00Z",
  "resolucion": "1m",
  "muestras_esperadas": 60,
  "intervalos_observados": 58,
  "cobertura": 0.9667,
  "ultima_observacion_at": "2027-03-01T03:59:00Z",
  "calidad": "parcial"
}
```

Cada punto incluye fecha, CPU relativa a asignación observada, memoria usada y
máximo observado, disco usado y máximo observado, tráfico del intervalo y calidad.
Un punto diario conserva medias ponderadas, máximos, tráfico válido, cobertura y
asignación que permita reconstrucción histórica. Una captura no confirmada
produce estado desconocido/error recuperable; la ausencia de muestra no prueba
inactividad ni caída. No hay datos y datos no consultables se distinguen en la
respuesta y en la UI.

Colector/evaluador trabajan por intervalos de un minuto con unicidad por
servicio/intervalo, secuencia de observación y calidad persistida. El tráfico se
obtiene por diferencia de contadores y detección
de reinicio; los intervalos incompletos no se reemplazan por capturas duplicadas.
La inactividad exige al menos 80 % de intervalos válidos en siete días, CPU bajo
5 % y tráfico válido inferior a 1 000 000 bytes, seguida de aviso y gracia de
48 horas. Sin cobertura suficiente no se ejecuta una pausa por inactividad.

Alertas: caída tras dos observaciones confirmadas separadas al menos un minuto;
CPU o memoria sobre 90 % de asignación durante quince minutos con cobertura
suficiente; recuperación tras dos observaciones normales separadas un minuto.
Una condición persistente tiene una apertura y una recuperación; no una apertura
por ciclo. Correo caído no borra el incidente ni revierte operaciones; su fallo
y reintento son observables para administración. El destinatario docente solo
recibe información de su cátedra, sin credenciales de acceso.

## Validación contractual pendiente de implementación

La implementación debe aportar regresiones para cada cambio de contrato,
concurrencia real con PostgreSQL, recuperación ante caída entre dispatch/UPID y
éxito/commit, resultados inciertos, calendarios corregidos tras aprobación,
recesos sin cobertura, recursos externos y storage compartido, métricas ajenas,
contadores reiniciados e intervalos duplicados. Se documentan evidencia simulada
y evidencia real por separado. Este contrato no acredita que esas pruebas ni
los endpoints propuestos ya estén operativos.
