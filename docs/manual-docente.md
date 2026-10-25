# Manual docente del portal NAP

Revisión: 25 de octubre de 2026. Roles del portal: administración y responsable de cátedra. Los alumnos utilizan las aplicaciones de su cátedra; no necesitan cuentas NAP. BookStack es una referencia provisional de libro virtual, pendiente de la entrevista con el cliente.

## Ingresar

Usá la dirección HTTPS que entregue la universidad. En esta PC, el entorno de desarrollo se abre en `http://localhost:5174`; esa dirección local no sirve como dirección institucional desde otra computadora.

1. Ingresá usuario o correo y contraseña en la pantalla de ingreso.
2. Si la contraseña es provisional, completá el cambio obligatorio. El formulario solicita la contraseña nueva y su confirmación; no se puede navegar al resto del portal hasta terminar.
3. Si ya activaste el segundo factor, aparecerá otro paso para el código de tu aplicación autenticadora. Una cuenta sin 2FA puede operar con su contraseña definitiva.
4. Para salir, usá **Cerrar sesión**. La sesión queda revocada en el servidor, no sólo oculta en el navegador.

Cinco fallos de autenticación dentro de quince minutos producen una espera temporal de quince minutos. También hay un límite por origen. El mensaje no confirma si una cuenta existe.

## Solicitar y seguir un servicio

Desde el panel o **Catálogo** (`/catalogo`), abrí una solicitud. También podés iniciarla desde **Pedidos** (`/pedidos`). No existe un asistente separado en `/solicitar`.

1. Elegí el tipo de servicio y una opción del catálogo. En Plataforma y Software también podés elegir **Otro** e indicar qué servicio necesitás.
2. Elegí una de tus cátedras. Si sólo tenés una, puede aparecer seleccionada.
3. Completá el nombre de la solicitud y la **justificación pedagógica**: actividades, cantidad estimada de estudiantes y necesidades del servicio.
4. Elegí primer cuatrimestre, segundo cuatrimestre o anual y un año lectivo **desde 2026**. Las fechas provienen del calendario que configura administración. Si faltan, solicitá su configuración o elegí un rango personalizado válido, con fechas desde el 01/01/2026.
5. Comprobá las fechas y pulsá **Enviar solicitud**. No necesitás indicar nodo, VMID, hostname ni parámetros de Proxmox.

Si elegís **Otro**, el pedido queda pendiente para que administración evalúe la necesidad, prepare el servicio y lo incorpore al catálogo. Después puede seleccionar esa oferta al aprobar tu pedido. Describir una aplicación no la instala automáticamente. Para Infraestructura se requiere una plantilla publicada.

Consultá el detalle y el historial desde **Pedidos**. Los estados son `solicitado`, `requiere_ajuste`, `aprobado`, `en_despliegue`, `activo`, `suspendido`, `error`, `rechazado` y `cancelado`. Una renovación aprobada registra condiciones; no afirma que el contenedor esté encendido.

El docente crea y consulta pedidos, solicita renovaciones y opera sus servicios. Si administración pulsa **Pedir aclaración**, el pedido queda como **Aclaración pendiente**: se registra un aviso en el portal y se encola un correo según tus preferencias. Abrí el detalle, pulsá **Responder aclaración**, completá la información y reenviá para revisión. Sólo podés hacerlo sobre pedidos de tus cátedras en ese estado; no elegís hardware ni aprobás la asignación. Administración recibe el aviso de respuesta. Aprobar, rechazar y cancelar continúa siendo administrativo.

## Usar los servicios

En **Servicios** (`/servicios`) aparecen los recursos de tus cátedras, su estado observado, períodos autorizados, operaciones y acciones habilitadas. IaaS es infraestructura Linux, PaaS es PostgreSQL y SaaS es BookStack; todos se ejecutan en LXC. No se ofrecen nuevas máquinas QEMU.

Una orden en curso o de resultado incierto no equivale a éxito. Esperá la confirmación y consultá su diagnóstico antes de repetirla. Si el acceso aún está pendiente de verificación, el contenedor puede estar encendido sin estar entregado como utilizable.

