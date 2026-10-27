# Contrato de autenticación, habilitación y recuperación

**Estado**: implementado y verificado en código (`009-remediar-hallazgos-cierre`).

**Alcance**: FR-001–FR-009, FR-051–FR-052 y FR-069–FR-071; US1, US2 y SC-001, SC-002, SC-012, SC-015 de [spec.md](../spec.md). Se aplica la constitución 4.0.0: el segundo factor es voluntario para ambos roles y se exige al ingresar únicamente cuando está activo. Las cuentas de alumnos de BookStack pertenecen a la aplicación desplegada; no participan de este contrato ni se crean en NAP.

Todas las rutas HTTP se ubican bajo `/api/v1`. Los nombres de endpoints son propuestas para implementación. Los contratos de features anteriores conservan valor histórico; este documento reemplaza, para 009, el flujo de login y cambio inicial que concedía un bearer operativo antes de completar las comprobaciones.

## Transporte y controles comunes

- El navegador recibe el JWT exclusivamente mediante la cookie de sesión. No se devuelve `access_token` en JSON ni se guarda en `localStorage`, `sessionStorage`, parámetros URL o estado persistido del frontend. El perfil local tampoco acredita permisos.
- En operación HTTPS, la cookie se llama `__Host-nap_session`, con `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, sin `Domain` y con vencimiento no posterior al de la sesión. En desarrollo HTTP se admite `nap_session` sin `Secure` únicamente con `APP_ENV=development`; esa excepción no se habilita en operación.
- El JWT lleva `sid`, `sub` estable correspondiente al ID de usuario, `iat`, `exp` y `auth_version`. No lleva permisos ni secretos. Se verifica firma con algoritmo permitido explícito, vencimiento y correspondencia con una fila vigente de `sesiones_autenticacion` y con la versión actual del usuario. Un JWT anterior sin estos atributos se rechaza.
- `sesiones_autenticacion.proposito` es la autoridad sobre la etapa de acceso. Cada petición vuelve a comprobar usuario activo, versión, etapa, rol actual y pertenencia actual cuando corresponde. La firma de un JWT no concede permiso sobre un recurso.
- Frontend y API se publican en una misma origin mediante reverse proxy; Vite utiliza proxy durante desarrollo. No se acepta CORS con origin comodín y credenciales. La allowlist de origins se configura explícitamente para el entorno.
- `POST /auth/login` exige `Origin` permitido y `X-NAP-Request: 1`. Esta cabecera identifica una petición deliberada del cliente y no es un secreto. No requiere una sesión previa ni token CSRF.
- Todas las demás mutaciones de este contrato exigen cookie vigente, `Origin` permitido y `X-CSRF-Token` válido para ese `sid`, incluidas las que completan desafíos con sesiones restringidas. Origin ausente, `null` o ajeno se rechaza. Los clientes de validación directa deben enviar también estos encabezados.
- `GET /auth/csrf` devuelve un token derivado por HMAC del `sid` vigente mediante una clave de servidor dedicada, independiente de la clave de firma JWT y del keyring de cifrado. No concede autenticación. Cambiar el `sid` invalida el token CSRF anterior; no se añade una cookie legible de autenticación.
- Respuestas de autenticación, perfil, CSRF, inscripción y códigos de recuperación usan `Cache-Control: no-store`. No se registran cuerpos ni cabeceras que contengan contraseñas, OTP, secretos, cookies, códigos de recuperación o autorizaciones asistidas.
- Las sesiones tienen vencimiento absoluto: `operativo` hasta 60 minutos; `onboarding` hasta 15 minutos; `mfa_pending` y `recovery` hasta cinco minutos. Ninguna actividad prolonga esos plazos. Un desafío vence a los cinco minutos o al vencer su sesión, lo que ocurra primero. Las sesiones de recuperación vencidas se revocan al detectarse y por limpieza periódica; la denegación por fecha es inmediata y no depende de que esa limpieza haya corrido.
- Rotar una sesión significa revocar el `sid` anterior y crear otro dentro de la misma transacción; no basta con sobrescribir la cookie. La respuesta confirma `sesion_rotada: true`, y el cliente obtiene el nuevo CSRF antes de otra mutación. Al salir o desactivar 2FA se elimina la cookie con los mismos atributos de alcance.

## Etapas de sesión y permisos

| Propósito | Cómo se obtiene | Acceso permitido |
|---|---|---|
| `mfa_pending` | Contraseña válida de una cuenta con 2FA activo. | Perfil mínimo, CSRF, completar el desafío TOTP, iniciar recuperación por código/asistida, solicitar desactivación deliberada con las pruebas exigidas y cerrar sesión. |
| `onboarding` | Contraseña válida sin 2FA activo, o TOTP de ingreso confirmado, cuando falta cambiar la contraseña provisoria. | Perfil mínimo, CSRF, cambiar la contraseña inicial y cerrar sesión. |
| `recovery` | Contraseña válida más código de recuperación consumido o autorización asistida consumida. | Perfil mínimo, CSRF, configurar/confirmar exclusivamente un factor nuevo y cerrar sesión. |
| `operativo` | Todos los pasos exigibles completados: cambio inicial resuelto y TOTP verificado si está activo. | Operaciones autorizadas por rol y cátedras actuales, además de seguridad de la propia cuenta. |

Una sesión restringida no puede consultar listados, pedidos, servicios, accesos, métricas ni recursos administrativos. Los endpoints de dominio responden `403 habilitacion_pendiente`, aunque se invoquen directamente. La recuperación no permite desactivar el factor, generar una sesión operativa por contraseña sola ni usar la contraseña inicial como excepción.

## Respuestas comunes

La respuesta de login o de una transición de habilitación lleva:

```json
{
  "estado": "mfa_pending",
  "expira_at": "2026-10-18T15:05:00Z",
  "sesion_rotada": true,
  "acciones_permitidas": ["verificar_totp", "recuperar_2fa", "desactivar_2fa", "cerrar_sesion"],
  "desafio": {
    "id": "identificador-opaco",
    "expira_at": "2026-10-18T15:05:00Z"
  }
}
```

`estado` coincide con el propósito de la nueva sesión. `desafio` se incluye únicamente si existe uno necesario para continuar; su identificador no funciona como credencial fuera de la sesión que lo originó. Las acciones son una ayuda de interfaz; el backend vuelve a verificar cada permiso. Todas las fechas de este contrato se expresan en UTC con zona explícita.

Los errores usan la forma `{"detail":{"codigo":"...","mensaje":"...","reintentable":false}}`, con `campos` y `operation_id` opcionales cuando corresponda al contrato general. `reintentable` es verdadero para una espera temporal o un paso que puede reiniciarse con pruebas vigentes; no autoriza repetir una mutación sin recuperar antes la etapa correcta. Los detalles adicionales documentados no incluyen datos de otras cuentas ni contenido del recurso denegado.

## Endpoints de ingreso y habilitación

| Método y ruta | Entrada | Respuesta y efectos |
|---|---|---|
| `POST /auth/login` | Formulario `username`, `password`; username admite nombre de usuario o email como actualmente. Origin y cabecera exigidos arriba. | `200`: contraseña válida crea una sesión nueva. Con 2FA activo: `mfa_pending` y desafío de ingreso de cinco minutos. Sin 2FA y cambio inicial pendiente: `onboarding`. Sin pendientes: `operativo`. Revoca la sesión anterior presentada, si existe. No devuelve perfil completo ni JWT en el cuerpo. |
| `GET /auth/csrf` | Cookie de cualquier propósito vigente. | `200 {"csrf_token":"...","expira_at":"..."}`. `401` si no hay sesión válida; no crea una sesión anónima. |
| `GET /auth/me` | Cookie vigente. | `200`: `estado`, `expira_at`, `acciones_permitidas` y `usuario`. En etapas restringidas, `usuario` contiene solo `id`, `username`, `nombre`, `debe_cambiar_password` y `totp_habilitado`; incluye desafío pendiente necesario sin exponer su secreto. En `operativo`, agrega el perfil y las cátedras actuales de `UsuarioResponse`. No devuelve códigos ni configuración de infraestructura. |
| `POST /auth/2fa/challenge/verify` | Sesión `mfa_pending`; JSON `desafio_id`, `codigo_totp`. | `200`: verifica y consume el desafío del ingreso, registra el paso TOTP y rota a `onboarding` si falta cambio inicial, o a `operativo`. Si falta emitir el juego por migración o restauración, agrega `codigos_recuperacion` nuevos una sola vez. No sirve un desafío de otra sesión, otro usuario o distinto propósito. |
| `POST /auth/cambiar-password-inicial` | Sesión `onboarding`; JSON `nueva_password`. | `200`: valida y establece contraseña definitiva, desmarca el pendiente, incrementa versión y revoca sesiones/desafíos previos; emite sesión `operativo` nueva porque la sesión de onboarding ya acredita los pasos anteriores. Devuelve transición y perfil actualizado. Ningún endpoint administrativo puede simular esta comprobación cambiando un campo del cliente. |
| `POST /auth/logout` | Sesión de cualquiera de los cuatro propósitos; CSRF y Origin. | `204`: revoca ese `sid` y sus desafíos pendientes, elimina cookie. No altera elección de 2FA ni credenciales. Un token robado de la sesión cerrada deja de ser válido. |

El cliente llama `/auth/me` al iniciar y tras recargar, obtiene CSRF si debe mutar y muestra la pantalla correspondiente a `estado`. Un `403 habilitacion_pendiente` redirige a completar ese paso; no se presenta como una sesión expirada ni como un listado vacío. Los errores de TOTP permanecen en el desafío mientras sea válido.

## Inscripción, reemplazo y códigos de recuperación

| Método y ruta | Permiso y pruebas | Respuesta y efectos |
|---|---|---|
| `POST /auth/2fa/setup` | `operativo` sin 2FA activo y JSON `password`; o `recovery`, cuya identidad ya fue comprobada. | `200`: crea inscripción pendiente de cinco minutos, ligada a esa sesión. Devuelve `desafio_id`, `secret`, `provisioning_uri`, `expira_at`; solo para presentar al titular. En inscripción voluntaria, el factor sigue desactivado. En recuperación, mantiene el factor anterior activo y no habilita operación. |
| `POST /auth/2fa/verify` | Misma sesión que inició setup; JSON `desafio_id`, `codigo_totp` del factor pendiente. | `200`: consume desafío y activa/sustituye el factor únicamente después de verificarlo; invalida generación anterior, crea diez códigos, incrementa versión, revoca sesiones/desafíos anteriores y rota a `operativo` o a `onboarding` si todavía debe cambiar contraseña. Devuelve transición y `codigos_recuperacion` una sola vez. |
| `POST /auth/2fa/replacement/setup` | `operativo` con 2FA activo; JSON `password`, `codigo_totp` vigente. | `200`: exige comprobación nueva del factor; crea desafío de reemplazo ligado a la sesión y entrega secreto pendiente. No sobrescribe ni desactiva el secreto vigente. |
| `POST /auth/2fa/replacement/verify` | Sesión que inició reemplazo; JSON `desafio_id`, `codigo_totp` del secreto pendiente. | `200`: confirma reemplazo, invalida generación anterior, entrega diez códigos una sola vez, revoca sesiones/desafíos e incrementa versión; emite sesión nueva. |
| `POST /auth/2fa/recovery-codes/regenerate` | `operativo` con 2FA activo; JSON `password`, `codigo_totp` vigente. | `200`: invalida todos los códigos anteriores y entrega diez nuevos una sola vez. Incrementa `auth_version`, revoca todas las sesiones/desafíos anteriores y crea sesión nueva tras la reautenticación. No modifica el secreto TOTP. |
| `DELETE /auth/2fa/setup` | Sesión que inició una inscripción o reemplazo; JSON `desafio_id`. | `204`: elimina el pendiente propio sin modificar el factor vigente ni la elección previa. Si la sesión es `recovery`, continúa restringida hasta reconfigurar o salir. |

Los códigos individuales son aleatorios con al menos 128 bits de entropía; los separadores de presentación no reducen esa entropía. Se almacenan únicamente como hash/HMAC, identificados por usuario y generación. El juego completo se entrega solo en la respuesta de generación y la UI permite guardarlo fuera del portal. No existe un endpoint que vuelva a mostrarlo. Si esa respuesta se pierde después del commit, no se reconstruye el juego: el titular puede regenerarlo tras comprobar su factor nuevo.

El secreto activo y el pendiente usan cifrado autenticado Fernet con keyring externo a la BD; `cryptography` pasa a ser dependencia directa. La clave de cifrado no se reutiliza como clave JWT o CSRF. La rotación del keyring conserva lectura de secretos existentes mientras se recifran y documenta respaldo separado de claves. No se convierte el secreto TOTP en hash, pues debe recuperarse para verificarlo.

Cada comprobación TOTP aceptada registra atómicamente el paso temporal utilizado. Un paso ya usado no se acepta de nuevo, aunque se presente en otro desafío o acción; el control es de cuenta/factor, no solo de endpoint. La ventana de tolerancia se limita al paso actual y un paso adyacente por deriva, con reloj del servidor sincronizado; el contador registrado evita reutilizar cualquiera de los pasos aceptados. El primer paso del factor nuevo se registra al confirmar, y no se reutiliza inmediatamente para otra acción sensible.

## Recuperación y desactivación voluntaria

| Método y ruta | Permiso y pruebas | Respuesta y efectos |
|---|---|---|
| `POST /auth/2fa/recovery` | `mfa_pending`; JSON `password`, `codigo_recuperacion`. | `200`: comprueba contraseña y consume exactamente un código vigente en una operación indivisible; incrementa versión, revoca sesiones/desafíos anteriores y emite `recovery` de cinco minutos. Invalida el desafío de ingreso pendiente. No entrega acceso operativo ni desactiva el factor. |
| `POST /auth/2fa/assisted-recovery` | `mfa_pending`; JSON `password`, `autorizacion_recuperacion` emitida por CLI. | `200`: consume autorización válida de la misma cuenta una sola vez; incrementa versión, invalida todos los códigos de recuperación anteriores y revoca sesiones/desafíos previos; emite `recovery`. No sustituye la contraseña ni habilita administración antes de confirmar factor nuevo. |
| `POST /auth/2fa/disable` | `operativo` o `mfa_pending`; JSON `password` y exactamente uno de `codigo_totp` o `codigo_recuperacion`. No se admite desde `recovery`. | `200 {"estado":"sesion_finalizada","totp_habilitado":false}`: comprueba contraseña y factor/código, consume la prueba, registra decisión deliberada, elimina secretos pendientes y activo, invalida códigos, incrementa versión, revoca todas las sesiones/desafíos y borra cookie. El siguiente ingreso usa contraseña y respeta el cambio inicial pendiente. |

En recuperación por código se consume el presentado; los otros códigos siguen disponibles hasta completar el reemplazo. Así, una sesión de recuperación vencida puede reiniciarse con otro código sin perder el factor activo ni forzar asistencia por una interrupción. Confirmar el factor nuevo invalida todo el juego anterior y genera otro. La misma cuenta se bloquea durante consumo/regeneración/desactivación para que ninguna carrera permita usar un código invalidado o consumirlo dos veces. Una autorización asistida se guarda como hash y solo se asocia a una sesión al consumirse; ningún endpoint la acepta como bearer operativo.

Si el titular todavía posee el factor anterior, puede volver a ingresar con él cuando una recuperación no se completó. Si perdió factor y todos los códigos/autorizaciones disponibles, debe repetir verificación asistida; no existe una puerta de entrada permanente por contraseña sola mientras 2FA siga activo.

## Errores, validación y límites

| HTTP / código | Condición y tratamiento |
|---|---|
| `401 credenciales_invalidas` | Contraseña errónea, cuenta inexistente o inactiva en login. Mismo mensaje y forma de respuesta; comprobar hash ficticio cuando no existe usuario para reducir diferencias temporales. No se informa si un email está registrado. |
| `401 sesion_invalida` | Cookie ausente, JWT incorrecto/vencido, `sid` revocado/inexistente, versión anterior o usuario inactivo. El cliente elimina estado local y pide ingreso. |
| `403 origen_no_permitido` | Origin ausente, `null` o fuera de allowlist, o login sin cabecera requerida. No inicia ni modifica sesión. |
| `403 csrf_invalido` | CSRF ausente, de otra sesión o anterior a una rotación. No modifica datos. El cliente obtiene CSRF vigente, conservando el formulario. |
| `403 habilitacion_pendiente` | Sesión válida pero etapa incompatible con la operación; agrega `estado` actual y `acciones_permitidas` mínimas. |
| `403 sin_permisos` | Rol o pertenencia actual insuficiente. No devuelve contenido del recurso ni realiza consultas de infraestructura en su nombre. |
| `400 prueba_invalida` | OTP, código de recuperación o autorización asistida incorrectos, utilizados o invalidados. Mensaje genérico; cuenta como fallo y no distingue el motivo interno. |
| `409 desafio_no_disponible` | Desafío de sesión vencido, consumido, reemplazado o de propósito incompatible. El cliente reinicia el paso correspondiente; no conserva un secreto pendiente anterior. Para un identificador ajeno se usa el mismo código sin revelar propietario. |
| `409 estado_2fa_incompatible` | Inscripción voluntaria sobre factor ya activo, reemplazo sin factor o generación de códigos sin 2FA. El cliente vuelve a consultar `/auth/me`. |
| `409 ultimo_administrador` | Una mutación dejaría cero administradores activos; no realiza ningún cambio parcial. |
| `422 datos_invalidos` | Campos faltantes, formatos incorrectos, pruebas mutuamente excluyentes o contraseña nueva fuera de política. No se trunca ni transforma una contraseña para hacerla válida. |
| `429 espera_autenticacion` | Límite de intentos alcanzado; agrega `reintentar_en_segundos` y `Retry-After` sin revelar existencia de cuenta. |

La espera es de quince minutos desde alcanzar cualquiera de estos límites dentro de una **ventana móvil** de quince minutos: cinco fallos por identificador de cuenta normalizado o treinta por origen. Cada evaluación cuenta los fallos de los quince minutos inmediatamente anteriores; no se reinicia el contador por cambiar de cuarto de hora o bucket. Cuatro fallos al final de un cuarto de hora y otro al comenzar el siguiente activan la espera. Las claves se almacenan pseudonimizadas y el registro de fallos/cálculo de bloqueo se serializa por clave estable en `intentos_autenticacion` de PostgreSQL, compartido entre procesos; la unicidad de una fila por bucket fijo no acredita este control. Cambiar de cuenta no elude el límite de origen; cambiar/recrear desafío no reinicia el de cuenta. Las claves por cuenta se calculan tanto para cuentas existentes como inexistentes, unificando username/email cuando identifican la misma cuenta. Las comprobaciones fallidas de contraseña, OTP, recuperación y prueba reforzada alimentan los controles; las peticiones rechazadas por falta de CSRF/Origin no consumen códigos ni cuentan como contraseña incorrecta de un tercero. No hay bloqueo permanente y el éxito de una cuenta no limpia el historial de fallos del origen.

Se usa la dirección remota real; `X-Forwarded-For` solo se acepta desde el reverse proxy declarado confiable, nunca directamente desde el cliente. No se duerme dentro de una petición para implementar la espera. Hashing/verificación bcrypt se ejecutan fuera del event loop mediante concurrencia acotada.

Se conserva compatibilidad con los hashes bcrypt existentes. Las nuevas contraseñas deben tener al menos ocho caracteres y no superar 72 bytes UTF-8; toda entrada de contraseña rechaza más de 72 bytes y el login admite las credenciales existentes sin imponer retroactivamente el mínimo de las nuevas. No se recortan espacios ni se truncan bytes; los formatos se validan antes de hashear. No se migra a otro algoritmo en esta feature. Los OTP se transmiten como cadenas numéricas, preservando ceros iniciales.

## Autorización y conservación de administración

Las rutas de dominio usan una comprobación de sesión operativa; los servicios mutantes aplican nuevamente rol y pertenencia, incluso cuando los invoca otro router o un trabajo interno con identidad de sistema explícita. Reasignar titularidad cambia permisos desde la siguiente petición una vez completado el protocolo de [revocación nativa](console-access.md); mientras está pendiente se deniegan las acciones afectadas en el portal y no se concede acceso al nuevo titular. Las consultas de acceso, último snapshot, históricos y consola aplican la misma comprobación que el detalle del recurso. La interfaz no decide permisos desde el perfil guardado.

Las mutaciones de usuarios continúan en `/usuarios`: crear/modificar personas y roles, desactivar y retirar requieren administrador operativo. El cambio de `admin` activo a otro rol se protege igual que desactivar o retirar. Todos los caminos administrativos y CLI que puedan quitar administración toman el mismo bloqueo `pg_advisory_xact_lock`, vuelven a contar administradores activos dentro de la transacción y rechazan dejar cero. El bloqueo se libera al terminar la transacción; no se usa un bloqueo Python local. Las carreras se validan en PostgreSQL real.

Los cambios de contraseña y factor invalidan sesiones mediante `auth_version` y revocación. Las solicitudes de cambio de rol, actividad o retiro las invalidan al admitir el trámite y bloquean operaciones de dominio de esa cuenta hasta completarlo, incluso tras otro login; si afectan una identidad nativa, se completa primero el protocolo de consola antes de dar por efectivo el cambio. Cambiar titularidades no depende de rotar tokens porque se consulta pertenencia actual y el bloqueo de cambios pendientes. El trámite mantiene la exclusión de cambios administrativos incompatibles y revalida el último administrador al admitir y completar, sin sostener locks durante la intervención externa. Los intentos rechazados no cambian estado de pedidos ni historial exitoso. El endpoint genérico de cambio de estado no puede sustituir las acciones autorizadas que reservan/liberan capacidad; su tratamiento se define en el contrato del ciclo de vida.

## CLI de alta inicial y recuperación asistida

Estas interfaces son propuestas para scripts por implementar. Se ejecutan desde `backend/`, con configuración de operación y acceso autorizado a PostgreSQL/keyring; no son endpoints HTTP ni se ejecutan automáticamente al iniciar el contenedor.

```bash
python -m scripts.bootstrap_admin
python -m scripts.recuperar_2fa --usuario identificador --actor operador_institucional --motivo "Pérdida de teléfono y códigos" --referencia ACTA-2026-001
```

### `scripts.bootstrap_admin`

- Interactivo sobre TTY: solicita usuario, nombre, email y contraseña con confirmación oculta. Aplica validaciones ordinarias y no tiene usuario, contraseña o factor predeterminados.
- Solo crea la primera cuenta cuando no existe ningún administrador; si hay uno activo o inactivo, termina sin modificar cuentas y explica que corresponde al procedimiento de recuperación. No restablece contraseñas por reinicio ni crea un administrador auxiliar.
- Toma el bloqueo de administración para impedir altas iniciales simultáneas. Crea administrador activo, 2FA desactivado y `debe_cambiar_password=true`; el primer ingreso queda limitado a onboarding. Activar 2FA sigue siendo una decisión voluntaria posterior.
- Registra alta con actor de operación identificable; no imprime contraseña, URI TOTP ni JWT. En entornos de operación no se ejecutan `seed_admin.py`/`seed_dev.py` como parte de startup.

### `scripts.recuperar_2fa`

- El responsable de infraestructura verifica la identidad del titular por el canal institucional documentado fuera del portal. Acceso a shell o conocimiento del nombre de cuenta no reemplaza esa verificación. `--actor`, `--motivo` y `--referencia` son obligatorios y dejan evidencia; la referencia apunta al registro de comprobación y no incorpora copias de documentos personales en logs.
- Solo actúa sobre una cuenta activa con 2FA habilitado. No crea cuentas, cambia rol, altera contraseña ni desactiva el factor. Es válido para el único administrador porque la autoridad de operación es externa al login bloqueado.
- Crea autorización aleatoria de al menos 256 bits con vencimiento de cinco minutos; guarda hash, usuario, actor/motivo/referencia y estado disponible/consumido/revocado en `desafios_autenticacion`. Esta autorización de origen CLI aún no tiene sesión; se vincula al `sid` que la consume por HTTP. Emitir otra para esa cuenta invalida las autorizaciones asistidas anteriores.
- Muestra la autorización completa una sola vez únicamente en stdout conectado a TTY; rechaza salida redirigida y no la agrega a logs ni argumentos de comandos. La entrega al titular usa el canal acordado en la verificación. No se envía automáticamente por email.
- La emisión no concede acceso; el titular debe presentar contraseña válida para obtener `mfa_pending`, obtener CSRF y consumir autorización en `/auth/2fa/assisted-recovery`. Esa aceptación revoca sesiones/desafíos anteriores y solo permite configurar un factor nuevo. El cambio queda auditado tanto al emitir como al consumir y confirmar.
- Si vence o se pierde la autorización antes de usarla, no se recupera ni amplía: se repite la emisión autorizada. Pérdida simultánea de contraseña no se resuelve modificándola como efecto colateral de este comando.

Ambos comandos terminan con código `0` si completaron la operación, `2` ante validación/estado incompatible y `1` ante fallo de configuración o persistencia; no declaran éxito antes del commit. Las herramientas no aceptan credenciales del titular mediante argumentos visibles en la lista de procesos.

## Persistencia, migración y pruebas de contrato

- `usuarios` conserva 2FA activo y passwords actuales; agrega `auth_version`, secreto cifrado, último paso TOTP y generación de códigos. `sesiones_autenticacion`, `desafios_autenticacion`, `codigos_recuperacion`, `intentos_autenticacion` y `eventos_seguridad` siguen las relaciones/índices de [data-model.md](../data-model.md).
- Los desafíos HTTP pertenecen a usuario y sesión. Su consumo, vencimiento, generación de códigos y revocación usan actualizaciones condicionales/bloqueos y transacciones. La autorización CLI sin sesión solo puede vincularse una vez a una sesión de ingreso de su misma cuenta.
- Una migración/preflight controlado cifra secretos activos con el keyring suministrado y detecta cuentas activas con 2FA incoherente. No las transforma silenciosamente en cuentas sin segundo factor; corresponde recuperación asistida. Secretos pendientes no confirmados no se convierten en factor activo.
- Las cuentas con 2FA preexistente y sin códigos reciben su primer juego después de acreditar contraseña y TOTP, mostrado una vez como parte del ingreso; nunca se envían códigos por una migración o correo. Se conserva la comprobación de cambio inicial.
- Restaurar una copia exige, antes de habilitar acceso, revocar todas las sesiones y desafíos restaurados, incluidas autorizaciones asistidas, e invalidar todos los códigos de recuperación del corte. Se incrementan `auth_version` y generación para que una revocación o consumo posterior al respaldo no se revierta en credenciales reutilizables. El factor TOTP activo se conserva; el siguiente ingreso que acredite contraseña y TOTP entrega un juego nuevo una sola vez. Si el titular perdió ese factor, utiliza recuperación asistida y obtiene códigos nuevos al confirmar el reemplazo. No se desactiva 2FA ni se admite contraseña sola para sustituir los códigos invalidados. Una actualización ordinaria no requiere este tratamiento de restauración ni invalida por sí sola los códigos válidos existentes.
- Todo JWT anterior al contrato se invalida, y el frontend elimina las claves locales `token`/`user` heredadas sin utilizarlas para autorizar. La actualización requiere nuevo ingreso; no reinicia cuentas ni instala datos demo.
- La auditoría distingue activación, cancelación, reemplazo, regeneración, recuperación, desactivación, cambios administrativos y bloqueos, con actor/resultado/motivo aplicables. No inventa un evento exitoso para un intento denegado ni registra las pruebas secretas.

La aceptación debe cubrir los cuatro propósitos, reload, cierre y rotación de sesión, cookies y CSRF, códigos/TOTP/desafíos vencidos o reutilizados, dos usos simultáneos del mismo código, regeneración simultánea, permiso retirado con sesión anterior y dos administradores intentando degradarse a la vez. Debe comprobar también el límite móvil al cruzar un cuarto de hora; que una restauración no revive sesiones/desafíos/códigos revocados o consumidos después del corte; que sin activar 2FA es posible operar tras cambiar la contraseña inicial; y que el único administrador recupera su factor mediante el procedimiento definido sin credenciales de demostración.

## Fuentes de las decisiones

- [OWASP: MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): reautenticación al cambiar factor, códigos de un uso y asistencia con comprobación rigurosa de identidad; su recomendación de obligatoriedad no sustituye la decisión funcional de este proyecto.
- [OWASP: sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) y [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): cookies protegidas, revocación y comprobación de mutaciones.
- [PyOTP](https://pyauth.github.io/pyotp/): antirreplay y limitación de intentos adicionales a verificar un OTP.
- [PostgreSQL 16: bloqueos](https://www.postgresql.org/docs/16/explicit-locking.html): exclusión compartida entre procesos hasta finalizar la transacción.
- [Cryptography: Fernet](https://cryptography.io/en/latest/fernet/): cifrado autenticado y keyring para rotación.
- [OWASP: contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): límite de bcrypt y conservación de hashes compatibles.
