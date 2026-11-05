# Convergencia 009 — revisión del 25 de octubre de 2026

Esta ejecución implementa T139–T146. No se conecta a PVE/SSH/SMTP reales ni altera la base operativa. Los datos de pruebas viven en SQLite en memoria y PostgreSQL 16 temporal por esquema. El contenedor PostgreSQL de pruebas usa el proyecto `nap009-tests`, separado del portal.

## Cambios y alcance

- Gate de consola enlazado a evidencia real tipada, integridad, instalación/clúster/versión, trámite completado e identidades/scopes con revisiones. Un archivo local o evidencia genérica no abre la consola. Pruebas sintéticas de declaraciones no acreditan ACL nativas reales.
- Retiro de `pedido_service.cambiar_estado` para impedir aprobación sin admisión y cancelación docente interna. Las rutas nombradas conservan controles transaccionales.
- Pausa/reactivación de pedido sólo tras efecto confirmado; cierre de ERROR sólo con ausencia reconciliada o operación nunca enviada, sin efectos/compromisos abiertos.
- Pool de UUID/DNS/TLS/DHCP preautorizados: reserva bajo lock antes de crear, snapshot persistido y MAC incluida en `net0`. Dos despliegues por PostgreSQL/BookStack con dobles no comparten destino ni contraseñas. No se agregan DNS/IPAM/CA automáticos ni se reutilizan identidades históricas.
- Avisos de vencimiento mediante outbox en la transacción del evento, con destinatarios/plazo efectivo, deduplicación y entrega SMTP fuera de HTTP.
- Retiro del publicador específico del laboratorio. El CLI sólo comprueba coherencia de manifiesto/evidencia explícitos y no publica ni muta usuarios.
- Manuales y contrato de conexión corregidos contra el software. La revisión por una persona ajena al desarrollo permanece pendiente junto a T119.
- Matriz/enlaces/acta distinguen referencias históricas, simulación, implementación y aceptación institucional pendiente.

## Verificación

Se reprodujeron y cerraron los fallos de aprobación aislada, gate por archivo, pedido sin transición y aviso sin outbox. La comprobación final detectó además que un stop/start borraba la entrega acreditada; ahora se conserva mientras la preparación sea la misma, y una preparación nueva sigue exigiendo prueba de red.

| Verificación | Resultado de esta ejecución | Alcance |
|---|---|---|
| Backend completo SQLite/dobles | 688 aprobadas, 451,60 s | Corrida general previa al último ajuste de conservación de entrega. |
| Backend afectado, repetición final | 93 aprobadas, 74,93 s | Seguridad (incluye una parametrización nueva de simulación), operaciones, preparación, entrega, vigencias, inactividad, ciclo docente y reactivación; después del ajuste final. |
| Pool/preparación de aplicaciones, repetición final | 3 aprobadas, 4,01 s | Dos PostgreSQL y dos BookStack con doble, fallo del runner/reintento sin cambiar identidad/cifrado y un solo create por instancia. |
| PostgreSQL 16, suite existente | 99 aprobadas, 199,75 s | Esquemas efímeros, migraciones y carreras, sin base operativa. |
| PostgreSQL, regresiones nuevas | 2 aprobadas, 5,46 s | Reservas de pool concurrentes y avisos concurrentes sin duplicación. |
| PostgreSQL afectado, repetición final | 11 aprobadas, 15,71 s | Worker/renovación y las dos regresiones nuevas, después del ajuste final. No sumar otra vez estos casos al total anterior. |
| Infraestructura | 130 aprobadas, 4 omitidas optativas, 9,61 s | Runner/servicios/laboratorio; no PVE/SMTP reales. |
| Vitest | 41 aprobadas, 26,45 s | Diez archivos de componentes. |
| Playwright Chromium | 21 aprobadas, 49,4 s | SPA compilada y recorridos con respuestas de prueba, sin aceptación institucional. |
| Contratos JSON | 2 schemas y 13 ejemplos válidos | Draft 2020-12; schema de evidencia runtime/contrato coherente. |
| Lint | 0 errores, 8 advertencias existentes | Sin cambiar reglas para ocultar advertencias. |
| Guías/CLI | Enlaces locales correctos; `--help` de bootstrap/preflight/comprobador contrastado | No sustituye lectura por una persona ajena al desarrollo. |

Los logs de ejecución locales están en `/tmp/nap009-convergencia-*.log`; son auxiliares efímeros, no rutas necesarias para operar o reproducir el despliegue. No se suman las repeticiones de tests como si fueran casos distintos. Las suites conservan advertencias de compatibilidad/deprecación; no se presenta una corrida sin errores como ausencia de advertencias.


No se repitió SC-008 con 12,96M muestras. Su archivo histórico identifica el código/entorno medido; no se atribuye el rendimiento de esa ejecución a esta revisión ni al clúster universitario. Las herramientas de auditoría de dependencias tampoco se volvieron a consultar: se conserva su evidencia histórica sin afirmar ausencia actual de vulnerabilidades.

## Pendientes de aceptación

- T102: aplicaciones/consola y aislamiento real desde otra computadora.
- T119: recorrido sin ayuda del responsable de una cátedra y feedback, incluida revisión de los manuales corregidos.
- T131: restore completo y separado de portal+keyring y aplicaciones, comparando datos/cuentas/permisos y RTO/RPO observado. La evidencia de control de restauración no equivale a esa prueba.
- T133: recorrido institucional con ambos roles, red, SMTP y evidencias de aceptación.

T101 tiene ensayos declarados en la VM local; no acredita el clúster universitario ni configura automáticamente el nuevo gate. Mantener consola cerrada mientras falte evidencia aplicable a la instalación receptora.

## Estado de tareas y hooks

T139–T144 y T146 marcadas completadas. T145 conserva pendiente sólo el recorrido del manual por un lector ajeno al desarrollo. Junto a T102/T119/T131/T133 quedan cinco tareas abiertas de 146; las 134 marcadas del bloque original se conservaron. No se ejecutaron commits ni despliegues operativos. `.specify/extensions.yml` no existe: sin hooks before/after_implement que despachar. El contenedor/esquemas PostgreSQL de prueba se retiraron al terminar.
