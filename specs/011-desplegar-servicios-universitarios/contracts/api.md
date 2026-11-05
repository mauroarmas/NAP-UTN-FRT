# Contrato del portal

Prefijo existente `/api/v1`. Reusar cookie HttpOnly, sesión activa, 2FA cuando esté habilitado,
CSRF/origen para mutaciones y servicios de autorización actuales. Todos los cuerpos son estrictos;
mutaciones idempotentes usan `Idempotency-Key`. No hay autorización sólo por ocultar controles.

## Catálogo administrativo

### POST `/templates/aplicaciones`

Sólo administración. Alta unificada, distinta del POST histórico de templates preparados.
Campos visibles básicos: `nombre`, `descripcion?`, `origen` y datos de origen.

- `imagen_docker`: `imagen`, `puerto`, modelo opcional (SaaS por defecto), configuración/persistencia
  únicamente si la aplicación las requiere. No recibir credenciales de registry, hashes ni perfiles
  internos desde el formulario; el servidor los deriva y verifica.
Ambas entradas de UI envían `origen=imagen_docker`; Docker Hub precarga la referencia
seleccionada. Nuevas solicitudes `community_scripts` se rechazan sin crear oferta.
No aceptar comandos de instalación ni reinterpretar registros históricos como imágenes.

Validación externa acotada antes de la transacción; revalidar permisos y perfil al confirmar.
Respuesta 201 con el template normal más `origen_despliegue`, `configuracion_id` interno,
`tamanos_permitidos`, `oferta_disponible=true` y estado de presentación `Disponible para solicitar`.
Repetir la clave devuelve el mismo resultado; no crea invitado, reserva ni ensayo. No persiste un
borrador visible si la validación falla; la UI conserva sus datos para reintentar.

### POST `/templates/{id}/configuracion`

Sólo administración. Mismos datos de origen y `revision_esperada` de oferta. Crea revisión de
configuración y cambia el puntero de la oferta en una transacción; no actualiza pedidos aprobados,
instancias ni secretos existentes. Nombre/descripción y retiro siguen usando acciones actuales.

### GET `/biblioteca/aplicaciones` y GET `/biblioteca/categorias`

Reemplazar el proveedor de búsqueda Community por Docker Hub, conservando la ruta de
búsqueda y el componente actual cuando resulte útil. Nombre y paginación acotados;
repositorio/referencia, descripción/procedencia y distintivos disponibles. No usar
el contenido de la ficha como autorización ni asumir que el Registry API v2 ofrece
búsqueda: descubrimiento Hub y resolución OCI son responsabilidades distintas.

La selección pasa por POST `/templates/aplicaciones` con `imagen_docker`, exactamente
como la referencia propia. Mostrar incompatibilidad comprobada por el resolver/perfil,
no exigir adaptadores por aplicación. Errores/rate limits del proveedor son explícitos,
no listas vacías; permitir ingresar una referencia manual y mantener catálogo interno.
No desarrollar un espejo ni cache nueva para este alcance.

GET `/biblioteca/categorias` puede devolver una lista vacía si la API elegida no las
expone. La UI omite ese filtro; no inventa categorías ni bloquea la búsqueda por nombre.
Rutas históricas 010 de incorporación/preparación permanecen sólo donde su compatibilidad
lo exija, fuera de la navegación habitual. Draw.io histórico no se reconvierte ni recrea.

## Pedidos, aprobación, programación y acceso

Conservar endpoints de creación, evaluación, aprobación, aclaración, rechazo, despliegue y servicios.

- En «Otro», referencia de imagen/instrucciones de uso opcionales son datos de la necesidad, no una
  autorización para ejecutar. No admitir credenciales embebidas en esa referencia.
- Extender selección efectiva/snapshot con configuración nueva. Evaluación firma también su hash,
  revisión de perfil y destino. No resolver fuentes cambiantes después de confirmar aprobación.
- Una intención nueva `solicitar_despliegue` permite inmediata o fecha inicial futura. Mantener
  `desplegar_inmediatamente` histórico con su significado actual; si se mandan decisiones
  contradictorias, 422. La UI ofrece una sola decisión entendible, no dos checkboxes técnicos.
- Para valores privados por pedido, entrada write-only administrativa únicamente cuando el perfil
  la exige. Cifrar antes de persistir y usar referencias/HMAC contextual en idempotencia; nunca
  guardar el cuerpo con secretos en `DecisionIdempotente`, snapshots o `contexto_seguro`.
