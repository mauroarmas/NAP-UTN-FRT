# Remediación del análisis de consistencia

Fecha: 2026-10-18. Cambios de diseño autorizados después de speckit-analyze. Esta revisión actualiza los artefactos; la implementación y la aceptación real siguen pendientes.

| Hallazgo | Corrección incorporada | Trabajo y comprobación previstos |
|---|---|---|
| C1 · Permisos contrarios a la constitución | Corregir/reenviar/cancelar pedidos requiere admin, también sobre pedidos propios. Docente crea/consulta, solicita renovación y opera sus servicios. Spec, plan, API y UI alineados. | T021, T025, T073, T080: denegación docente por HTTP y UI; admin autorizado. |
| G1 · Sesiones nativas de consola tras retirar permisos | Trámite duradero: bloqueo preventivo, revocación institucional de permisos efectivos y sesiones, evidencia y cambio efectivo posterior; fallo conserva pendiente sin transferencia. | T022, T026, T027, T038; T101–T102 acreditan consola abierta/URL guardada denegadas y otros pools conservados en infraestructura real. |
| A1 · Referencias de evidencia sin interfaz de ingreso | Registro admin POST/GET /evidencias, schema cerrado de tres tipos, JSON canónico inmutable, UUID/checksum y relaciones del modelo; consumidores comprueban identidad/revisión/entorno. | T010, T018, T086, T087, T089, T097, T099. Productores y casos de rechazo en [contrato](../contracts/evidence.md). |
| I1 · Rendimiento medido solo en API | Medición en navegador de tres recorridos hasta resultado visible/utilizable; diez contextos, datos completos, despliegue lento, muestras por flujo y fallos incluidos. | T117–T119 y [protocolo SC-008](../quickstart.md). HTTP se conserva como diagnóstico. |
| G2 · Suites infra fuera de recolección | Configuración y fixtures infra propios, comando explícito, job CI y cierre que exigen ambas suites con recolección no vacía. | T005, T007, T085, T089, T134. No se presupone que backend/pytest.ini recolecte infra. |

[Tareas actualizadas](../tasks.md): 138 pendientes (seis añadidas), IDs únicos y consecutivos; dependencias explícitas hacia tareas anteriores; 73/73 FR y 17/17 SC con cobertura, y las 138 tareas mapeadas. Las marcas pendientes se conservan: preparar este documento no completa ninguna tarea de implementación.

Se comprobaron enlaces locales, sintaxis de ejemplos y schemas JSON, referencias internas/patrones de schemas, numeración, cantidades, cobertura y dependencias. La constitución conserva el mismo contenido que al comenzar esta remediación. La metavalidación completa Draft 2020-12 queda para el check con jsonschema previsto en implementación: esa dependencia no está instalada en este entorno.

No se ejecutaron suites de aplicación, ensayos de rendimiento ni pruebas reales de red/Proxmox durante esta edición documental. Los nuevos contratos de [evidencias](../contracts/evidence.md) y [consola](../contracts/console-access.md), junto con [plan](../plan.md), [modelo](../data-model.md) y [quickstart](../quickstart.md), describen cómo implementarlos y acreditarlos.
