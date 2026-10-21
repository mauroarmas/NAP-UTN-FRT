# Esquema final — T126

Implementación y pruebas aisladas del 2026-10-21. No se aplicó la revisión a la base operativa, al laboratorio 55433 ni al volumen de carga 55434.

`009_13_cierre_constraints` retira usuarios.totp_secret, servicios.credenciales_acceso y los cuatro campos pedidos.reserva_*. Primero exige ausencia de secretos pendientes de cuarentena y valida restricciones; bloquea tablas y limita a cinco segundos la espera del bloqueo. Un fallo cancela la migración sin borrar filas. No hay downgrade destructivo: requiere copia verificada y versión compatible para volver atrás.

El operador debe ejecutar primero preflight/backfill sobre una copia. El adaptador de legado lee columnas antiguas por introspección únicamente durante estas intervenciones o la revisión administrativa. Están fuera del modelo operativo y no tienen doble escritura. La cuarentena se cifra y se comprueba antes de limpiar; el backfill conserva compatibilidad con la revisión aditiva anterior y con el esquema final sin esas columnas.

Las cantidades históricas positivas sin snapshot se conservan como snapshot parcial de origen legado. La bitácora guarda los valores y caducidad retirados, incluidos datos no aptos para una asignación nueva. Este traslado no autoriza capacidad, no crea ledger y no deduce definición, propiedad ni fechas. Se conserva el estado ERROR/EN_DESPLIEGUE y los VMID históricos duplicados para revisión. La unicidad operativa por clúster/VMID vive en identidades retenidas; compromisos, operaciones, vigencias e historia mantienen los únicos parciales/FK de las revisiones aditivas.

Se añaden CHECK de recursos positivos en perfiles/servicios, revisiones y coherencia tipo/servicio del pedido, modelo y disponibilidad de aplicación. No hay límite artificial de disco: 200 GiB continúa válido. El saldo y caducidad pertenecen al ledger; `compromiso_capacidad` en la API es una proyección de esa autoridad. Administración sigue viendo asignación autorizada y vencimiento comprobado, sin depender de los campos retirados. Nuevos inicios/reinicios también exigen nombre/modelo históricos regularizados.

Comprobaciones:

- Siete pruebas PostgreSQL de migración/concurrencia aprobadas en 11,88 s: fresh/upgrade, MFA preservado, dos sesiones de decisión/backfill.
- Siete pruebas PostgreSQL de migración/read-only aprobadas en 14,02 s, incluyendo rechazo por secreto pendiente, backfill real con columnas antiguas, cuarentena descifrable y retiro posterior. Se comparan las columnas finales de usuarios/pedidos/servicios/perfiles con los modelos.
- 37 pruebas backend de regularización/backfill/inicio/vigencia/auth aprobadas en 29,60 s.
- 37 pruebas de autoridad de compromiso/liberación/evaluación/proyecciones/preflight aprobadas en 13,16 s. El primer ensayo detectó una expectativa del contador retirado y un reenvío antiguo sin vigencia; se actualizaron las pruebas al snapshot conservado y al contrato obligatorio.
- 25 pruebas finales de autoridad/preflight aprobadas en 4,39 s; 19 de guardas/regularización/inicio/proyecciones aprobadas en 13,51 s tras exigir también nombre/modelo históricos.
- Diez pruebas Vitest de formularios y regularización aprobadas en 8,07 s. Las suites completas y una nueva medición SC-008 con la proyección de compromiso corresponden a T134.

T120 ya pasa. T121 sigue a la espera de T130; estos resultados no acreditan restauración ni aceptación real de infraestructura.
