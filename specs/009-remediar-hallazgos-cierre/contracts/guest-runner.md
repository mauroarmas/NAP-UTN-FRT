# Contrato del runner de personalización de invitados

Versión: `nap-guest-runner/1`. Contrato implementado en el repositorio para FR-014, FR-019–FR-022, FR-035–FR-038, FR-061–FR-063 y FR-073 (`infra/runner/nap_guest_runner.py` y recetas en `infra/services/`). La instalación en nodos reales del clúster universitario requiere la validación externa de infraestructura (`T102`).

## Responsabilidad y transporte

Proxmox API crea el LXC desde una imagen saneada identificada por digest. El runner ejecuta una preparación fija dentro de ese invitado y devuelve información comprobada. No existe en este diseño una API Proxmox de ejecución arbitraria; las operaciones internas son `pct push` y `pct exec` mediante un wrapper de infraestructura.

El worker invoca OpenSSH mediante `subprocess`, con argumentos separados y sin `shell=True`. Se usa un ejecutable remoto constante, `forced-command` en la clave autorizada y JSON por stdin. No se añade Paramiko. El proceso HTTP no conserva una sesión SSH root general ni ejecuta el bootstrap en su event loop.

- Cuenta SSH dedicada sin shell libre, sin PTY, agent/X11 forwarding ni túneles. `sudo` autoriza únicamente el wrapper fijo; no autoriza `pct`, intérpretes o shells con argumentos libres.
- `StrictHostKeyChecking=yes`, archivo `known_hosts` suministrado por infraestructura, `IdentitiesOnly=yes` y `BatchMode=yes`. Una hostkey nueva o cambiada falla; no se usa TOFU ni `StrictHostKeyChecking=no`.
- La configuración por entorno indica rutas de clave y `known_hosts` montados en el worker. La clave privada es un archivo 0600, fuera del repositorio, la base y los logs; no se introduce su contenido en variables que se impriman ni en argumentos del proceso.
- Solo nodos de gestión previamente autorizados. El destino SSH se resuelve en configuración de infraestructura; no proviene de un hostname/URL proporcionado por el solicitante.
- Entrada UTF-8 de un objeto JSON, máximo 64 KiB, una respuesta JSON por llamada. Tiempo de conexión de 10 s, operación con deadline de hasta 180 s; polling posterior mediante la operación persistida si sigue pendiente. Salida y errores nunca incluyen secretos o comandos con valores secretos.

La instalación del wrapper, privilegios, hostkeys y conectividad son un gate operacional previo a habilitar el nodo para esa definición. Su ausencia produce `RUNNER_UNAVAILABLE`; no habilita una instalación manual por instancia como sustituto del flujo diario.

## Identidad del recurso antes de ejecutar

El worker crea y registra antes del bootstrap una identidad inmutable con `cluster_uuid`, `resource_uuid`, `nonce` aleatorio de al menos 128 bits y pool de NAP. `cluster_uuid` es el identificador de inventario de ese clúster gestionado por NAP, no un endpoint UUID de Proxmox asumido. Antes de personalizar, estos valores deben constar en configuración/marcas del LXC mediante la API Proxmox, además de en la operación persistida del portal.

El wrapper comprueba que el VMID pertenece al nodo indicado, que es LXC no privilegiado, que está en el pool permitido y que sus marcas coinciden exactamente con esa identidad y el digest esperado. La propiedad se comprueba **antes y después** de cada `pct exec` y antes de cualquier `pct push`; cualquier cambio invalida el resultado y detiene nuevas acciones. Un hostname coincidente no acredita propiedad. Esta regla también rige la adopción de un contenedor tras un fallo parcial.

El runner obtiene el bundle permitido de su registro local de recetas y verifica su digest. El invitado no elige qué bundle ejecutar. No se siguen rutas simbólicas ni se escribe en rutas del host elegidas por el cliente. La carpeta temporal del host es exclusiva por operación, privada y fuera del espacio de carga de los usuarios.

## Solicitud y resultado

Todos los campos no documentados se rechazan. El sobre de solicitud contiene:

