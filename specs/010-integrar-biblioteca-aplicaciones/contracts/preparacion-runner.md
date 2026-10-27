# Contrato de construcción, artefactos y Draw.io

## Separación de ejecución

- API: decisiones y persistencia; ninguna instalación en proceso HTTP.
- Worker de ensayos: coordina operaciones durables, leases y capacidad.
- Host builder aislado: resolución y construcción de rootfs limpio mediante receta instalada, nunca en el nodo operativo ni en un guest académico.
- Worker/servicios PVE: creación, tareas/UPID, ownership y limpieza de dos LXC de ensayo.
- Guest runner: bootstrap acotado en la imagen preparada; no descarga Community Scripts ni instala paquetes por pedido.

## `nap-build-runner/1` — nuevo

Transporte SSH con hostkey fijada, cuenta dedicada y forced-command institucional; privilegio acotado al host builder. Un mensaje JSON cerrado por stdin, una respuesta JSON segura. Prohibidos shell libre, URLs/rutas elegidas por cliente, secretos de cátedra y credenciales PVE. La implementación compartirá utilidades de límites del runner actual sin ampliar su lista de comandos.

Solicitud: `protocol`, `operation_id`, `ensayo_id`, `generation` (entero positivo monotónico por ensayo), `action`, `recipe_id`, `recipe_revision`, `input_sha256` y `input_ref` institucional. Acciones: `resolve`, `build`, `status`, `stage`, `cancel`, `cleanup`. `cancel` y `status` no requieren entradas de receta; el esquema cerrado diferencia campos obligatorios por acción. `resolve` usa catálogo de fuentes aprobado en configuración; `build` exige entradas exactas previamente confirmadas y registradas. No recibe `latest`, rangos ni scripts remotos. `stage` sólo distribuye a destinos institucionales permitidos mediante credencial acotada y confirma hashes por destino; no publica ofertas.

Respuesta: `protocol`, `operation_id`, `generation`, `job_id` nullable y `status` (`accepted`, `running`, `succeeded`, `failed`, `cancelled`, `not_found`, `unknown`), `observed_at`, `result` con referencias/digests/tamaños y código de fallo seguro. No responde archivos arbitrarios, logs sin filtrar ni secretos. Petición máxima 64 KiB, respuesta máxima 256 KiB; inventario grande por archivo institucional referido con digest. Control interactivo total 10 s; construir es trabajo durable consultado con `status`, no proceso que requiera mantener SSH abierto. Deadline de trabajo y presupuesto de disco desde perfil; si el ensayo vence, el worker cerca la operación y ordena detener/limpiar al builder.

Registro remoto durable por `ensayo_id`: `max_generation`, `closed` y trabajos por `operation_id`, conservado fuera del directorio temporal. Bajo lock exclusivo de ensayo, rechazar mutaciones de generación menor con `stale_generation`; aceptar una generación mayor sólo después de persistirla y cercar los trabajos de la anterior. La misma operación y digest conserva job_id incluso si cambia la generación de su propietario; otra carga con el mismo ID es conflicto. `status` es lectura y permite conciliar un trabajo de generación anterior, devolviendo también `max_generation` y `closed`; `not_found` exige ausencia comprobada en registro íntegro, `unknown` nunca autoriza recrear.

`cancel` cierra irreversiblemente el ensayo remoto: primero persiste `closed=true` y su generación, después detiene/recolecta procesos descendientes. `cleanup` exige cierre confirmado, elimina sólo temporales propios y conserva ese registro de cierre. Una orden resolve/build/stage retrasada se rechaza tras el cierre aunque presente generación mayor; otro intento de preparación requiere otro ensayo. Repetir cancel/cleanup es idempotente. Si falla el cierre o no se acredita la terminación de procesos, el resultado es incierto y no se libera presupuesto ni se confirma limpieza.

