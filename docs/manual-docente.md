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

1. Elegí una aplicación del catálogo (disponibles desde Docker Hub o imágenes propias universitarias) o una plantilla de infraestructura Linux (Ubuntu 24.04 o Debian 13).
   - En Plataforma y Software también podés elegir **Otro** para solicitar un software específico; podés indicar el nombre, una referencia de imagen Docker opcional e instrucciones breves sin completar datos técnicos ni elegir hardware.
2. Elegí una de tus cátedras. Si sólo tenés una, aparece preseleccionada.
3. Completá el nombre del pedido y la **justificación pedagógica**: actividades, estimación de estudiantes y requerimientos docentes.
4. Seleccioná el período lectivo (cuatrimestral o anual) o indicá fechas personalizadas dentro del año académico.
5. Comprobá los datos y pulsá **Enviar solicitud**. No necesitás indicar IPs, puertos, memorias ni parámetros de virtualización.

Si elegís **Otro**, el pedido queda registrado para que administración revise la solicitud y asigne una imagen compatible al momento de aprobar. La solicitud no crea contenedores ni reserva capacidad anticipadamente; la reserva se efectúa cuando administración aprueba el pedido.

Consultá el avance desde **Pedidos**:
- La barra de cuatro etapas (**Preparar recursos → Crear instancia → Iniciar aplicación → Habilitar acceso**) muestra el progreso real del despliegue en curso sin porcentajes simulados.
- Los estados posibles son `solicitado`, `requiere_ajuste`, `aprobado`, `en_despliegue`, `activo`, `suspendido`, `error`, `rechazado` y `cancelado`.
- Si administración pulsa **Pedir aclaración**, el pedido pasa a **Aclaración pendiente**: podés responder en el detalle y reenviar el pedido sin perder el historial.

## Usar los servicios

En **Servicios** (`/servicios`) aparecen los recursos activos de tus cátedras:
- **Acceso web seguro a aplicaciones**: Pulsá **«Ver acceso»** y luego **«Abrir aplicación»**. El sistema abre la herramienta mediante el gateway HTTPS protegido de NAP vinculado a tu sesión académica, sin exponer contraseñas en el navegador ni requerir complementos.
- **Acceso a infraestructura Linux (IaaS)**: En servicios Ubuntu o Debian, usá **«Ver acceso»** para revelar de forma segura las credenciales SSH (`root`) generadas por el sistema o consultar el enlace directo a la consola interactiva.
- **Ciclo de vida**: Podés iniciar, detener o reiniciar tus servicios según la actividad del curso. El reinicio o detención conserva intactos todos los datos guardados en los volúmenes del contenedor.

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

## Draw.io en Software

Solicitar desde **Catálogo** o **Pedidos → Nueva Solicitud → Software**. La oferta muestra su versión; indicar cátedra, propósito y vigencia, sin elegir hardware. Si cambia o se retira una oferta durante el envío, el formulario conserva los datos para revisar la selección. «Otro» permite describir una aplicación todavía no ofrecida.

Administración aprueba con la versión disponible en ese momento y avisa si difiere de la solicitada. Luego la versión autorizada queda fija. Cada cátedra recibe una instancia propia cuando comienza su vigencia y se verifica la entrega. El acceso HTTPS usa una credencial de perímetro de esa instancia; no es una cuenta nativa de Draw.io. Guardar/exportar los diagramas `.drawio` localmente y reabrirlos para continuar; esta oferta no incorpora almacenamiento compartido ni colaboración.
