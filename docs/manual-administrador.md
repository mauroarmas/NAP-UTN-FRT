# Manual administrativo y operativo de NAP

Revisión: 25 de octubre de 2026. Este manual describe los controles presentes en la spec 009. La integración con el clúster/red universitarios sigue pendiente; los ensayos locales no acreditan esa instalación. Consultar [estado de cierre](evidencia/009/cierre.md).

## Instalación y configuración

Seguir [DOCKER.md](../DOCKER.md) para construir, migrar, otorgar permisos al rol runtime, ejecutar preflight y arrancar API/proxy. Usar exclusivamente `docker-compose.production.yml` para operación. El worker tiene un perfil separado; la API no ejecuta el scheduler.

La configuración privada se monta mediante `NAP_SETTINGS_FILE`: archivos `runtime.json` y `release.json` fuera del repositorio, con propietario de ejecución y modo 0600. El ejemplo está en [infra/production/settings.example.json](../infra/production/settings.example.json). No contiene valores aptos para arrancar.

Configurar `database_url`, `secret_key`, `csrf_secret` independiente, `secret_keyring` con identificadores y claves Fernet, y `secret_active_key`. En configuración por entorno esos nombres se escriben `DATABASE_URL`, `SECRET_KEY`, `CSRF_SECRET`, `SECRET_KEYRING` y `SECRET_ACTIVE_KEY`. Conservar todas las versiones utilizadas del keyring; no regenerarlo al reiniciar ni restaurar. No existe una variable `ENCRYPTION_KEY`.

Configurar también origen HTTPS del portal, proxy confiable, zona institucional, SMTP y cuenta/token PVE de permisos mínimos con TLS y CA verificados. No usar root como identidad del portal ni desactivar verificación de certificados. Completar `infrastructure_profile`, `service_artifacts`, `network_profiles` y `runner_nodes` con las rutas internas de los contenedores. La consola usa además `console_access_profile`; su ausencia mantiene el acceso cerrado.

Los cambios de esquema son migraciones Alembic explícitas. El arranque no migra, no siembra datos y no crea/restablece cuentas. Respaldo, roles de DB, actualización y reinicios están detallados en [DOCKER.md](../DOCKER.md).

## Alta inicial y comprobaciones

Desde una terminal interactiva del backend con su configuración privada:

```bash
python -m scripts.bootstrap_admin --actor OPERADOR_INSTITUCIONAL
```

Solicita usuario, nombre, correo y contraseña sin mostrarla. Rechaza el alta si ya existe un administrador; no tiene `--force-reset`, `--apellido` ni parámetros de contraseña por línea de comandos. El primer ingreso exige cambiar esa contraseña. El 2FA es opcional para ambos roles.

Comprobaciones de sólo lectura:

```bash
python -m scripts.preflight
python -m scripts.preflight --datos
python -m scripts.preflight --datos --inventario
```

El primero valida configuración; el segundo añade datos/claves/ofertas; el tercero también sondea inventario PVE. Requiere conectividad real y permisos de lectura, sin adoptar ni crear recursos. Un resultado no apto se acompaña de códigos de diagnóstico sin secretos. No existen las opciones `--modo`, `--json` ni un modo mock operativo. Los dobles se usan en las suites de pruebas aisladas.

## Usuarios y cátedras

Las pantallas son **Usuarios** (`/usuarios`) y **Cátedras** (`/catedras`). Los roles API son `admin` y `catedra_admin`. Crear primero las cátedras sin titular y asignarlas al crear el responsable, o gestionar la reasignación de forma explícita. Un responsable puede tener varias cátedras.

El alta exige nombre, usuario, correo válido y al menos una cátedra para el rol responsable. Si se genera una contraseña provisional, se entrega por el outbox de bienvenida; no aparece en la respuesta general del usuario. Revisar el estado de correo si el envío no llega. El cambio inicial es obligatorio y no se vuelve a enviar esa contraseña después de reemplazarla.

Retirar, desactivar o degradar no puede dejar al portal sin administración activa. Reasignar cátedras conserva historial y datos. Si la identidad nativa es desconocida, el cambio puede bloquearse hasta inventariarla; desconocido no equivale a no tener acceso.

