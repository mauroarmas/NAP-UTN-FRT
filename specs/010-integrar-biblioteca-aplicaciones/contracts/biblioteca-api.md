# Contrato de biblioteca y preparación

Contrato propuesto, no API implementada. Rutas relativas al prefijo API existente. Autenticación propia y CSRF/manejo de sesión vigentes. Todas las rutas de este documento requieren rol administrador con acceso operativo. JSON cerrado, sin secretos en respuestas generales; fechas ISO-8601 UTC. Las lecturas llevan `Cache-Control: no-store` hacia navegador.

## Convenciones

Mutaciones requieren `Idempotency-Key`; repetir misma clave/payload devuelve resultado original, distinta carga con la misma clave devuelve 409. Restricciones de unicidad de dominio evitan duplicados incluso con claves distintas. Ediciones y acciones de estado incluyen `revision_esperada`; conflicto 409 con revisión actual, preservando el formulario. Trabajos largos responden 202 una vez confirmada la intención durable y entregan `ensayo_id`, `operacion_id`, `estado` y URL de consulta. No hacer I/O largo manteniendo transacciones abiertas.

Errores conservan formato institucional `detail.codigo`, mensaje y datos seguros: 401 sesión, 403 rol, 404 objeto, 409 conflicto/estado/indisponibilidad de preparación, 413 tamaño, 422 validación, 502 fallo de infraestructura/proveedor. Un recurso ajeno sigue la política de no exposición existente.

## Búsqueda externa

`GET /biblioteca/aplicaciones?q=draw.io&categoria=diagramas&cursor=...&limit=20`

- `q`: opcional, 1–100 caracteres cuando se informa, comparación normalizada de nombre/alias; categoría opcional validada contra índice NAP. Exigir al menos uno de `q` o `categoria`; permitir categoría sin texto y rechazar ambos ausentes/vacíos con 422. Si se informan ambos, combinar filtros con AND. `limit` 1–50, cursor opaco ligado a revisión de índice/filtros.
- Resultado: `{items, next_cursor, fuente: {proveedor, revision, consultada_at, cache, estado}}`.
- Item: `{identidad_externa, nombre, descripcion?, categorias, procedencia_datos, comando_origen, url_origen, revision_fuente, version_externa?, requisitos?, compatibilidad, faltantes}`. Compatibilidad es `sin_comprobar`, `no_soportada` o `adaptador_disponible`; la última no equivale a comprobada/publicada.
- Sin coincidencias: 200 y `items: []`. Fallo externo sin cache utilizable: 502 `proveedor_no_disponible`. Con cache previa: 200, `fuente.estado: desactualizada`, fecha y aviso explícitos; no presentar la cache como respuesta actual sin advertencia. 403/429 del proveedor se mapean a indisponibilidad con `reintentar_desde` si se conoce.
- Sólo repositorio/host/rutas permitidos. Resolver SHA de commit, recorrer árbol `ct/` sin truncamiento inadvertido, construir índice hasta 10.000 entradas/8 MiB; si `truncated` impide completarlo, recorrer subárboles o fallar explícitamente. Límite total 10 s, timeout de conexión 3 s, respuesta acotada. Cache servidor 15 min y refrescos coalescidos; no una llamada externa por pulsación de tecla. Token GitHub opcional sólo de configuración, nunca desde navegador.
- No analizar/ejecutar shell. Comando informativo generado exclusivamente desde una ruta `.sh` simple y revisión permitidas. No aceptar URL arbitraria ni redirigir fuera de hosts permitidos. Se registra digest de contenido fuente para procedencia.

## Incorporación editable

| Método/ruta | Entrada | Resultado |
|---|---|---|
| `POST /biblioteca/incorporaciones` | Identidad externa y revisión devueltas por búsqueda | 201 borrador o 200 existente; `incorporacion_id`, datos y `faltantes` |
| `GET /biblioteca/incorporaciones` | Filtros y paginación | Borradores administrativos |
| `GET /biblioteca/incorporaciones/{id}` | — | Datos de origen, ediciones, vínculo a definición y ensayos |
| `PATCH /biblioteca/incorporaciones/{id}` | revision_esperada y campos administrativos permitidos | 200 actualizado |
| `POST /biblioteca/incorporaciones/{id}/definicion` | revision_esperada, codigo, version NAP y base_definicion_id opcional | 201 nueva revisión técnica Draw.io o 200 de la misma revisión ya vinculada; 409 si pertenece a otra incorporación; rechazar otro producto sin adaptador |

