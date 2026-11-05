# Servicios de referencia: qué vamos a ofrecer y cómo se preparan

Actualización: 20 de octubre de 2026. Orientación para la [especificación 009](spec.md). El catálogo, perfiles, recetas, runner, preparación y acceso están implementados y probados localmente. Todavía no se construyeron/publicaron imágenes operativas ni se aceptaron aplicaciones desde otra computadora. El [procedimiento técnico](../../infra/services/README.md) describe los comandos y comprobaciones pendientes de T101/T102.

**Qué significa cada nivel en este proyecto**

| Oferta | Qué recibe la cátedra | Qué prepara y mantiene el equipo del portal |
|---|---|---|
| IaaS: contenedor LXC | Un entorno Linux con recursos autorizados. | Creación, acceso, aislamiento, estado y ciclo de vida del contenedor. |
| PaaS: PostgreSQL | Una base de datos accesible con dirección, puerto, nombre y usuario propios. | La instalación y configuración del servicio de base de datos y su comprobación funcional. |
| SaaS: BookStack | Una aplicación web donde el docente publica contenido y el alumno lo consulta. | La aplicación y sus dependencias, acceso inicial, permisos, persistencia y comprobación funcional. |

Para probar PostgreSQL alcanza inicialmente con conectarse desde otro equipo, crear una tabla, escribir y consultar un dato. La documentación oficial explica el acceso mediante su cliente y otras herramientas: [acceso a una base PostgreSQL](https://www.postgresql.org/docs/current/tutorial-accessdb.html).

BookStack organiza el contenido en libros, capítulos y páginas; por eso se toma como referencia cercana a la mención de libro virtual. Esa cercanía es una elección provisional para demostrar el portal, no una conclusión sobre lo que necesita el cliente. [Organización de contenido en BookStack](https://www.bookstackapp.com/docs/user/content-overview/).

**Tres conceptos diferentes que conviene separar**

- **Plantilla de recursos:** indica cuánta CPU, memoria y disco autorizamos.
- **Definición de servicio:** indica qué producto preparar, qué versión validamos, qué parámetros admite, cómo se comprueba y cómo se entrega el acceso. Por ejemplo, la definición de PostgreSQL.
- **Instancia:** es el servicio particular de una cátedra, con sus recursos, datos, dirección y credenciales. Dos pedidos generan instancias diferentes, aunque usen la misma definición.

Una plantilla que solo indica «2 CPU y 1 GB RAM» no alcanza para dejar funcionando una base de datos o aplicación. La definición añade esa preparación y su validación.

**Cómo vamos a facilitar la creación**

La especificación exige este recorrido:

1. Preparar una definición reproducible del producto en un entorno de prueba, con sus dependencias e instrucciones.
2. Comprobar que instala o genera una instancia limpia, con acceso propio y datos persistentes.
3. Publicar la definición validada en el catálogo con una versión identificable y un perfil de recursos adecuado.
4. El docente solicita el servicio; administración revisa recursos y fechas y aprueba.
5. Cuando la fecha lo permite y se ordena el despliegue, el portal crea y personaliza la instancia, comprueba su función y entrega el acceso.
6. Administración puede repetir ese despliegue desde el catálogo sin instalar paquetes a mano en cada nueva instancia.

El [plan técnico](plan.md) eligió preparar una imagen de aplicación saneada y personalizar cada instancia con una operación limitada de infraestructura. La imagen incluye el software instalado, pero no contraseñas, claves ni datos de cátedras anteriores. Proxmox crea el LXC y una preparación controlada configura el acceso propio de esa copia. Su compatibilidad se comprobará con el clúster disponible antes de publicar la oferta. [Referencia oficial de contenedores de Proxmox](https://github.com/proxmox/pve-docs/blob/master/pct.adoc).

El plan define credenciales independientes, comprobación de función y recuperación de fallos sin crear otra copia del servicio. Antes de anunciarlo como utilizable, administración realiza la prueba de acceso de esa instancia desde la red prevista, importa su documento de evidencia en el formulario administrativo y usa la referencia devuelta para confirmar el acceso. El mismo registro recibe la evidencia de preparación de una definición; el [contrato de evidencias](contracts/evidence.md) describe el formato para el equipo técnico. No se requiere introducir URLs ni rutas de archivos del servidor. No alcanza con que el contenedor figure encendido. El flujo ya está implementado con pruebas locales; su habilitación y aceptación reales siguen pendientes. La pantalla Ver acceso distingue preparación local, validación administrativa y entrega. Registrar evidencia y confirmar acceso son acciones separadas, y repetirlas no duplica la entrega.

La preparación inicial de un producto sigue siendo una tarea técnica, que esta entrega debe dejar documentada. Lo que se simplifica para la operación diaria es repetir despliegues ya validados. Incorporar otro producto significa preparar y validar una nueva definición compatible, conservando el flujo de solicitud y aprobación.

**Qué se comprobará en los dos ejemplos**

| Ejemplo | Prueba mínima | Comprobaciones adicionales |
|---|---|---|
| PostgreSQL | Conexión remota con la cuenta entregada; escritura y lectura de un registro. | Dos cátedras aisladas, credenciales diferentes y dato conservado al reiniciar. Es una instancia distinta de la base interna del portal. |
| BookStack | Docente crea un libro y una página y cuentas individuales; cada alumno ingresa con su cuenta de lectura. | El lector no puede editar/administrar; revocar una cuenta no afecta a las demás; el contenido permanece tras reiniciar; dos instancias no comparten datos o secretos. |

BookStack requiere su propio conjunto de componentes web y una base MySQL/MariaDB. El PostgreSQL ofrecido como PaaS no se presenta como la base interna de BookStack. La receta fija BookStack 26.09.1, PHP 8.3 y MariaDB 10.11; PostgreSQL usa la familia 16. El build exige patches/paquetes exactos y digests, datos nuevos y secretos propios de cada instancia. [Instalación de BookStack](https://www.bookstackapp.com/docs/admin/installation/).

La [guía de preparación y operación](../../infra/services/README.md) cubre build, validación/publicación, prueba individual, mantenimiento, variantes y retiro. Los procedimientos finales y ensayos de respaldo/restauración siguen pendientes de cierre. Los alumnos no reciben credenciales de administración del portal ni del clúster.

El docente crea y revoca las cuentas individuales de lectura dentro de su instancia BookStack, donde también publica contenido. Esas cuentas pertenecen a la aplicación y no requieren registrar alumnos en NAP. La demostración no usará una cuenta compartida ni lectura anónima; tampoco exige sincronización de usuarios con el portal. Los permisos del docente se limitan a su propia aplicación. La configuración concreta deberá comprobar los permisos de los lectores y el efecto de revocar una cuenta. [Roles y permisos de BookStack](https://www.bookstackapp.com/docs/user/roles-and-permissions/).

**Responsabilidad de los respaldos**

El portal tendrá respaldo y restauración de sus datos internos de gestión. Para PostgreSQL y BookStack de las cátedras se entregará un procedimiento documentado de copia y restauración mediante herramientas externas al portal, coordinadas con infraestructura. Esta entrega no incorpora un módulo del portal que programe o gestione los respaldos de esas aplicaciones.

El procedimiento debe identificar qué datos y configuración se conservan, quién ejecuta y verifica las copias y cómo recuperar el acceso. Se probará en un entorno separado recuperando un dato de PostgreSQL y un libro/página de BookStack desde sus respectivos cortes. Una copia de la base interna del portal no demuestra haber respaldado el contenido de las aplicaciones desplegadas.

**Qué falta relevar sobre el libro virtual**

En la entrevista conviene determinar si existe una aplicación elegida o desarrollada por la facultad; quién crea el contenido; si se necesita solo lectura o también ejercicios, evaluaciones e interacción; si el producto final mantiene el esquema de cuentas individuales elegido para la demostración; qué contenido existente debe importarse; qué red tendrá acceso y cómo deben conservarse los datos al terminar el período.

Esas respuestas pueden justificar mantener BookStack o sustituir el ejemplo por otra aplicación. La demostración básica permite avanzar ahora con el mecanismo de preparación, catálogo y entrega, sin afirmar que esos requisitos pedagógicos ya estén acordados.

**Cómo se relaciona con el calendario elegido**

Administración configura los períodos de cada año. Un pedido académico toma las fechas del período seleccionado y las conserva al aprobarse. Antes del inicio permanece aprobado en espera: no se crea la instancia. Desde la fecha inicial se habilita la acción de despliegue.

En un alta, la capacidad se compromete desde la aprobación y el plazo ordinario para desplegar empieza cuando el despliegue ya está permitido. Así una aprobación anticipada no pierde su reserva por esperar al comienzo del cuatrimestre. Los cambios posteriores del calendario no cambian silenciosamente lo que ya se autorizó.

Si se renueva un servicio para un período que comienza después del actual, el intervalo intermedio queda sin cobertura: al terminar el primero se confirma la pausa y se conservan datos y disco. Desde el nuevo inicio la cátedra puede solicitar reactivación, comprobando capacidad disponible. Esa renovación no mantiene cómputo reservado durante el receso ni recrea el servicio; si falta capacidad, permanece pausado y se puede reintentar dentro de la vigencia.

**Recorrido que puede usar quien no prepara imágenes**

1. En Catálogo, elegir un perfil publicado de Linux, base de datos o aplicación. Elegir cátedra y vigencia con el formulario completo.
2. Administración evalúa y aprueba. Antes de la fecha inicial no se despliega.
3. Seguir la operación en Pedidos/Servicios. Una respuesta pendiente no es una entrega terminada.
4. Administración abre Ver acceso, revela solo para validar y prueba esa instancia desde la red prevista. Importa el documento del ensayo y confirma su UUID por separado.
5. Una vez entregado, el docente revela su acceso inicial. En BookStack publica contenido y crea/revoca lectores individuales dentro de la aplicación; no da de alta alumnos en NAP.

La configuración de red, DNS y certificados se coordina con infraestructura. Si falta, el portal conserva el estado pendiente/incierto y los datos, y muestra el siguiente paso. BookStack sigue siendo una referencia provisional hasta entrevistar al cliente.
