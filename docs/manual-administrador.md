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

## Catálogo y despliegue de aplicaciones

El catálogo administrativo unifica dos caminos simples para incorporar aplicaciones:
1. **Docker Hub**: búsqueda por nombre de imágenes públicas (por ejemplo `traefik/whoami`), mostrando procedencia y distintivos oficiales.
2. **Imagen propia**: referencia directa a imágenes en repositorios universitarios autorizados (por ejemplo `campus-demo:acceptance`).

Ambas entradas reutilizan un **único motor OCI** sobre contenedores LXC no privilegiados con Ubuntu 24.04:
- **Elegir → Agregar → Disponible para solicitar**: el alta en catálogo guarda la configuración y deja la aplicación lista para ser solicitada por las cátedras. **No crea instancias ni consume capacidad de cómputo o almacenamiento anticipadamente**.
- No existen pasos manuales de «preparar, abrir y confirmar publicación» ni ensayos de 24 horas.
- **Aprobación indivisible**: al aprobar un pedido, la reserva de cómputo y almacenamiento se realiza en forma atómica en el libro mayor (`CompromisoCapacidad`). Si el inicio es futuro, el despliegue queda programado y se inicia automáticamente al llegar la fecha autorizada.
- **Consola operativa de despliegue**: los administradores disponen del botón **«Ver consola»** en Pedidos y Servicios para seguir en tiempo real la salida del instalador (fondo negro, texto blanco monoespaciado, texto literal seguro sin HTML/ANSI, retención de hasta 10 MB y 30 días). Cerrar o consultar la consola nunca altera ni cancela operaciones en marcha.
- **Recuperación ante fallos**: ante una falla transitoria de red o infraestructura, la operación queda marcada como `fallida` y se habilita el botón **«Reintentar despliegue»**. El reintento preserva los secretos del pedido y revalida la capacidad antes de despachar una operación `reparar`. Si el estado de la infraestructura es incierto tras un reinicio, NAP reconcilia con Proxmox sin duplicar contenedores.
- **Baja y retiro**: dar de baja un servicio destruye el contenedor y **sólo libera la dirección IP y la capacidad tras confirmar la ausencia física y lógica** del recurso en Proxmox. Ante cualquier falla en la destrucción, el servicio pasa a `limpieza_pendiente` visible en el portal y no se libera la cuota. Retirar una oferta del catálogo bloquea nuevas solicitudes pero mantiene intactas las instancias existentes.

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
