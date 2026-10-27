# US6 — Catálogo, perfiles y acceso en UI

T098/T099 implementadas y T100 documentada. Definiciones administrativas permiten crear borrador, editar manifiesto, registrar evidencia, validar, publicar y retirar por acciones separadas. La versión validada queda de solo lectura. Perfiles eligen una definición publicada del mismo modelo y respetan mínimos; QEMU solo conserva lectura histórica. Se quitó la selección de imágenes PVE de este formulario.

Catálogo está disponible a usuarios operativos y muestra solo ofertas LXC disponibles, agrupadas por modelo. Reutiliza el formulario completo de solicitud/vigencias y conserva el perfil elegido. Si el perfil se retira al abrir, informa el cambio sin seleccionar otro silenciosamente. El docente no recibe controles de definición ni datos técnicos del manifiesto.

Ver acceso consulta metadatos solo al abrir el detalle, no una vez por fila. El revelado exige botón deliberado, tiene opción de ocultar y copia únicamente por otro botón explícito. BookStack filtra también en UI los campos internos. La verificación administrativa reutiliza RegistroEvidencia, conserva claves idempotentes de reintentos, importa primero y confirma por UUID/endpoint/fecha en otra acción. Una nueva edición de evidencia elimina la referencia anterior del formulario. Tras confirmar se oculta la contraseña y se consulta el estado actualizado.

El editor de manifiesto conserva el texto original dentro del sobre API manifest, incluidos duplicados para que el servidor los rechace. Una prueba de navegador comprueba ese formato y la conservación del texto ante 422.

## Verificación

- Suite Vitest completa: **24 aprobadas en 12,57 s**, `/tmp/nap009-us6-frontend-suite.txt`.
- Primeros cuatro recorridos de navegador de catálogo y acceso: **4 aprobados en 7,2 s**, `/tmp/nap009-us6-ui-browser.txt`.
- Catálogo/editor ampliados: **3 aprobados en 5,7 s**, `/tmp/nap009-us6-catalogo-wire.txt`. Incluye publicación/retiro, solicitud con vigencia y sobre JSON con duplicados.
- SPA compilada y lint sin errores; advertencias existentes de hooks y bundle grande pendientes de US7. Logs `/tmp/nap009-us6-ui-build.txt` y `/tmp/nap009-us6-ui-lint-final.txt`.
- Captura de detalle tras entrega inspeccionada visualmente: `/tmp/nap009-access-ui.png`, datos sintéticos. No se detectaron desbordes en el viewport de escritorio de este recorrido; no sustituye la aceptación de teclado/personas de T119.

Las pruebas usan SPA compilada y todos los endpoints/servicios externos simulados/bloqueados. No acreditan un producto real instalado. El primer intento de navegador falló antes de ejecutar pruebas por Chromium ausente en `/tmp`. Se instaló en caché persistente `/home/mauro/.cache/nap009-playwright` y se repitieron los recorridos correctamente; no era una espera de Proxmox. La prueba de clipboard se ajustó al getter de navigator que instala user-event, sin modificar el comportamiento de la aplicación para hacerla pasar.

La [guía técnica](../../../infra/services/README.md) y la [guía introductoria](../../../specs/009-remediar-hallazgos-cierre/guia-servicios-referencia.md) distinguen preparación inicial de uso diario, versiones compatibles y libro virtual provisional. Incluyen comandos reales del builder y registro, con marcadores explícitos donde faltan datos institucionales. T101/T102 siguen pendientes.