El ejecutor registra intención antes de lanzar cada proceso, verifica generación/cierre antes de cada efecto y de promover artefactos, y cerca/recolecta procesos antiguos antes de admitir otra generación. Una tarea antigua no puede instalar réplicas ni confirmar resultados después de cancel. Directorio temporal exclusivo por ensayo/operación; ninguna ruta de cleanup proviene del navegador. Pruebas obligatorias: build atrasado después de cancel/cleanup, cancel antes de un build aún no recibido, respuesta perdida, reinicio del ejecutor y persistencia del cierre. El chequeo de lease sólo en base de datos no sustituye este control remoto.

## Paquete institucional inmutable

Conservar:

1. Rootfs LXC `*.tar.gz` de Ubuntu 24.04 amd64 con runtime/aplicación ya instalados.
2. `recipe.tar.gz` con bootstrap/probes admitidos y digest.
3. Entradas fijadas: base y fuentes/digests, inventario/lock de paquetes, revisiones y versiones efectivas.
4. Manifiesto draft y luego manifiesto validado, evidencia e inventario de réplicas verificadas.

El worker verifica los bytes recibidos antes de registrar. Distribución usa staging temporal y cambio atómico al nombre final controlado por digest; contenido publicado es de sólo lectura. Cada nodo elegible necesita imagen visible PVE y bundle verificado en su registro root. El portal actual también verifica paths/hashes institucionales: el registro debe actualizarse mediante operación cerrada y recargable para API/workers, sin insertar secretos/rutas desde un manifiesto del usuario. Si hay varios procesos, publicación exige que todos usen revisión de registro coherente; esa revisión forma parte de la validación de disponibilidad. Artefacto faltante o divergente bloquea nuevos despliegues con error seguro, sin reemplazarlo por descargas remotas.

Saneamiento: excluir contraseñas/hash de contraseña, claves TLS/SSH, identidades/nonce/estado de bootstrap, diagramas, uploads, sesiones, caches y logs de ensayo. El artefacto maestro se construye antes de crear los LXC de comprobación; nunca se reconstruye desde uno usado por administración. Mantener licencias/avisos de dependencias y procedencia. Los dos ensayos posteriores prueban que el paquete puede crear instancias independientes y funcionales.

## Manifiesto `schema_version: 1.1`

Se mantienen lectores 1.0 existentes; esquema específico y cerrado para 1.1, sin cambiar archivos históricos. Extensiones requeridas:

| Concepto | Valor/regla Draw.io |
|---|---|
| product / service_model / resource_type | `drawio` / `saas` / `lxc` |
| image | Campos existentes; Ubuntu 24.04 amd64, unprivileged true, nesting false, sanitized true; digest real |
| runtime.components.drawio | versión efectiva, revisión/tag, SHA-256 del WAR |
| runtime.components.tomcat | versión exacta 11.0.x, digest de archivo oficial |
| runtime.components.java | versión efectiva de JRE 21; coherente con inventario de paquetes |
| preparation | `drawio-tomcat11-ubuntu-24.04-v1`, revisión Git comprometida, bundle_sha256, `drawio-v1`, protocolo guest existente |
| allowed_parameters | `display_name` |
| secret_metadata.generated_fields / owner_reveal_fields | `["access_password"]` |
| secret_metadata.guest_only_fields | `[]`; nonce/clave TLS se gestionan fuera de este inventario como en infraestructura actual |
| access | `https`, puerto 443, endpoint derivado del perfil institucional, TLS obligatorio |
| health | `drawio-ready-v1`, `drawio-status-v1`, timeout 1–60 s, evidencia de red obligatoria |
| persistent_paths | `["/"]` para compatibilidad de snapshots/recuperación del sistema; no promete almacenamiento centralizado de diagramas |
| validation | Dos identidades ensayadas, hashes y checks actuales más ciclo editable, perímetro autorizado y ausencia de dependencia Community Scripts |