| Campo | Tipo y regla |
|---|---|
| `protocol` | Constante `nap-guest-runner/1`. |
| `operation_id` | UUID de operación persistido en NAP; estable en reintentos. |
| `action` | Uno de `inspect`, `bootstrap`, `verify`. |
| `cluster_uuid`, `resource_uuid` | UUID de inventario y de recurso propio. |
| `node` | Nodo ya vinculado a la operación y autorizado en infraestructura. |
| `vmid` | Entero positivo, válido para la versión real de Proxmox, vinculado a la operación. |
| `pool` | Pool permitido de NAP, exactamente el registrado en configuración del recurso. |
| `nonce` | Identificador aleatorio opaco de instancia; no se usa como contraseña ni como único control de acceso. |
| `definition_key`, `definition_version` | Versión inmutable autorizada por el snapshot de aprobación. Debió estar publicada al aprobar; su retiro ordinario posterior no invalida esa aprobación ni sustituye la versión. |
| `definition_sha256`, `bundle_sha256` | Digest del manifiesto canónico y de la receta autorizada. |
| `network_profile_id` | Perfil autorizado y validado, resuelto por infraestructura. |
| `parameters` | Objeto limitado por producto y esquema de parámetros. |
| `secrets` | Solo para `bootstrap`: claves permitidas por el producto y valores de instancia. Nunca forma parte del manifiesto público. |

La respuesta contiene `protocol`, `operation_id`, `action`, `resource_uuid`, `status` (`succeeded`, `pending`, `failed` o `unconfirmed`), `phase`, `observed_at`, `identity_verified` y `result` o `error`. `result` puede contener IP comprobada, endpoint real, versión observada, resultado de probes, digest y marcas de finalización. No devuelve contraseñas, `APP_KEY`, tokens ni contenidos de `.env`. `observed_at` es fecha/hora con zona; un dato antiguo no se presenta como observación actual.

`error` contiene únicamente `code`, `phase`, `retryable` y `message` redactado. Códigos mínimos: `INVALID_REQUEST`, `IDENTITY_MISMATCH`, `DEFINITION_MISMATCH`, `UNKNOWN_RECIPE`, `UNSUPPORTED_GUEST`, `NETWORK_PROFILE_UNAVAILABLE`, `RUNNER_UNAVAILABLE`, `GUEST_NOT_READY`, `BOOTSTRAP_FAILED`, `PROBE_FAILED`, `DEADLINE_EXCEEDED`, `IDEMPOTENCY_CONFLICT` y `UNCONFIRMED`.

La IP inspeccionada debe pertenecer al perfil esperado. El endpoint se construye exclusivamente con la configuración institucional y la dirección comprobada. Ni `inspect` ni un hostname local crean DNS, rutas, certificados, NAT o una reserva de DHCP. Los perfiles de red son configuración autorizada de infraestructura, no un nuevo IPAM del portal.

El retiro ordinario impide nuevas solicitudes; el runner puede completar una aprobación anterior con su versión y digests originales, cuyos artefactos se conservan. Se verifica la autorización de la operación contra ese snapshot, sin permitir elegir una definición retirada desde el cliente. Un bloqueo urgente por seguridad es una decisión explícita y auditada distinta del retiro ordinario; suspende el despliegue afectado hasta una nueva decisión, sin actualizar silenciosamente la versión autorizada ni eliminar historia.

## Operaciones cerradas

| Acción | Función permitida | Efectos y límites |
|---|---|---|
| `inspect` | Consultar identidad, preparación, direcciones y versión mediante comandos fijos. | No cambia usuarios, claves, paquetes, recursos o datos. |
| `bootstrap` | Ejecutar la receta exacta del producto con parámetros y secretos de esa instancia. | Inicialización única e idempotente. No actualiza una instancia existente a otra definición ni acepta scripts del cliente. |
| `verify` | Ejecutar probes enumerados para esa definición. | No borra ni recrea datos. El smoke test de escritura usa una transacción revertida y espacio temporal propio. |

No hay acciones para shell, instalación de paquetes arbitrarios, cambio de CPU/RAM/disco, gestión de otras cátedras, borrado de contenedores, modificación de red/host ni respaldo programado de aplicaciones. La creación/arranque/parada y las tareas UPID continúan en el adaptador de Proxmox, con su control de capacidad y vigencia.

## Definiciones y parámetros permitidos

El [esquema de definición](service-definition.schema.json) fija las tres ofertas de esta entrega. Sus paquetes exactos, imágenes, commits y digests se completan con el resultado real del build y deben verificarse al publicar; los ejemplos de este contrato no acreditan que esos artefactos existan. Un borrador puede estar incompleto: este esquema estricto se exige al validar/publicar, no para guardar el borrador. El manifiesto queda inmutable desde la validación.

