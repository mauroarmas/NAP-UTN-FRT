# Servicios del catálogo y tamaños compartidos

Fecha: 2026-10-25. Ajuste posterior a la integración local de la feature 010, por decisión del usuario. Se conserva el árbol de trabajo previo y la rama `010-integrar-biblioteca-aplicaciones`.

## Resultado

- Una entrada **Administración → Servicios del catálogo** sustituye las entradas separadas Definiciones y Perfiles. Las direcciones anteriores redirigen.
- Small: 1 vCPU, 512 MB RAM, 4 GB disco. Medium: 2 vCPU, 1024 MB RAM, 8 GB disco. Se utiliza la base Ubuntu 24.04/LXC existente.
- El frontend consulta los tamaños del backend para alta, edición, publicación y aprobación; no mantiene otra copia operativa de esos valores.
- Cada preparación determina sus tamaños compatibles a partir de sus mínimos. Una aplicación que supera Medium queda sin oferta disponible; la interfaz explica el bloqueo y no reduce sus requisitos.
- La cátedra elige aplicación, propósito y fechas. Administración elige el tamaño; cambiarlo invalida la evaluación antes de aprobar. El snapshot aprobado conserva tamaño y recursos. Las renovaciones históricas conservan su asignación original.
- La publicación de una revisión permite elegir el servicio existente por nombre, conservando su ID/revisión internamente.
- El alta se realiza desde **Servicios disponibles → Agregar servicio**, con búsqueda, preparación y publicación dentro de un mismo diálogo. Las herramientas técnicas y evidencias quedan en **Opciones avanzadas: registro manual y versiones** del formulario. Importar, preparar, comprobar y publicar siguen siendo acciones distintas.
- Tarjetas alineadas, búsqueda, confirmación de retiro, filtros y navegación móvil; temas claro/oscuro y selección mediante teclado.

## Verificación ejecutada

| Alcance | Resultado |
|---|---|
| Backend: perfiles/definiciones, biblioteca, ensayos, admisión y evaluación (`test_perfiles_definiciones_009`, `test_biblioteca_api_010`, `test_biblioteca_pedidos_010`, `test_ensayos_api_010`, `test_admision_inicio_009`, `test_evaluacion_asignacion_009`) | 20 passed, 17.93 s |
| Backend: tamaños nuevos, alta/edición/retiro de ofertas, catálogo y entrega Draw.io (`test_tamanos_catalogo`, `test_templates_edicion`, `test_templates_retiro`, `test_templates_admin`, `test_catalogo_definiciones_009`, `test_drawio_entrega_010`) | 43 passed, 24.65 s |
| `npm --prefix frontend test -- --run` | 53 passed, 14 archivos, 23.87 s |
| `npm --prefix frontend run test:e2e -- --reporter=line` | 36 passed; incluye build Vite y los cuatro recorridos nuevos |
| `npm --prefix frontend run lint` | Sin errores; ocho advertencias preexistentes de hooks/exports |
| `git diff --check` | Sin errores |
| API local `http://localhost:8001/openapi.json` | Incluye `/api/v1/templates/tamanos` |
| Frontend local `http://localhost:5174/admin/servicios` | HTTP 200 |

Las dos selecciones aprobadas en backend utilizan las reservas y snapshots reales del dominio con infraestructura simulada. Se comprueba que publicar no reserve capacidad, que un tamaño desconocido o recursos alterados sean rechazados y que editar la recomendación conserve la asignación aprobada. Son 63 casos backend seleccionados, no una nueva ejecución de la suite completa.

Se inspeccionaron capturas de la pantalla y el editor en temas claro/oscuro y ancho móvil de 390 px; los recorridos comprueban ausencia de desbordamiento horizontal, tarjetas alineadas y apertura/cierre por teclado de la navegación móvil. Los datos de las capturas y los recorridos de navegador son fixtures.