La recuperación asistida del factor se realiza con el CLI institucional después de verificar identidad:

```bash
python -m scripts.recuperar_2fa --usuario USUARIO --actor OPERADOR --motivo MOTIVO --referencia REFERENCIA
```

La autorización se entrega una sola vez en terminal interactiva, dura cinco minutos y exige además la contraseña de la cuenta. La persona entra en recuperación restringida y confirma un factor nuevo antes de operar. No se desactiva 2FA por asistencia ni existe un botón administrativo que omita esa comprobación. El procedimiento sirve también para el único administrador. No se promete una pantalla de restablecimiento de contraseña que no esté implementada.

## Consola e inventario institucional

La única derivación admitida a Proxmox es la consola del contenedor propio. No eliminar indiscriminadamente todas las identidades docentes: las identidades individuales autorizadas se limitan a los pools de sus cátedras. Infraestructura administra sus ACL directas/heredadas, sesiones y concesiones.

Importar inventario comprobado con `scripts.importar_identidades_consola --archivo ARCHIVO --actor OPERADOR --referencia ACTA`. Exige configuración explícita de base. El JSON contiene `usuario_id`, `estado` (`asignada` o `sin_identidad`) e `identidad`. Una identidad asignada no se reemplaza sin revocación.

Antes de habilitar consola, demostrar en la versión real del clúster que se terminan sesiones previas y se deniega una URL guardada, conservando otros pools legítimos. Registrar la evidencia tipada y completar el trámite. El campo `console_access_profile` selecciona explícitamente esa evidencia y su SHA-256, clúster/versión e identidades/scopes con revisiones vigentes. Ver el [contrato](../specs/009-remediar-hallazgos-cierre/contracts/console-access.md). La existencia de un archivo de laboratorio no habilita la consola.

Al reasignar/retirar acceso nativo: NAP bloquea primero el alcance y devuelve un trámite pendiente. El operador institucional revoca ACL/sesiones y prueba los accesos negativos; administración registra el JSON en **Registrar evidencia institucional** y confirma por UUID en **Cambios de consola** (`/admin/cambios-consola`). Sólo entonces se completa el cambio. Si falla, registrar el motivo y mantener el trámite pendiente, sin entregar al nuevo titular. Actualizar las declaraciones de concesión sólo después de comprobarlas en PVE.

## Calendario, pedidos y capacidad

En **Calendario lectivo** (`/calendario`), consultar un año **desde 2026** y configurar inicio/fin de primer cuatrimestre, segundo cuatrimestre y anual. Cada tarjeta muestra si está completa, sin configurar o requiere revisar sus fechas. Los cuatrimestres no se solapan; una modalidad vacía queda sin configurar. **Quitar fechas** limpia esa modalidad en el formulario; el cambio se aplica al guardar. No se admiten fechas anteriores al 01/01/2026. Guardar utiliza revisión esperada y conserva las fechas aprobadas anteriormente. No hay períodos fijados por el desarrollador ni duración académica de 180 días.

En **Pedidos** (`/pedidos`), revisar la solicitud y sus observaciones. **Pedir aclaración** devuelve el pedido a la cátedra con observaciones, aviso en el portal y correo según sus preferencias. La cátedra puede responder y reenviar únicamente mientras esté pendiente esa aclaración; administración recibe un nuevo aviso. Aprobar, rechazar y cancelar sigue siendo administrativo. La reserva se establece al aprobar, no al responder una aclaración.

Si la cátedra eligió **Otro** en Plataforma o Software, el pedido conserva el nombre del servicio requerido, el título y la justificación pedagógica, sin plantilla ni reserva inicial. Evaluar la propuesta, preparar, comprobar y publicar el servicio desde **Catálogo**. Volver al pedido y seleccionar esa oferta compatible al aprobar: queda vinculada al pedido original y se conserva la justificación. Hasta entonces puede consultarse, requerir ajustes o rechazarse; no puede desplegarse sin asignación aprobada.

