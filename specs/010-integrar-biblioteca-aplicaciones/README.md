# Biblioteca de aplicaciones — estado y continuidad

La especificación es [spec.md](spec.md) y su validación está en [checklists/requirements.md](checklists/requirements.md). `.specify/feature.json` apunta a esta carpeta. La implementación está en la rama `010-integrar-biblioteca-aplicaciones`, con trabajo previo conservado en el workspace.

## Decisión acordada

Administración busca una aplicación de Community Scripts, incorpora un borrador y prepara/comprueba una versión antes de publicar su oferta. Draw.io es el piloto completo. Al publicarse, la cátedra puede seleccionarlo en Catálogo o Nuevo pedido, con nombre, justificación pedagógica y fechas, sin hardware. La misma definición se reutiliza para distintas cátedras; las instancias y sus datos son independientes.

La implementación local y sus pruebas están registradas en [tasks.md](tasks.md) y [regresión](../../docs/evidencia/010/regresion.md). Las aceptaciones de staging y mediciones humanas pendientes no se consideran aprobadas por las pruebas con dobles.

## Ajuste de administración acordado

Administración se reúne en **Catálogo**, con Small (1 vCPU, 512 MB, 4 GB) y Medium (2 vCPU, 1024 MB, 8 GB) compartidos y la base Ubuntu 24.04/LXC existente. La cátedra solicita la aplicación; administración elige el tamaño al aprobar. Cada aplicación habilita sólo los tamaños que alcanzan sus mínimos comprobados. Preparación, pruebas y publicación conservan sus compuertas. Ver [guía y pruebas manuales](../../docs/administracion-servicios.md) y [validación del ajuste](../../docs/evidencia/010/servicios-tamanos.md).

## Antecedentes de la especificación inicial

- Los mantenedores indican que el catálogo actual ofrece acceso público mediante PocketBase y que el antiguo catálogo JSON cambió. No se verificó un endpoint operativo ni su contrato actual: confirmar acceso autorizado, datos, límites y condiciones antes de elegir la integración. [Respuesta del mantenedor](https://github.com/community-scripts/ProxmoxVE/issues/13545).
- La [ficha de Draw.io](https://community-scripts.org/scripts/drawio) publica la aplicación para contenedores. El [script del host](https://github.com/community-scripts/ProxmoxVE/blob/main/ct/drawio.sh) también crea el contenedor y carga un motor compartido; el [instalador](https://github.com/community-scripts/ProxmoxVE/blob/main/install/drawio-install.sh) prepara la aplicación. No asumir que ejecutar el comando externo equivale a desplegar mediante NAP.
- Al revisar esos scripts, se observó Debian 13 y Tomcat 11 para Draw.io y descargas de la versión más reciente. La planificación debe comprobar la compatibilidad vigente y cómo conservar una preparación reproducible, incluyendo las dependencias del instalador. No se ejecutaron esos scripts ni se instaló Draw.io.
- Al iniciar la especificación, [el contrato de definiciones](../../backend/app/schemas/definicion.py) limitaba los productos a Linux, PostgreSQL y BookStack; la implementación 010 agregó el adaptador Draw.io. Revisar también [el servicio de catálogo](../../backend/app/services/catalogo_service.py) y [la guía de productos](../../infra/services/README.md). Importar metadatos no amplía por sí solo la preparación, ejecución o validación permitidas.
- Conservar el flujo acordado en [la spec 009](../009-remediar-hallazgos-cierre/spec.md): pedidos por perfiles/«Otro», aclaraciones con respuesta docente y correo, reservas al aprobar, fechas desde 2026, pools automáticos por cátedra y aislamiento. No reintroducir cuotas ni campos de hardware para la cátedra.
- La base local fue limpiada por pedido del usuario conservando Usuarios/Cátedras y autenticación. Catálogo y calendario quedaron vacíos. Al iniciar esta spec seguían existiendo contenedores de ensayo fuera de la base limpia. Posteriormente se eliminaron los CT 100–107 y seis pools de prueba por pedido del usuario; ver [verificación de limpieza](../../docs/evidencia/010/reparacion-entorno-y-limpieza.md). [Acta de limpieza](../../docs/evidencia/009/limpieza-desarrollo.md).
- Una demostración simulada no acredita funcionamiento real de Draw.io. La aceptación funcional requiere probar acceso desde la red prevista y dos instancias independientes.

Las fuentes se consultaron el 25/10/2026. Estos antecedentes no reemplazan la investigación y decisiones finales de [research.md](research.md), ni la aceptación real pendiente.

## Simplificación autorizada del alta (25/10/2026)

El recorrido administrativo vigente es **elegir → preparar → abrir y comprobar → publicar o eliminar**, sin entorno manual, revisión técnica ni plazo de 24 horas. La preparación y la oferta publicada no caducan automáticamente; la vigencia de pedidos académicos se conserva. Los detalles técnicos se resuelven internamente y las aplicaciones sin adaptador compatible siguen bloqueadas.

Este ajuste sustituye la interacción avanzada y el TTL originalmente descritos en US2/FR-018, sin dar por aprobadas las aceptaciones reales pendientes. Ver [contrato vigente](contracts/alta-simple-api.md), [guía de usuario](../../docs/administracion-servicios.md) y [verificación y límites](../../docs/evidencia/010/preparacion-simple.md).