Abrí **Ver acceso** y revelá deliberadamente las credenciales iniciales cuando esté habilitado. No se incluyen en listados ni correos. Si cambiaste una contraseña dentro del servicio, utilizá la nueva: NAP no la sincroniza ni la restablece al reintentar.

| Servicio | Acceso y uso |
|---|---|
| Linux Ubuntu 24.04 | Consola nativa del contenedor propio, con identidad PVE individual limitada a tus pools y comprobación institucional previa. Dentro del invitado se usa `napadmin` con su contraseña y sudo local. No se promete SSH al invitado ni acceso al panel general de Proxmox. |
| PostgreSQL 16 | Cliente PostgreSQL con host, puerto, base, usuario y contraseña entregados. Usar TLS `verify-full` y la CA institucional que indique operación. El rol no administra el servidor ni la base interna de NAP. |
| BookStack | Navegador HTTPS en la dirección entregada. El docente publica libros/páginas y administra lectores individuales dentro de su propia instancia. No usar una cuenta compartida ni habilitar lectura anónima para sustituirlos. |

La consola Linux permanece bloqueada si no están acreditados identidad, aislamiento y revocación de sesiones nativas de la instalación. El portal sólo deriva a la consola del servicio concreto; las demás operaciones se realizan en NAP.

## Vigencia y renovación

Revisá las fechas locales mostradas. Una alta futura reserva desde su aprobación, pero sólo puede desplegarse desde el inicio autorizado. Cambiar después el calendario no cambia las fechas ya aprobadas.

Usá **Renovar** para solicitar otro período del mismo servicio. La renovación conserva datos e identidad. Si hay un intervalo entre períodos, se pausa al terminar el primero y no puede encenderse durante el receso. Desde el nuevo inicio se comprueba capacidad para reactivarlo; si no hay saldo, permanece pausado y permite reintentar. El disco y los datos se conservan.

La inactividad puede programar una pausa tras aviso y gracia. El vencimiento también genera aviso con el plazo efectivo. Consultá las alertas del servicio y el correo institucional; un envío fallido no elimina el aviso del portal. La opción de exención de inactividad no extiende la vigencia autorizada.

## Segundo factor opcional y recuperación

En **Seguridad** (`/seguridad`), confirmá tu contraseña para iniciar la configuración. Copiá la clave manual o la URI a tu aplicación autenticadora y confirmá un código válido. La interfaz actual ofrece clave/URI; no es necesario un QR.

Cancelar antes de confirmar mantiene el factor desactivado. Al activarlo se entregan **diez códigos de recuperación**, que se muestran una sola vez: guardalos fuera del portal. Regenerarlos invalida el juego anterior y exige contraseña más TOTP. Para reemplazar un factor activo, no basta conocer la contraseña.

Si perdés el teléfono, en **Completar acceso** elegí recuperar con un código guardado y presentá también tu contraseña. Ese código sólo permite configurar y confirmar un factor nuevo; no concede directamente acceso operativo. Cada código se consume una sola vez.

Si también perdiste los códigos, pedí recuperación institucional. El operador verifica identidad y emite una autorización de cinco minutos y un uso, sin desactivar tu factor ni crear cuentas auxiliares. También existe este procedimiento para el único administrador.

Para desactivar voluntariamente 2FA se exige contraseña y prueba del factor o un código de recuperación vigente. Se cierran las sesiones y los códigos anteriores quedan invalidados. El siguiente ingreso vuelve a utilizar contraseña.

## Errores, teclado y ayuda

Un error de consulta se muestra como error o dato anterior con su antigüedad, no como un listado vacío confirmado. Usá **Reintentar** cuando corresponda. Los diálogos admiten Tab/Shift+Tab, foco visible y cierre por Escape cuando el paso no sea obligatorio ni esté enviándose.

Al informar un problema, indicá pantalla, identificador del pedido/servicio, instante y mensaje. No compartas contraseñas, códigos, cookies ni claves privadas. Para comprobar usabilidad, el responsable de una cátedra debe poder enviar un pedido y consultar su estado sin ayuda, completando el formulario en hasta tres minutos; la decisión administrativa y la espera de infraestructura no se cuentan.

Referencias: [manual administrativo](manual-administrador.md), [servicios de referencia](../infra/services/README.md) y [estado de aceptación](evidencia/009/cierre.md).
