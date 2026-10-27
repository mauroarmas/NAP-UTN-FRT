# US2 — acceso, MFA optativo y recuperación

Validación local del 20/10/2026. No se modificaron cuentas, factores ni SMTP institucionales.

La suite de aceptación de autenticación, CLI y bienvenida utiliza solicitudes HTTP reales sobre ASGI y bases efímeras: incluye cookie, Origin/CSRF, ingreso sin MFA, onboarding obligatorio, conservación exacta de contraseña, setup cancelado/vencido, antirreplay TOTP, recuperación restringida, códigos de un uso, desactivación deliberada y cierre de sesiones. El ensayo del único administrador emite y consume autorización asistida desde el código CLI, cambia el factor por HTTP y conserva una sola cuenta administrativa. La salida redirigida del CLI se rechaza; el ingreso interactivo institucional queda sujeto al procedimiento documentado.

Resultados:

- 30 pruebas backend de aceptación aprobadas (auth_contrato_009, cli_identidad, outbox_bienvenida, login_flujo, primer_login y alta_usuario_password).
- 8 pruebas PostgreSQL aprobadas: consumo simultáneo de código, regeneración/desactivación con un mismo paso TOTP, ventana móvil entre cuartos de hora, transferencias y administración pendiente, instalación y actualización del esquema, cifrado de factor legado confirmado sin desactivar factores inconsistentes. Otras 4 pruebas de autenticación concurrente incluyen diez fallos simultáneos: solo cinco se registran antes del bloqueo común.
- 12 pruebas Vitest aprobadas: restauración desde servidor con datos locales dañados, etapas sin portal montado, inscripción opcional cancelada, presentación de códigos y cierre confirmado, además de permisos/consola y login rechazado.
- 3 escenarios Chromium aprobados con API simulada y red externa bloqueada: ingreso sin sesión, recarga en onboarding y operación sin MFA con cierre de sesión. No se presentan como prueba de cookies de producción ni de SMTP real.
- Regresión completa inicial: 398 aprobadas, 9 fallidas y 12 PostgreSQL omitidas explícitamente. Se corrigieron ocho expectativas anteriores de rol/perfil/consola y una configuración CSRF del fixture; los 48 casos afectados pasaron después. Permanece la expectativa antigua del tope de disco, anterior a la feature y prevista en T134. Las comprobaciones PostgreSQL se ejecutan por separado y no se sustituyen por SQLite.

Las sesiones tienen cuatro propósitos y plazos absolutos. El backend comprueba sid, versión, usuario y permisos actuales; todas las mutaciones autenticadas comprueban Origin y CSRF. Los JWT anteriores no acreditan acceso. Claves independientes para firma, CSRF y cifrado; secretos TOTP con contexto por cuenta/desafío. Códigos de 128 bits solo como hash y autorización asistida de 256 bits con cinco minutos/un uso. Bcrypt se comprueba fuera del event loop, con concurrencia acotada y límite explícito de 72 bytes sin truncar ni recortar espacios.

La bienvenida se confirma transaccionalmente con el alta; SMTP ocurre fuera de la transacción mediante lease y resultado condicional. El secreto temporal separado/cifrado se borra al enviar o invalidar; no se registran cuerpos ni errores SMTP crudos. La prueba de fallo y reintento conserva Message-ID. No se promete entrega exactamente una vez.

Startup no ejecuta Alembic ni crea cuentas. Bootstrap explícito, TTY y ausencia de credenciales predeterminadas; seed_dev solo prepara una cátedra en development. El frontend usa misma origin, cookie y perfil del servidor; descarta token/user heredados sin interpretarlos. Los códigos se guardan solo en memoria para su presentación única.

Pendiente para habilitación operativa: configuración institucional de claves/origins/proxy/TLS, respaldo del keyring, despliegue y ensayo de entrega SMTP. El worker que procesa periódicamente la outbox se integra en T063; estas pruebas invocan su procesador explícitamente. No ejecutar este corte intermedio en operación sin completar migración/preflight y fases restantes.