- Respuestas ordinarias no incluyen valores sensibles. Mostrar/revelar acceso exige consulta
  explícita y pertenencia vigente, conservando la autorización previa al descifrado.

El trabajo de agenda usa la revisión aprobada y clave por pedido/revisión, conserva APROBADO hasta
admitir una operación efectiva y no ejecuta antes de inicio. Si se retira la oferta, una decisión
ya aprobada conserva su configuración salvo bloqueo técnico/de seguridad explícito del perfil.

## Reintentar

### POST `/operaciones/{id}/reintentar`

Sólo administración, CSRF, body vacío e idempotencia. Si la ejecución anterior está confirmadamente
fallida, admitir una operación `reparar` con raíz lógica e intento siguiente; 202 con el mismo
formato de operación actual y `operacion_raiz_id`/`intento_efectivo` adicionales.

Si hay trabajo en curso, incertidumbre de identidad/resultado o vigencia ausente, 409 sin crear
otro intento. Una respuesta de inicio perdida se reconcilia; no se trata como un fallo confirmado.
Si el recurso fue retirado con ausencia confirmada, reclamar otra identidad y validar capacidad
antes de un nuevo efecto. No alterar la configuración aprobada para hacer pasar el reintento.
Conservar valores y referencias de secretos de aplicación del mismo pedido incluso si se recrea
el recurso. Generar otro resource UUID/nonce y claves TLS de infraestructura; un nuevo pedido de alta sí
genera sus propios secretos de aplicación; una renovación conserva los del alta original. No interpretar un reintento como un nuevo pedido.

## Consola administrativa de lectura

### GET `/operaciones/{id}/consola`

Resolver raíz lógica y exigir **administrador actual**, no sólo permiso para consultar el estado
de una operación propia. Parámetros: `after` exclusivo o `before` exclusivo (mutuamente excluyentes),
`limit_bytes` 1–65536, `through_seq?` para exportación. Sin cursor, devolver el último lote retenido;
la respuesta indica ese rango y permite pedir mensajes anteriores.

Respuesta 200:

| Campo | Significado |
|---|---|
| operation_id, operacion_raiz_id | Consulta y agrupación efectiva |
| estado, fase, intento_efectivo | Estado seguro y número estable de instalación |
| items | seq, intento, captured_at, fase, stream y texto depurado, tanto del portal como del runner |
| next_cursor, previous_cursor, has_more | Continuación después del lote y límite para anteriores, sin repetir fragmentos |
| first_retained_seq, last_seq | Rango retenido para recuperación/exportación |
| truncated, expired, dropped_messages | Señal explícita de recorte, vencimiento o huecos |
| last_captured_at, last_ingested_at | Distinguir silencio del proceso y atraso de consulta |
| resultado_final | Resumen independiente del texto purgado |

Consulta cada 1 s sólo con consola visible. Si `after` queda detrás del rango retenido, devolver
el rango disponible y aviso de salto; no fingir continuidad. Registro vencido devuelve cabecera,
resultado y `expired=true`, no un 404 que sugiera operación inexistente. SQL/cursor no se expone
como identidad de infraestructura ni contiene credenciales.

La consulta también funciona si la creación falla antes de existir un job del nodo: devuelve los
hitos seguros del portal y el resultado, sin exigir runner_job_id. Ambos productores comparten
secuencia/cuota/retención; su deduplicación interna está definida en `data-model.md`. El cursor
público sigue siendo seq de la raíz y no el source_seq privado del runner.

Copiar/descargar es una acción explícita de la UI: fijar `through_seq=last_seq`, pedir las páginas
retenidas y formar texto plano. Revalidar permisos en cada página; abortar ante revocación y no
persistir el registro en localStorage ni caché. La UI informa si hubo purga durante la exportación.
No hay endpoint de escritura de consola, comando libre ni PTY. Cerrar la consola no cancela nada.

## Respuestas y errores comunes

- 401 sesión inválida/vencida; 403 rol/alcance/origen no autorizado; 404 recurso inexistente.
- 409 revisión/capacidad/estado/perfil incompatible o reconciliación pendiente.
- 422 datos/formato/rutas de persistencia/variables no admitidos.
- 502 fuente/infraestructura inaccesible; no confundir con búsqueda sin resultados.
- `Cache-Control: no-store`. Nunca devolver stderr crudo, traceback, credenciales, rutas privadas
  o comandos fallidos con valores de configuración.

Las rutas públicas de este documento son contratos de diseño; no se consideran implementadas por
su presencia aquí. Los endpoints y formatos existentes conservan compatibilidad de lectura.