| Producto | Preparación fija | Parámetros de instancia |
|---|---|---|
| Linux, IaaS | Ubuntu 24.04; `linux-v1`. Cuenta guest `napadmin` con contraseña propia y sudo local, accesible desde la consola Proxmox autorizada y delimitada. Root bloqueado, sin autologin. | `display_name`: texto de presentación de 1–100 caracteres. |
| PostgreSQL, PaaS | Ubuntu 24.04 y PostgreSQL 16 con versión patch fijada; `postgresql-v1`. | `display_name`; `database_name` opcional: identificador `[a-z][a-z0-9_]{0,62}`, nunca `postgres`, `template0` o `template1`. Si falta, se deriva del UUID de instancia. |
| BookStack, SaaS | Ubuntu 24.04, BookStack 26.09.1, PHP 8.3 y MariaDB 10.11 con versiones exactas fijadas; `bookstack-v1`. | `display_name`; `teacher_name`: 1–100 caracteres; `teacher_email`: correo válido, máximo 254 caracteres; `locale`: `es` o `en`. El docente se obtiene del pedido autorizado, sin alta de alumnos en NAP. |

Los textos se serializan como datos, nunca se interpolan en shell, PHP o SQL ejecutable. Parámetros, recetas y perfiles no pueden cambiar VMID, nonce, producto, privilegios o recursos aprobados. La ausencia o exceso de recursos mínimos falla antes de iniciar la preparación.

## Secretos, imagen y bootstrap

Antes de crear la imagen se eliminan datos de cátedras, bases inicializadas, usuarios de aplicación utilizables, `.env` definitivo, `APP_KEY`, sesiones, claves SSH, contraseñas y logs. Se regenera la identidad del sistema cuando corresponda. Root no conserva contraseña conocida. Los servicios no quedan expuestos con cuentas predeterminadas mientras esperan bootstrap. El manifiesto conserva evidencia de saneamiento y digest del artefacto, no una declaración manual sin prueba.

El worker genera una sola vez los secretos de cada instancia y los guarda cifrados antes del envío. Reintentar recupera los mismos valores. `bootstrap` transporta por stdin los valores permitidos: Linux recibe `guest_password`; PostgreSQL recibe `database_password`; BookStack recibe `teacher_password`, `database_password` y `app_key`. En BookStack, `app_key` tiene formato válido para la versión fijada y entropía criptográfica de 256 bits; no se reutiliza entre instancias.

El runner usa archivos privados temporales y una ruta interna fija para transferir la configuración. No incluye secretos en SSH argv, parámetros Proxmox, logs ni respuesta. El invitado conserva únicamente lo necesario, con permisos mínimos. Se elimina el material temporal del host y del invitado al terminar; la eliminación no sustituye el cifrado del respaldo de configuración persistente.

Bootstrap Linux crea `napadmin` dentro del invitado y configura `guest_password` única, entregada a la cátedra mediante el endpoint de revelado autorizado. `napadmin` puede administrar su contenedor mediante sudo local; no concede permisos sobre el nodo, Proxmox o NAP. Root permanece bloqueado y no se configura autologin. La identidad institucional para abrir la consola Proxmox es distinta de esta cuenta guest: abrir la consola no sustituye el login Linux. Su comprobación local incluye existencia de la cuenta y configuración de login/sudo; la aceptación exige iniciar sesión realmente por la consola delimitada.

Bootstrap PostgreSQL crea un clúster de datos nuevo y una base/rol de cátedra separados de la base interna de NAP. El rol entregado puede administrar sus datos, sin superusuario, creación de roles, replicación ni acceso a otras instancias. Se limita `pg_hba.conf` a redes autorizadas con TLS y SCRAM; no se añade `trust` remoto.

Bootstrap BookStack crea MariaDB local y usuario limitado a su base, configura `APP_URL` real, `.env`, `APP_KEY` nueva, HTTPS y permisos de archivos. Sustituye o elimina la cuenta inicial conocida antes de exponer la aplicación. El docente recibe administración **de su instancia BookStack** para publicar y gestionar lectores, sin rol administrativo de NAP o Proxmox. Las cuentas de alumnos son individuales, con el rol de solo lectura de BookStack y sin roles adicionales que sumen edición o administración. Registro abierto y lectura pública permanecen desactivados. `STORAGE_TYPE=local_secure` evita servir imágenes de contenido sin autenticación; se prueban también adjuntos.

## Idempotencia, fallos y pruebas