No se modifica el esquema de la base ni se ejecutan cambios sobre Proxmox. Los contratos numéricos anteriores permanecen compatibles para integraciones e historia; cuando se envía `tamano`, el backend exige recursos exactamente coherentes. El portal utiliza los dos tamaños en las altas, publicaciones y aprobaciones nuevas. Las tareas reales de staging/mediciones de 010 continúan con el estado que registra `tasks.md`.

Guía y comprobaciones manuales: [administración de servicios](../../administracion-servicios.md).

## Revisión del alta: formulario único

Por nueva indicación del usuario, se retiraron las pestañas de la pantalla principal. **Servicios disponibles** queda como única sección de gestión y contiene **Agregar servicio**. El formulario permite usar una aplicación publicada o buscar/importar una ficha, editarla, continuar con la preparación y publicar sin abrir otros diálogos. La búsqueda se conserva al volver a la selección inicial. Los accesos antiguos de preparación abren este mismo formulario.

La suite de componentes pasó con **54 casos** (14 archivos, 17.67 s) y la suite de navegador con **36 casos** (56.9 s). El recorrido de biblioteca ahora entra por el botón de alta, guarda una ficha y continúa con la preparación dentro de un solo diálogo. Se mantuvieron los recorridos de versiones, errores, recuperación de ensayos y retiro. Se estabilizó la preparación de datos de una prueba histórica para esperar a la inicialización del formulario antes de escribir fechas.

Esta revisión modifica la interfaz y su composición; no cambia API, reservas ni infraestructura.

## Catálogo único por rol

El acceso principal **Catálogo** (`/catalogo`) reúne consulta, solicitudes y administración cuando la sesión es de administrador. Se elimina el enlace duplicado de Administración. Las direcciones administrativas anteriores redirigen al catálogo únicamente dentro de las rutas del administrador; la vista docente conserva su componente de consulta y solicitudes, sin montar formularios, consultas ni controles administrativos.

Se conserva **Solicitar** para administración, junto a alta/edición/retiro y filtros. La selección de aplicación y cátedra en la solicitud administrativa se comprobó en navegador. También se verificó que una cátedra no vea alta/edición/retiro ni solicite definiciones, tamaños administrativos u ofertas retiradas; la entrada directa por la dirección administrativa anterior tampoco habilita gestión.

Validación: **54 pruebas de interfaz** (14 archivos); **6 escenarios finales de navegador** en `servicios-admin.spec.js` (13.1 s), incluidos temas/móvil, redirecciones, solicitud administrativa y aislamiento del rol docente. La selección más amplia de recorridos de biblioteca y catálogo también pasó antes del cierre. **10 pruebas backend** en `test_templates_admin.py` y `test_biblioteca_api_010.py` (6.32 s), con rechazo 403 de alta/edición/retiro y biblioteca para el rol docente. Build Vite y `git diff --check` correctos; lint sin errores y ocho advertencias anteriores.

## Simplificación visual del asistente

Por indicación del usuario se amplió exclusivamente el alta de servicios: hasta 1160 px de ancho y 880 px de alto, adaptados al viewport. Cabecera y pasos visuales permanecen visibles mientras se desplaza el contenido. La biblioteca usa búsqueda compacta, tarjetas con iconos y colores, fichas guardadas y un panel de selección con la acción principal **Preparar aplicación**. Descripción y metadatos técnicos quedan desplegables; se retiraron párrafos repetidos y textos de datos desconocidos. En móvil, el panel seleccionado se muestra antes de los resultados y no hay desbordamiento horizontal.

La etapa de publicación del indicador se activa sólo al disponer de un ensayo comprobado y una definición validada. La ficha distingue preparación disponible de adaptación pendiente y conserva el aviso de que incorporar no instala/publica.

Validación final: 55 pruebas de interfaz aprobadas (14 archivos, 31.35 s), 8 recorridos de navegador aprobados (30.2 s, build incluido). Se comprobó ancho superior a 1000 px en escritorio y ausencia de desbordamiento en móvil, además de error visible, reintento idempotente, foco, guardado y continuación. Se inspeccionaron capturas en temas claro/oscuro y móvil. No se cambian reservas, permisos, API ni recursos de infraestructura.