Para aprobar, seleccionar un servicio compatible, tamaño **Small** o **Medium**, vigencia y destino. Pulsar **Evaluar asignación**; cambiar la selección invalida la evaluación. Revisar costo y capacidad reales. La evaluación dura sesenta segundos y una confirmación desactualizada exige repetirla. La sobreasignación requiere justificación administrativa, sin superar límites físicos imposibles. No hay cupos fijos por cátedra; las altas del portal utilizan los dos tamaños compartidos. Las renovaciones conservan los recursos autorizados originalmente.

Aprobar una alta reserva capacidad en la misma transacción. Si el inicio es futuro, se conserva la reserva durante la espera: el plazo ordinario de veinticuatro horas comienza en el posterior entre aprobación e inicio, limitado por el fin de vigencia. No se despliega antes del inicio. Revertir una aprobación sólo libera lo que aún no está enviado/materializado; un resultado incierto exige reconciliación.

## Catálogo y despliegue

La lista de **Cátedras** muestra el ID en la primera columna y un botón **Verificar infraestructura** por fila. La consulta muestra si el pool está preparado, pendiente del primer servicio o requiere atención; antes de consultarlo figura **Sin verificar**. No crea pools ni mueve invitados. El estado se refiere al pool, no certifica la red, el catálogo o la entrega de aplicaciones.

Al desplegar un servicio aprobado, NAP comprueba el pool `catedra-{id}` y lo crea si falta. Reutiliza los existentes, comprueba permisos y pertenencia de sus miembros y crea el contenedor dentro del pool. No concede permisos automáticamente ni asigna cuotas por cátedra. La cuenta API necesita `Pool.Allocate`, `VM.Allocate`, `VM.Audit` y `VM.PowerMgmt` en el alcance de ese pool; los permisos adicionales de almacenamiento/red corresponden al despliegue ordinario. Si faltan permisos, no se crea el contenedor: la operación conserva su reserva y vuelve a comprobar antes de desplegar, sujeta a vigencia y expiración. Un pool con miembros desconocidos requiere revisión manual; no se vacía ni se adopta.

Los pools de Proxmox sobreviven a la limpieza de la base de NAP. Se reutilizan por ID de cátedra y no reservan hardware por existir. **Pool View** los muestra agrupados; **Server View** muestra los invitados por nodo.

Seguir la [guía técnica de productos](../infra/services/README.md) para construir/sanear imágenes, ensayar dos instancias y registrar evidencia. Catálogo nuevo: LXC Ubuntu 24.04, PostgreSQL 16 y BookStack de referencia; QEMU queda en lectura histórica.

En **Catálogo** (`/catalogo`), abrir **Agregar servicio**, elegir una aplicación y completar nombre, descripción opcional y Small/Medium. Pulsar **Preparar aplicación**, abrirla con **Ver acceso** y elegir **Funciona correctamente → Publicar servicio** o **No funciona, eliminar**. NAP resuelve los pasos técnicos. La publicación no vence a las 24 horas. Ver [administración sencilla de servicios](administracion-servicios.md). Una oferta retirada bloquea pedidos nuevos y conserva los ya aprobados. La biblioteca permite descubrir aplicaciones; sólo las preparaciones compatibles pueden instalarse desde NAP.

El antiguo script de publicación específico de la PC está retirado. `scripts.publicar_catalogo` sólo comprueba coherencia local de archivos mediante `--manifest`, `--evidence`, `--cluster-uuid` y `--definition-id`; no registra/publica, no crea perfiles y no modifica usuarios.

Para PostgreSQL/BookStack, infraestructura prepara un pool de UUID/DNS/TLS/reservas DHCP por MAC en los perfiles de portal y runner. NAP elige una identidad no utilizada, conserva su asignación antes de crear y utiliza siempre los mismos datos en los reintentos. El pool se prepara en lote; no se editan perfiles por cada despliegue. Sin destinos preparados se informa el agotamiento antes de crear. El contrato y la lista de entrega a infraestructura están en [conexion-infraestructura.md](conexion-infraestructura.md).