El runner persiste deduplicación por `(cluster_uuid, resource_uuid, nonce, operation_id, action)` y digest del contenido de solicitud mediante una huella autenticada que no permita inferir secretos. Misma clave y mismo contenido devuelve el resultado registrado o retoma una fase confirmada. Misma clave y contenido distinto produce `IDEMPOTENCY_CONFLICT`. Un nuevo `operation_id` tampoco puede saltar la marca de bootstrap completo de la instancia ni cambiar sus secretos/definición; una rotación futura requiere un contrato específico.

Un timeout no acredita que el comando haya terminado o revertido. Primero se consulta/reconcilia el intento en curso; no se ejecuta otro bootstrap concurrente. El runner limita a una personalización por recurso, conserva fases recuperables y verifica identidad nuevamente antes de afirmar éxito. No recrea bases ni regenera `APP_KEY` para arreglar un reintento. Si no se puede determinar el resultado, responde `unconfirmed` y el portal conserva reserva, operación e incertidumbre hasta confirmar recurso o limpieza.

La comprobación periódica PostgreSQL usa conexión autenticada y `SELECT`; `pg_isready` solo no prueba acceso. La preparación verifica escritura/lectura en transacción revertida. BookStack verifica `/status` y disponibilidad del login, pero eso no demuestra permisos o aceptación pedagógica. La aceptación funcional usa docente y lectores reales desde la red prevista. La ausencia de probe o una falla del canal de observación se informa como no confirmado.

En esta entrega no se promete un probe remoto automático en la red alumno. Después de crear, personalizar y comprobar localmente, la operación de infraestructura termina `confirmada`; el servicio sigue con disponibilidad `no_verificada` y el pedido en `EN_DESPLIEGUE`. No se mantiene una operación abierta esperando intervención humana. Un operador prueba **cada instancia** desde la red prevista y un administrador importa primero el documento tipado por `POST /evidencias` según [evidence.md](evidence.md) y confirma con el UUID devuelto mediante `POST /servicios/{id}/verificar-acceso`, sobre el endpoint real ya vinculado a esa instancia, sin URLs o comandos arbitrarios. La evidencia incluye identidad de servicio, red de origen, fecha, actor y resultado, sin secretos: acceso/login Linux por consola y sudo local; conexión y escritura/lectura PostgreSQL; login/publicación/lectura y permisos BookStack según corresponda. Solo una verificación satisfactoria habilita `utilizable` y `ACTIVO`; una falla conserva el recurso y su capacidad contabilizada para corregir y reintentar. La evidencia de publicación de una definición y su flag de red no sustituyen esta verificación individual.

Pruebas del contrato: rechazo de campos/comandos/rutas/secretos extra, hostkey incorrecta, recurso ajeno, identidad cambiada durante ejecución, digest diferente, parámetros inválidos y clave idempotente con contenido distinto; reanudación tras corte de transporte; secretos ausentes de logs y respuestas; imagen sin credenciales predeterminadas; dos instancias de cada aplicación con datos/secretos distintos y persistencia tras reinicio. En cada BookStack, el docente crea dos lectores, se rechaza edición/administración/acceso cruzado y revocar uno bloquea su siguiente acceso sin afectar al otro. La validación JSON Schema usa Draft 2020-12 con verificación de formatos; además verifica coherencia semántica de inventario, componentes/paquetes, mínimos y evidencia. Una cadena de digest bien formada no demuestra por sí misma integridad o validación real.

## Respaldo y referencias

El runner de esta entrega no programa ni gestiona respaldos de aplicaciones. Infraestructura ejecuta el procedimiento externo, copia a un destino separado y prueba PostgreSQL y BookStack restaurados. En BookStack se conserva `APP_KEY` del respaldo, base, `.env`, imágenes, adjuntos y temas; restaurar no equivale a un bootstrap nuevo. Una copia del portal no sustituye estos datos.

Fuentes primarias para la implementación: [Proxmox Container Toolkit](https://github.com/proxmox/pve-docs/blob/master/pct.adoc), [BookStack: instalación](https://www.bookstackapp.com/docs/admin/installation/), [roles](https://www.bookstackapp.com/docs/user/roles-and-permissions/), [archivos seguros](https://www.bookstackapp.com/docs/admin/upload-config/), [respaldo/restauración](https://www.bookstackapp.com/docs/admin/backup-restore/), [PostgreSQL: SCRAM](https://www.postgresql.org/docs/16/auth-password.html) y [pg_isready](https://www.postgresql.org/docs/16/app-pg-isready.html). Las capacidades y comandos se contrastan además con la versión instalada del clúster; no se asume compatibilidad por consultar documentación de otra versión.
