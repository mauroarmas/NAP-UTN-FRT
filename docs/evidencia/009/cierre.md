# Estado de cierre de la spec 009

Corte: 25 de octubre de 2026. La entrega integral **no está aceptada**: falta el entorno universitario y las comprobaciones humanas/externas. Ver [convergencia](convergencia.md) y [matriz de trazabilidad](matriz-trazabilidad.md).

La lista original contiene 138 tareas: 134 marcadas y cuatro abiertas (T102, T119, T131, T133). T101 está marcada por ensayos declarados de la VM local; no se considera acreditada la instalación universitaria. La fase 12 agrega ocho tareas T139–T146 para corregir las brechas encontradas. Se completaron siete de las ocho tareas nuevas; T145 conserva pendiente la lectura externa de los manuales. El total actual es 141 marcadas y cinco abiertas de 146. El estado ejecutable vigente está en [tasks.md](../../../specs/009-remediar-hallazgos-cierre/tasks.md), sin inferir completitud por un porcentaje histórico.

| Historia | Implementación / comprobación local | Aceptación restante |
|---|---|---|
| US1 — aislamiento | Guards y trámite duradero; nuevo gate de consola exige evidencia e identidad aplicables a la instalación. | ACL, consola abierta/URL previa y pools legítimos reales: T102/T133. |
| US2 — acceso | Sesiones por propósito, cambio inicial, MFA voluntario, códigos y asistencia; pruebas aisladas. | Comprobación de uso según instalación; no se promete desactivar MFA por asistencia. |
| US3 — capacidad | Admisión/ledger y concurrencia; fachada genérica retirada también dentro de servicios. | Inventario y permisos del clúster receptor por comprobar. |
| US4 — recuperación | Operaciones duraderas con fallo/reinicio; pausa/reactivación del pedido al confirmar y cierre ERROR seguro. | Recorrido institucional y revisión de fallos externos: T133. |
| US5 — fechas | Calendario configurable, snapshots, reserva futura y receso con dobles/reloj controlado. | Persistencia/servicios reales del escenario final. |
| US6 — productos | Recetas y runner; pool de red preparado en lote, dos instancias por aplicación con dobles y secretos distintos. | Publicación/despliegue cotidianos desde otra computadora y pruebas funcionales: T102. |
| US7 — observación/UI | Intervalos, incidentes, outbox de vencimiento, accesibilidad y recorridos automatizados. | Responsable de una cátedra sin ayuda, <=3min y feedback: T119. SC-008 tiene una medición histórica, no se repitió para esta revisión. |
| US8 — operación/entrega | Migraciones, controles de restauración, configuración externa y guías corregidas. | Restore completo separado T131; red/SMTP/recorrido institucional T133; revisión de manuales por lector externo T145/T119. |

## Evidencias existentes y límites

- [Convergencia del 25/10](convergencia.md): cambios, regresiones actuales y límites.
- [Regresión histórica](regresion-cierre.md): ejecución registrada anteriormente y sus adaptaciones; no es el resultado automático de esta revisión.
- [Preparación de servicios](preparacion-servicios.md) y archivos de staging: laboratorio local; no habilitan por sí mismos el gate del clúster receptor.
- [Producción aislada](produccion.md): ensayo Docker/HTTPS sin integración real PVE/SMTP.
- [Control de restauración](restauracion-control.md): revocación/bloqueo/reconciliación sobre copia de prueba. No acredita una restauración completa con pg_dump/pg_restore y contenido de aplicaciones.
- [Dependencias](dependencias.md): auditoría histórica; no se volvió a consultar advisories en esta revisión.
- [Rendimiento de navegador](rendimiento-navegador.json): ejecución del laboratorio del 21/10 con fuentes/recursos identificados. Sus valores no se mezclan con otros resultados ni se atribuyen al entorno universitario.

No existen las antiguas evidencias llamadas `migracion-respaldo.md`, `dependencias-seguridad.md` ni `rendimiento-api.json`. Se corrigieron sus enlaces y las afirmaciones que dependían de ellas; no se recrean archivos con resultados supuestos.

## Condiciones de entrega

Infraestructura debe entregar configuración/artefactos conforme a [conexion-infraestructura.md](../../conexion-infraestructura.md), además de destino/custodia de respaldos. El software conserva gates y diagnósticos; conectar el clúster no sustituye validar TLS, permisos, red de alumno, consola, SMTP y restauración.

BookStack sigue siendo referencia provisional del libro virtual. No hay alumnos dentro de NAP, nueva oferta QEMU, cuotas fijas por cátedra ni módulo del portal para administrar respaldos de aplicaciones. La revisión por una persona ajena al desarrollo y el responsable de cátedra se coordina para aceptación; no se sustituye por los tests.
