# Continuar esta feature en otro chat

La especificación es [spec.md](spec.md) y su validación está en [checklists/requirements.md](checklists/requirements.md). `.specify/feature.json` apunta a esta carpeta. Se mantuvo la rama existente `009-remediar-hallazgos-cierre`; la numeración de esta carpeta no crea una rama Git. Los cambios previos de la spec 009 permanecen en el workspace.

## Decisión acordada

Administración busca una aplicación de Community Scripts, incorpora un borrador y prepara/comprueba una versión antes de publicar su oferta. Draw.io es el piloto completo. Al publicarse, la cátedra puede seleccionarlo en Catálogo o Nuevo pedido, con nombre, justificación pedagógica y fechas, sin hardware. La misma definición se reutiliza para distintas cátedras; las instancias y sus datos son independientes.

Se creó únicamente documentación. El siguiente paso es `/speckit-plan` sobre esta feature; todavía no hay plan, tareas ni implementación de la biblioteca.

## Hechos y cuestiones para investigar al planificar

- Los mantenedores indican que el catálogo actual ofrece acceso público mediante PocketBase y que el antiguo catálogo JSON cambió. No se verificó un endpoint operativo ni su contrato actual: confirmar acceso autorizado, datos, límites y condiciones antes de elegir la integración. [Respuesta del mantenedor](https://github.com/community-scripts/ProxmoxVE/issues/13545).
- La [ficha de Draw.io](https://community-scripts.org/scripts/drawio) publica la aplicación para contenedores. El [script del host](https://github.com/community-scripts/ProxmoxVE/blob/main/ct/drawio.sh) también crea el contenedor y carga un motor compartido; el [instalador](https://github.com/community-scripts/ProxmoxVE/blob/main/install/drawio-install.sh) prepara la aplicación. No asumir que ejecutar el comando externo equivale a desplegar mediante NAP.
- Al revisar esos scripts, se observó Debian 13 y Tomcat 11 para Draw.io y descargas de la versión más reciente. La planificación debe comprobar la compatibilidad vigente y cómo conservar una preparación reproducible, incluyendo las dependencias del instalador. No se ejecutaron esos scripts ni se instaló Draw.io.
- Actualmente [el contrato de definiciones](../../backend/app/schemas/definicion.py) limita los productos a Linux, PostgreSQL y BookStack. Revisar también [el servicio de catálogo](../../backend/app/services/catalogo_service.py) y [la guía de productos](../../infra/services/README.md). Importar metadatos no amplía por sí solo la preparación, ejecución o validación permitidas.
- Conservar el flujo acordado en [la spec 009](../009-remediar-hallazgos-cierre/spec.md): pedidos por perfiles/«Otro», aclaraciones con respuesta docente y correo, reservas al aprobar, fechas desde 2026, pools automáticos por cátedra y aislamiento. No reintroducir cuotas ni campos de hardware para la cátedra.
- La base local fue limpiada por pedido del usuario conservando Usuarios/Cátedras y autenticación. Catálogo y calendario quedaron vacíos. Los contenedores de ensayo en Proxmox siguen existiendo fuera de la base limpia; no adoptarlos ni eliminarlos automáticamente para esta feature. [Acta de limpieza](../../docs/evidencia/009/limpieza-desarrollo.md).
- Una demostración simulada no acredita funcionamiento real de Draw.io. La aceptación funcional requiere probar acceso desde la red prevista y dos instancias independientes.

Las fuentes se consultaron el 25/10/2026. Revisar su estado al retomar; esta nota no reemplaza la investigación técnica del plan.
