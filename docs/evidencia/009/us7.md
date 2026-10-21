# US7 — observación, interfaz y rendimiento

## Validación automatizada

Captura por minuto con calidad explícita, contadores BIGINT y deltas/épocas; límites de la misma muestra; salud falsa sólo tras un fallo funcional comprobado, transporte desconocido conserva null. GET ordinarios sólo leen DB. Captura duplicada concurrente probada en PostgreSQL, sin duplicar RPC. Inactividad usa siete días,80 % de intervalos conocidos, máximo CPU<5 %, tráfico<1MB y gracia48h; descarta huecos, reinicios y datos viejos. Apertura/restitución de incidentes produce un aviso lógico por destinatario/canal; incertidumbre no inventa caída ni recuperación. El correo fallido conserva su decisión/outbox y sólo expone diagnóstico seguro al admin.

Resumen diario conserva integrales y cobertura, cambios de asignación/cátedra e instantes de días DST; tráfico exacto aunque exceda BIGINT diario. Purga sólo detalle respaldado por resúmenes cerrados, conserva extremos y no convierte el legado desconocido en intervalos válidos. Migración009_11 preserva Float originales/duplicados y marca legado sin cobertura. Pruebas específicas aprobaron en SQLite y PostgreSQL aislados; no hubo envío de correo ni cambios de invitados reales en estas pruebas.

Registros recientes:44 pruebas de resúmenes/alertas/historia/orquestación/recuperación aprobadas;18 jobs/resúmenes aprobadas;25 API/captura aprobadas;6 PostgreSQL de leases/captura aprobadas. Tras las mejoras de filtros,14 guardas/API aprobadas(4,33s) y3 PostgreSQL de precisión/bordes del historial aprobadas(4,18s). La suite backend completa sigue reservada para T134; estos resultados no la sustituyen.

Frontend:37 Vitest aprobadas tras consultas/foco(11,03s). Dos recorridos Playwright de teclado y tres de métricas/formularios/chunks aprobaron en la SPA compilada con API sustituida; se repetirán las comprobaciones afectadas tras el cambio final del scroll. Diálogos compartidos tienen nombre, foco inicial/retorno, Tab contenido, fondo inerte y guardas de formulario ocupado. Consultas independientes conservan el último éxito, muestran error/reintento y cancelan respuestas de alcances anteriores. [Bundle y comprobaciones](frontend-rendimiento.md).

## Rendimiento SC-008

[Laboratorio y protocolo](rendimiento-laboratorio.md). PostgreSQL dedicado con100servicios y12.960.000 muestras, diez contextos autenticados(5docentes/5admins),150 calentamientos excluidos y300 mediciones repartidas por igual. API y SQL reales, PVE/runner simulados; el despliegue se admite por202 real, queda pendiente durante las mediciones y se confirma al cierre. Se preserva el fallo completo previo en [rendimiento-navegador-antes.json](rendimiento-navegador-antes.json): p95 Pedidos1,70s, Servicios2,22s y Métricas4,40s. Métricas incumplió; no se aceptó ese ensayo.

La corrección usa búsquedas indexadas por bloque para seleccionar observaciones reales de noventa días, sin ordenar todas las filas por petición. Un intento de comprobación del scroll se interrumpió y quedó [registrado como incompleto](rendimiento-interrumpido.json); no cuenta para aceptación. El siguiente ensayo persiste cada muestra en un diario privado y comprueba visibilidad del resumen/gráficas en el viewport. El ensayo completo final aprobó SC-008 bajo las condiciones registradas: p95 Pedidos1567,9ms/100 % válidas<=3s, Servicios2747,2ms/98 % y Métricas2472,3ms/100 %. Se verificaron150calentamientos excluidos+300medidas, reparto por contexto, diario, operación pendiente y confirmación final a51,31s. [Muestras/fuentes/recursos](rendimiento-navegador.json) y [HTTP/DB separado](rendimiento-diagnostico.json). Las mejoras no convierten este ensayo de transportes simulados en aceptación PVE real.

## Validación con el responsable de cátedra — pendiente

Por indicación del usuario del 2026-10-21 se valida con un único responsable de cátedra; se retiró la muestra de cinco personas. El plan de trabajo individual pide feedback de uso simulado de una cátedra de prueba, sin fijar cinco participantes. El umbral de tiempo se conserva como criterio propio de SC-007. Esta hoja está preparada; todavía no se registraron resultados ni tiempos. No inferirlos de Playwright. Hace falta un entorno de demostración con la cuenta del responsable y catálogo preparado, separado del fixture medido. El responsable recibe sólo la consigna; no una explicación del desarrollador durante la tarea. El observador anota intentos, errores, ayuda y tiempos con un reloj monotónico. No registrar contraseñas ni nombres personales en esta evidencia.

Consigna docente: «Pedí un servicio para tu materia indicando para qué lo necesitás y sus fechas. Después comprobá que el pedido quedó registrado y encontrá su estado». Iniciar el tiempo al comenzar el formulario; detener al confirmar envío. Registrar aparte el tiempo para encontrar su estado. Excluir decisión administrativa y espera externa; incluir correcciones de formulario. Éxito SC-007: el responsable envía y consulta sin ayuda, formulario<=180s. Si hay ayuda, no contar como éxito aunque finalmente complete.

| Participante | Formulario(s) | Envió | Consultó estado | Sin ayuda | Problema observado |
|---|---:|---|---|---|---|
| Responsable de cátedra | pendiente | pendiente | pendiente | pendiente | pendiente |

Consigna administración, con cuenta autorizada: «Revisá un pedido, cambiá justificadamente su asignación y confirmá la decisión. Encontrá lo finalmente aprobado y su vigencia». Anotar si hay bloqueo de validación, pérdida de datos o campos sin explicación; repetir tras corregir los problemas.

SC-010 requiere además repaso de teclado de solicitud/aprobación/seguridad/métricas/acceso, errores identificables y retorno de foco en todos los pasos. Las comprobaciones automatizadas focalizadas son evidencia parcial; el repaso completo forma parte del cierre T119/T134. T119 permanece abierta por estas pruebas y la validación del responsable, aunque el ensayo de carga llegue a aprobar.
