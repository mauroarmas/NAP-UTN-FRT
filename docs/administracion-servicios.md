# Administración sencilla de servicios

Desde **Catálogo**, administración gestiona los servicios. Las cátedras consultan lo disponible y hacen pedidos.

## Agregar una aplicación

1. Pulsar **Agregar servicio** y buscar por nombre o elegir una categoría del proveedor.
2. En una aplicación con **Instalación automática**, pulsar **Agregar servicio**, revisar nombre y descripción y elegir **Agregar al catálogo**.
3. NAP completa la instalación y las comprobaciones en segundo plano. Al terminar muestra **Servicio disponible**.

Se puede cerrar la ventana y volver después. No hay pasos manuales de preparar, comprobar o publicar,
ni plazos de 24 horas. Si algo falla, se muestra el problema y se puede reintentar o cancelar el alta.
Agregar una aplicación conserva su imagen para reutilizarla y retira los contenedores auxiliares.
Cada pedido aprobado tendrá su propia instancia. Retirar un servicio impide nuevos pedidos y conserva los existentes.

Actualmente, Draw.io tiene instalación automática. Otras aplicaciones de la biblioteca pueden necesitar
soporte técnico inicial; NAP lo indica antes de permitir agregarlas. No se crean fichas para aplicaciones
sin instalación disponible ni aparece una sección «Guardadas». Las altas existentes se retoman al
elegir nuevamente la aplicación. Guardar una ficha no equivale a contar con instalación automática.

Las categorías y descripciones se consultan en las colecciones públicas del proveedor; si no se
pueden actualizar, se informa y sigue disponible la búsqueda por nombre. Descubrir una aplicación
no habilita la ejecución automática de su script.

El objetivo acordado es una nube pequeña para la universidad, incluyendo aplicaciones propias
basadas en imágenes. Esa ampliación sigue pendiente: ver [rumbo del producto](rumbo-mini-cloud.md).

## Entornos Linux (IaaS)

**Ubuntu 24.04 y Debian 13** aparecen automáticamente cuando sus plantillas estándar están descargadas
en Proxmox y está configurada la red Linux. **Actualizar catálogo** vuelve a consultar el nodo.
No hay que construirlas ni publicarlas. Retirar una base se respeta en las siguientes actualizaciones.

## Dos tamaños y aprobación

| Tamaño | CPU | Memoria | Disco |
|---|---:|---:|---:|
| Small | 1 vCPU | 512 MB | 4 GB |
| Medium | 2 vCPU | 1024 MB | 8 GB |

La cátedra elige el servicio, explica su propósito pedagógico e indica las fechas. Se conserva **Otro**
para necesidades aún no disponibles. Administración elige Small o Medium y aprueba, rechaza o pide aclaración.
Aprobar reserva los recursos; se despliega desde la fecha inicial. Cambiar una recomendación no modifica
los pedidos ya aprobados. La vigencia académica sigue siendo independiente del catálogo.

Al revisar un pedido, NAP comprueba la disponibilidad automáticamente. El formulario muestra
el servicio, Small/Medium y las fechas solicitadas; **Cambiar fechas** permite ajustarlas.
Los detalles de capacidad quedan en una sección opcional. **Aprobar pedido** reserva los recursos;
**Desplegar después de aprobar** solicita también la creación si la fecha inicial está habilitada.
Si otra asignación cambia la capacidad, se conservan los datos y se puede usar **Actualizar disponibilidad**.
Las variaciones normales del uso de memoria del host no invalidan la aprobación.

## Pruebas manuales

- Abrir **Catálogo** como administrador: Ubuntu, Debian y Draw.io deben figurar como disponibles en el laboratorio.
- Filtrar por **IaaS**, **PaaS** o **SaaS** y buscar por nombre.
- Hacer un pedido de Ubuntu o Debian con justificación y fechas; aprobarlo con Small y desplegarlo cuando la fecha inicial lo permita.
- En **Servicios → Ver acceso**, comprobar que se recuperen las credenciales. El administrador puede abrir
  la consola iniciando sesión con su cuenta propia de Proxmox. Las cátedras necesitan su acceso individual
  configurado por la institución; NAP no comparte la cuenta ni el token de administración.
- Agregar una aplicación compatible: no deben aparecer pasos de preparar o publicar. Cerrar la ventana,
  volver a abrirla y comprobar que continúe la misma alta.
- Simular una desconexión: debe conservar el catálogo anterior y mostrar el error, sin anunciar un alta exitosa.
- Como cátedra, comprobar que se puedan pedir servicios disponibles u **Otro**, sin herramientas administrativas.

El responsable técnico configura la conexión y las redes una sola vez. Ver [conexión de infraestructura](conexion-infraestructura.md).
Las pruebas automatizadas con simuladores no sustituyen verificaciones en la infraestructura real.

## Seguir un despliegue

En **Pedidos → Ver detalle**, NAP muestra el avance por etapas: preparar recursos, crear instancia,
iniciar aplicación y habilitar acceso. La barra representa etapas completadas, sin estimar minutos.
El listado y el detalle se actualizan automáticamente mientras el pedido está en despliegue.

**Servicio iniciado · acceso pendiente** significa que la instancia ya arrancó y falta completar la
verificación de acceso. No indica que continúe instalándose. **Servicio disponible** corresponde a
la entrega completada. Si hay un error o una consulta falla, se muestra esa situación y se conserva
el último estado conocido.

La **campana de notificaciones** muestra avisos de aprobación, inicio de despliegue y resultado.
Al pulsar un aviso se abre su pedido. Se pueden marcar como leídos; esa preferencia se guarda por
cuenta en este navegador. Los avisos nuevos de avance son internos al portal; los correos de los
otros eventos conservan su configuración existente.

Draw.io se abre desde **Servicios → Ver acceso → Abrir aplicación** usando la sesión de NAP, sin otra
contraseña. El texto de BookStack sólo corresponde a BookStack. Ver [acceso con NAP](acceso-aplicaciones-nap.md).

En **Ver acceso** sólo se muestran el estado y las acciones de uso. No se piden documentos de evidencia,
UUID ni fechas técnicas. Las comprobaciones automáticas y el historial permanecen internos.

La búsqueda de nuevas imágenes consulta Docker Hub. Las limitaciones de compatibilidad
se muestran al agregar un servicio; el catálogo comprobado es independiente de los resultados de búsqueda.

## Administrar instancias desplegadas

En **Servicios**, el botón **Detener servicio** apaga el contenedor y conserva sus datos.
Cuando está detenido aparece **Iniciar servicio**. En **Opciones del servicio** están
**Reiniciar**, **Estado en Proxmox** y **Dar de baja**. Esta última acción, exclusiva de
administración, pide confirmación y elimina la instancia y sus datos; conserva el historial
administrativo. No retira la aplicación del catálogo.

El sistema comprueba cada minuto el estado de los recursos identificados como propios.
**Estado en Proxmox** permite comprobarlo inmediatamente y actualizar el listado.
Una consulta fallida conserva el último estado conocido. La fecha de comprobación se muestra
junto al servicio. Una operación en curso conserva su bloqueo hasta confirmar su resultado.

Detener y dar de baja no requieren completar el nombre histórico ni las fechas académicas;
sí requieren identidad y asignación registradas, y el ejecutor comprueba la pertenencia real
antes de actuar. Iniciar y reiniciar conservan las comprobaciones de capacidad y vigencia.
Si el contenedor ya está detenido, la orden de detención se resuelve sin reenviarla.
La recuperación de una detención sin identificador de tarea registra explícitamente el
estado observado, sin afirmar que se recuperó la tarea externa.