Antes de validar/publicar, bloquear el acceso a Community Scripts y crear los dos LXC de ensayo desde el paquete institucional retenido; registrar `deployment_without_provider` ligado a sus identidades/digests. Esta prueba no requiere una oferta publicada ni pedidos académicos. Después de publicar, SC-006 verifica adicionalmente el recorrido completo con un pedido nuevo.

La validación exige evidencia con creación/edición/exportación local `.drawio`/reapertura conservando contenido; acceso sin credenciales y con credenciales de otra instancia denegado; no copiar credenciales entre ensayos; repetir bootstrap y reiniciar sin regenerarlas. Comprobar que el circuito mínimo no requiere recursos web del proveedor. PDF, colaboración, almacenamiento cloud y conectores externos no son criterios del piloto.

Actualizar schemas de evidencia/validación y validadores del builder/portal en paralelo. Conservar como fixtures evidencia 009 y nuevos ejemplos 010 válidos/inválidos, sin declarar una evidencia sintética como ensayo realizado.

## Guest runner y acceso por instancia

Ampliar registros cerrados de `nap-guest-runner/1` para `drawio`, parámetros y secreto `access_password`; no aceptar un comando/recipe_id arbitrario desde el guest. `node_executor` comprueba identidad, pool, nonce y bundle antes de `pct exec`, y acepta el nuevo bootstrap instalado. Para ensayos se exige propietario institucional de ensayo; no asumir que la ausencia de pedido concede acceso.

Bootstrap: contraseña persistida/cifrada antes del dispatch, usuario de perímetro derivado de UUID, nginx TLS con material de esa identidad, Tomcat en loopback y configuración de contexto del editor. Reutilizar la reserva de red institucional para SaaS, extendiendo las ramas hoy limitadas a PostgreSQL/BookStack. No generar alumnos ni usuarios nativos Draw.io. No reiniciar/resetear contraseña al reintentar si la operación anterior ya se aplicó.

Respuesta de bootstrap/probe: campos cerrados `ready`, `bootstrap_completed`, `host`, `address`, `addresses`, `port`, `endpoint`, `username`, `checks`; endpoint HTTPS exacto del perfil, usuario exacto de UUID y check Draw.io correspondiente. Para ensayos se valida el artefacto de construcción y su ownership mediante un camino específico; no relajar la exigencia de definición publicada del bootstrap académico. El probe comprueba editor/runtime y perímetro, no sólo puerto abierto. Respuesta local no activa una instancia: conservar la evidencia externa por servicio y gate de verificación existentes. Contraseña, Authorization y certificados privados no aparecen en resultados ni logs.

Prueba cruzada: NAP deniega consulta/operación fuera de cátedra; el HTTPS de B rechaza contraseña de A y petición anónima. El puerto Tomcat no es accesible desde redes de clientes. Credenciales iniciales sólo se revelan desde endpoint autorizado, con auditoría y `no-store`, nunca en URL/correo/historial.

### Detalles del registro implementado

`resolve` también recibe `definition_id`, `definition_key` y `definition_version` para fijar la identidad NAP del plan aprobado. `stage` acepta `validated_manifest` sólo después de comprobar evidencia; valida schema 1.1 y rechaza cambios fuera de `validation` respecto del manifiesto construido. `status` responde además `max_generation` y `closed`. El transporte limita la respuesta a 64 KiB (más restrictivo que el máximo de 256 KiB); no transportar inventarios completos por este canal.

Los destinos de distribución son montajes configurados por infraestructura, no URLs enviadas desde la API. El registro dinámico usa un archivo por `definition_key:definition_version`, con nombre SHA-256 de esa clave y reemplazo atómico. Portal, worker y runner recargan esos archivos. El cierre remoto conserva su tombstone fuera del workspace; la limpieza no borra paquetes finales. Si quedó un paquete final sin registrar en la base después de perder una respuesta, la reserva de disco permanece retenida para conciliación administrativa.