Desde **Servicios** (`/servicios`) se ordena desplegar desde la fecha inicial. Una respuesta 202 admite una operación, no acredita éxito. El worker confirma tarea y propiedad, prepara el producto y registra salud local. El acceso sigue pendiente de comprobación desde la red prevista.

Abrir **Ver acceso**, revelar sólo para validación, realizar las pruebas funcionales e importar el documento `acceso_instancia` en **Registrar evidencia institucional**. Confirmar con el UUID, endpoint e instante coincidentes. Sólo después se entrega el servicio como utilizable. No marcar pruebas simuladas como reales. No modificar una cuenta ni inventar resultados para forzar publicación.

## Operación, métricas, avisos y recuperación

El worker captura por minuto y las consultas leen PostgreSQL, sin capturar por visitante. **Métricas** (`/metricas`) distingue observación confirmada, ausencia de datos y datos anteriores. La reducción de detalle conserva resúmenes diarios e historial por cátedra.

Avisos y alertas se muestran por servicio. Estado administrativo del correo: `GET /api/v1/alertas/correo`; contiene metadatos de envío y errores seguros, sin cuerpos ni secretos. Un fallo SMTP no revierte aprobación, entrega ni vigencia. El worker procesa y reintenta el outbox.

Una pausa automática se confirma antes de liberar CPU/RAM y registrar pedido suspendido. La reactivación exige vigencia y capacidad; conserva disco/datos. Una renovación con receso no autoriza encender durante ese intervalo.

Frente a una operación fallida o incierta, consultar motivo, identidad y operación. No crear otra por nombre/VMID ni liberar una reserva por timeout. El reintento sobre una preparación existente conserva identidad y claves. Un pedido ERROR sólo puede cerrarse como rechazado cuando una operación duradera acredita no haber enviado o la ausencia está confirmada, sin servicio/compromiso/operación abiertos.

Respaldar y restaurar según [operacion-respaldos.md](operacion-respaldos.md) y [preparar-restauracion.md](preparar-restauracion.md). Un dump del portal no incluye los libros ni las bases del curso. Restaurar en entorno separado, conservar keyring, revocar accesos efímeros recuperados y reconciliar antes de habilitar automatismos. Destino externo, custodios y ensayo institucional siguen pendientes de acordar con infraestructura.

## Referencias de API y aceptación

La SPA usa cookies HttpOnly y misma origin. Las mutaciones de dominio requieren Origin/CSRF; las decisiones idempotentes además `Idempotency-Key`. No usar ejemplos antiguos con Bearer como acceso operativo. Consultar contratos [auth](../specs/009-remediar-hallazgos-cierre/contracts/auth.md), [operaciones](../specs/009-remediar-hallazgos-cierre/contracts/operations.md), [catálogo](../specs/009-remediar-hallazgos-cierre/contracts/catalog-ui.md) y [evidencias](../specs/009-remediar-hallazgos-cierre/contracts/evidence.md).

Los resultados automatizados y pendientes reales están en [cierre](evidencia/009/cierre.md). Una persona ajena al desarrollo todavía debe recorrer esta guía y el responsable de una cátedra validar el flujo sin ayuda (T119); las pruebas automatizadas de documentación no sustituyen esa aceptación.

## Biblioteca y preparación de aplicaciones

En **Catálogo → Agregar servicio → Buscar en la biblioteca**, buscar por nombre o categoría e incorporar una ficha. Incorporar no instala ni publica. Para Draw.io, continuar con su preparación y seguir el recorrido sencillo de la sección anterior. Se puede cerrar la ventana y retomar el progreso después.

La preparación no tiene vencimiento automático. Publicar conserva la aplicación reutilizable y limpia los recursos auxiliares; eliminar cancela y limpia la preparación. Si la limpieza está pendiente, NAP conserva el seguimiento hasta confirmar la eliminación. Las fechas de los pedidos académicos siguen aplicándose a sus instancias.

La conexión con Proxmox, construcción y red se configura una sola vez por el responsable técnico. Si falta, NAP lo comunica antes de preparar. La [guía técnica](../infra/services/README.md) queda como referencia para ese responsable; no es un formulario que deba completar administración en cada alta.
