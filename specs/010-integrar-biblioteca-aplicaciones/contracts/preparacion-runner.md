# Contrato de construcción, artefactos y Draw.io

## Separación de ejecución

- API: decisiones y persistencia; ninguna instalación en proceso HTTP.
- Worker de ensayos: coordina operaciones durables, leases y capacidad.
- Host builder aislado: resolución y construcción de rootfs limpio mediante receta instalada, nunca en el nodo operativo ni en un guest académico.
- Worker/servicios PVE: creación, tareas/UPID, ownership y limpieza de dos LXC de ensayo.
- Guest runner: bootstrap acotado en la imagen preparada; no descarga Community Scripts ni instala paquetes por pedido.

## `nap-build-runner/1` — nuevo

Transporte SSH con hostkey fijada, cuenta dedicada y forced-command institucional; privilegio acotado al host builder. Un mensaje JSON cerrado por stdin, una respuesta JSON segura. Prohibidos shell libre, URLs/rutas elegidas por cliente, secretos de cátedra y credenciales PVE. La implementación compartirá utilidades de límites del runner actual sin ampliar su lista de comandos.

Solicitud: `protocol`, `operation_id`, `ensayo_id`, `action`, `recipe_id`, `recipe_revision`, `input_sha256` y `input_ref` institucional. Acciones: `resolve`, `build`, `status`, `stage`, `cleanup`. `resolve` usa catálogo de fuentes aprobado en configuración; `build` exige entradas exactas previamente confirmadas y registradas. No recibe `latest`, rangos ni scripts remotos. `stage` sólo distribuye a destinos institucionales permitidos mediante credencial acotada y confirma hashes por destino; no publica ofertas.

Respuesta: `protocol`, `operation_id`, `job_id`, `status` (`accepted`, `running`, `succeeded`, `failed`, `unknown`), `observed_at`, `result` con referencias/digests/tamaños y código de fallo seguro. No responde archivos arbitrarios, logs sin filtrar ni secretos. Petición máxima 64 KiB, respuesta máxima 256 KiB; inventario grande por archivo institucional referido con digest. Control interactivo total 10 s; construir es trabajo durable consultado con `status`, no proceso que requiera mantener SSH abierto. Deadline de trabajo y presupuesto de disco desde perfil; si el ensayo vence, el worker cerca la operación y ordena detener/limpiar al builder.

Repetir `operation_id`+digest devuelve el mismo trabajo; digest distinto es conflicto. `status` debe distinguir trabajo ausente de estado desconocido. Tras perder confirmación se consulta antes de volver a construir. Directorio temporal exclusivo por ensayo/operación; cleanup verifica dueño y nunca acepta una ruta del navegador. Fencing por generación evita que el resultado de un worker vencido publique o recree recursos. Un lock local por trabajo serializa acciones builder.

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

La validación exige evidencia con creación/edición/exportación local `.drawio`/reapertura conservando contenido; acceso sin credenciales y con credenciales de otra instancia denegado; no copiar credenciales entre ensayos; repetir bootstrap y reiniciar sin regenerarlas. Comprobar que el circuito mínimo no requiere recursos web del proveedor. PDF, colaboración, almacenamiento cloud y conectores externos no son criterios del piloto.

Actualizar schemas de evidencia/validación y validadores del builder/portal en paralelo. Conservar como fixtures evidencia 009 y nuevos ejemplos 010 válidos/inválidos, sin declarar una evidencia sintética como ensayo realizado.

## Guest runner y acceso por instancia

Ampliar registros cerrados de `nap-guest-runner/1` para `drawio`, parámetros y secreto `access_password`; no aceptar un comando/recipe_id arbitrario desde el guest. `node_executor` comprueba identidad, pool, nonce y bundle antes de `pct exec`, y acepta el nuevo bootstrap instalado. Para ensayos se exige propietario institucional de ensayo; no asumir que la ausencia de pedido concede acceso.

Bootstrap: contraseña persistida/cifrada antes del dispatch, usuario de perímetro derivado de UUID, nginx TLS con material de esa identidad, Tomcat en loopback y configuración de contexto del editor. Reutilizar la reserva de red institucional para SaaS, extendiendo las ramas hoy limitadas a PostgreSQL/BookStack. No generar alumnos ni usuarios nativos Draw.io. No reiniciar/resetear contraseña al reintentar si la operación anterior ya se aplicó.

Respuesta de bootstrap/probe: campos cerrados `ready`, `bootstrap_completed`, `host`, `address`, `addresses`, `port`, `endpoint`, `username`, `checks`; endpoint HTTPS exacto del perfil, usuario exacto de UUID y check Draw.io correspondiente. Para ensayos se valida el artefacto de construcción y su ownership mediante un camino específico; no relajar la exigencia de definición publicada del bootstrap académico. El probe comprueba editor/runtime y perímetro, no sólo puerto abierto. Respuesta local no activa una instancia: conservar la evidencia externa por servicio y gate de verificación existentes. Contraseña, Authorization y certificados privados no aparecen en resultados ni logs.

Prueba cruzada: NAP deniega consulta/operación fuera de cátedra; el HTTPS de B rechaza contraseña de A y petición anónima. El puerto Tomcat no es accesible desde redes de clientes. Credenciales iniciales sólo se revelan desde endpoint autorizado, con auditoría y `no-store`, nunca en URL/correo/historial.
