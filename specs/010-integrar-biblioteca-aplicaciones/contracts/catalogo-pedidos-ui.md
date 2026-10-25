# Contrato de oferta, pedidos y experiencia

## Identidad estable y publicación

La oferta es el perfil actual `RecursoTemplate`, no una entrada paralela de catálogo. El asistente de publicación crea el primer perfil o selecciona uno existente del mismo código/producto/modelo. Publicar una nueva versión cambia atómicamente ese perfil y aumenta `revision`; si existen otros perfiles se actualizan sólo por decisión explícita individual. Cada uno conserva su bitácora.

`GET /templates/` mantiene contrato actual y añade para ofertas de biblioteca metadatos seguros: `origen_biblioteca`, `version_ofrecida` y `revision`. Cátedra sólo obtiene oferta publicada/activa, descripción y disponibilidad; no comando, manifiesto, nodo, VMID, hardware editable ni estado de ensayos. No cambiar la semántica de perfiles de Linux/PostgreSQL/BookStack ajenos a esta función.

## Selección y aprobación

- Catálogo abre `NuevoPedidoModal` con el `template_id` elegido. También es elegible desde Nuevo pedido, tipo Software. «Otro» permanece en Plataforma/Software.
- Crear/reenviar valida oferta vigente y pertenencia de cátedra en servidor y persiste `seleccion_oferta_snapshot` con ID/revisión/definición/version observados. Formulario requiere cátedra, nombre, justificación y vigencia válida desde 2026, sin CPU/RAM/disco ni instalación.
- Si la oferta se retiró o cambió mientras se completaba el formulario: conservar campos; retiro exige revisar selección. Si sólo cambió de versión, mostrar la oferta vigente antes de enviar y registrar lo efectivamente enviado. No enviar una versión ocultamente distinta de la mostrada.
- Evaluación administrativa de alta resuelve la definición vigente de la oferta. Respuesta añade `{version_solicitada, version_efectiva, cambio_version}` y mantiene asignación, vigencia, destino y token existentes. La UI informa el cambio antes de aprobar.
- Aprobar usa mismo perfil estable y versión vigente; una oferta alternativa se elige expresamente por el flujo administrativo existente. Prohibir escoger una versión retirada como alternativa a la vigente de esa misma oferta.
- Token firmado actual (60 s) incluye revisión de pedido/perfil, definición/hash/artefactos, disponibilidad y capacidad. Bajo locks de capacidad y filas se recalcula antes de reservar. Si una publicación cambió la selección o requisitos, devolver 409 `evaluacion_desactualizada`, obtener nueva evaluación y pedir decisión administrativa; no pedir confirmación docente.
- En éxito, historial/decision_snapshot guardan ambas versiones y notificación segura al responsable. Persistir evento/outbox de notificación en la transacción de aprobación; reintentos no duplican decisión ni aviso. Fallo SMTP no revierte aprobación; política de preferencias/entrega existente se conserva y el cambio sigue visible en portal.
- Tras aprobar: asignación, imagen, receta, definición y recursos quedan congelados. Una publicación posterior no los modifica, incluso con fecha inicial futura. Despliegue sigue sujeto a fecha, reserva vigente, pool/red y verificaciones actuales.
- Renovación conserva versión/snapshot del servicio original. Vincular oferta a «Otro» conserva la descripción solicitada y la decisión administrativa. No introduce aprobación automática.

## Definiciones: búsqueda e incorporación

En `Definiciones.jsx`, añadir búsqueda de aplicaciones y ficha con comando de origen en sólo lectura, procedencia, datos disponibles/faltantes y compatibilidad. Diferenciar «sin coincidencias», «fuente inaccesible», cache desactualizada y «incorporada anteriormente». Buscar/incorporar nunca instala. Botón de preparación sólo con adaptador Draw.io y campos necesarios. Otras aplicaciones explican su limitación.

La ficha importada es editable sin exigir al administrador escribir un manifiesto JSON desde cero. La edición técnica avanzada existente se conserva para productos previos. Completar datos → iniciar ensayo con plazo visible → revisar entradas fijadas → construir y consultar estado → comprobar desde la red → validar y publicar oferta. Ninguna etapa aprueba la siguiente automáticamente.

## Estado, errores y accesibilidad

Mostrar progreso persistido con polling acotado (cada 5 s con pestaña visible, suspender al ocultar); recargar página recupera ensayo y trabajo activo. Cerrar navegador no cancela trabajo. Mostrar vencimiento/aviso, recursos pendientes de limpieza y botones de recuperación según estado servidor. Una publicación completada puede mostrar limpieza fallida sin volver a «no publicada».

Todo control con etiqueta, orden de foco y teclado; resultados/progreso con `role=status`, errores con `role=alert` y resumen ligado a campos. Deshabilitar doble envío y conservar misma Idempotency-Key tras respuesta perdida; usar otra clave sólo al cambiar intención/carga. Formularios mantienen valores válidos ante 409/422/502; llevar foco al resumen o campo inválido. No mostrar detalles de transporte, leases o scripts al responsable de cátedra.

## Criterios verificables

1. Draw.io aparece con los tres términos; incorpora un borrador único sin instalaciones y dentro de SC-001.
2. Ningún borrador incompleto o ensayo fallido produce opción docente; la publicación completa aparece en ambos puntos de entrada.
3. Dos responsables seleccionan el mismo perfil y reciben servicios aislados; ambos cumplen ciclo editable de SC-003.
4. Cambiar versión antes de aprobar usa la vigente y notifica; cambiar después conserva snapshot; carrera de publicación invalida evaluación anterior.
5. Fallo del proveedor no bloquea selección, aprobación ni despliegue desde artefacto retenido.
6. Flujo docente en menos de 3 minutos y administrativo de búsqueda/incorporación en menos de 2 minutos, medidos como tareas humanas; latencias técnicas se miden por separado.