El servidor valida el snapshot contra su índice/registro, no confía en un comando enviado por el navegador. Modificar descripción no cambia fuente. Incorporar no crea definición técnica ficticia, reserva, instalación ni publicación. Repetir identidad/versión externa conocida (o identidad/revisión si la versión es desconocida) devuelve borrador anterior sin sobreescribirlo. Completar el piloto permite elegir código/versión NAP y crea/vincula una `DefinicionServicio` borrador mediante el servicio existente; aplicaciones sin adaptador conservan ficha editable y limitación explícita. Una incorporación admite múltiples revisiones técnicas, listadas en su detalle. La primera no exige antecedente; las siguientes indican `base_definicion_id` de esa incorporación, conservan código/producto y usan una versión NAP semánticamente mayor. El mismo código/versión devuelve la revisión existente sin sobrescribirla. Una nueva versión no cambia la definición publicada ni el perfil hasta superar otro ensayo y publicación explícita, incluso si comando/revisión fuente no cambiaron. No es necesario reimportar ni falsificar un cambio externo.

## Ensayo

| Método/ruta | Entrada | Resultado |
|---|---|---|
| `POST /definiciones/{id}/ensayos` | incorporacion_id, revision_esperada de definición, plazo_horas, perfil_ensayo_id | 202; reserva dos LXC y presupuesto builder antes de I/O |
| `GET /ensayos/{id}` | — | Estado/fase, revisión, vencimiento/aviso, operaciones, recursos y errores seguros |
| `GET /ensayos/{id}/eventos` | Cursor | Historia append-only |
| `POST /ensayos/{id}/confirmar-entradas` | revision_esperada, entradas_sha256 | 202 construcción con lock exacto; sin comandos ni parámetros libres |
| `POST /ensayos/{id}/comprobar` | revision_esperada, evidencia_id y SHA-256 | 200 comprobada si evidencia real y resultados coherentes |
| `POST /ensayos/{id}/reintentar` | revision_esperada | 202 conciliación de fase incierta/fallida |
| `POST /ensayos/{id}/descartar` | revision_esperada, motivo | 202 cierre y limpieza |
| `POST /ensayos/{id}/reintentar-limpieza` | revision_esperada | 202; no afecta evidencia ni artefacto conservado |
| `POST /ensayos/{id}/recursos/{recurso_id}/revelar-acceso` | Acción explícita, sin datos de credenciales | Acceso sensible de ensayo, auditado y no cacheable |

`plazo_horas`: 1–168, predeterminado configurado 24. Antes de confirmar se muestra vencimiento estimado; al admitir se fija `expires_at` con reloj servidor. Aviso a 1 h del vencimiento o al inicio de plazo 1 h. Perfil de ensayo institucional determina nodo/storage/red/pool y límites; no recibe hostname/VMID/URL/shell libres. Recursos insuficientes: 409 con evaluación segura; en piloto no hay sobreasignación para ensayos. Si no existe host builder, base, receta instalada o red elegible: 409 `ensayo_no_preparado` sin crear recursos.

La admisión inicializa atómicamente la fila `PresupuestoBuilder` por scope configurado si aún no existe y la bloquea antes de reservar espacio; la primera admisión concurrente usa el mismo bloqueo que las posteriores.

La resolución produce entradas concretas que administración confirma dentro del mismo flujo NAP. Completar construcción no significa comprobación funcional. Fallos y trabajo vencido no pueden continuar creando LXC por un lease antiguo.

## Publicación de oferta

Se mantienen las rutas existentes de manifiesto, validación y retiro. Añadir:

`POST /definiciones/{id}/publicar-oferta`

Entrada cerrada: `{revision_esperada, ensayo_id, perfil: {template_id?, revision_esperada?, nombre, descripcion, default_vcpus, default_ram_mb, default_disk_gb}}`. Identificar un perfil existente o crear el primero; no aceptar tipos distintos de LXC/Software ni mínimos inferiores a los comprobados.

Éxito 200/201: `{definicion_id, template_id, template_revision, publicacion_id, limpieza_estado}`. Una transacción verifica definición validada/comprobada, hashes/replicas y evidencia; publica, crea/actualiza perfil estable, registra bitácora y encola limpieza. Si el perfil apunta a una versión más nueva o cambió de revisión, 409 y revisión administrativa. No publicar ni limpiar artefacto final con un éxito parcial. Si falla limpieza posterior, publicación sigue disponible con advertencia administrativa.

La ruta anterior `POST /definiciones/{id}/publicar` mantiene comportamiento para productos previos; para el flujo biblioteca no puede eludir los gates de ensayo/artefacto. Mantener separadas publicación técnica y oferta sólo para compatibilidad; el asistente usa la acción atómica. Retirar no borra nada y bloquea nuevas solicitudes/aprobaciones sobre perfiles sin definición vigente publicada.
