# US8 — migración conservadora del legado

La revisión aditiva `009_12_bitacora_cierre` incorpora una bitácora inmutable con actor/referencia, hashes de estado anterior/posterior, acciones, pendientes y cuarentena cifrada. No altera registros heredados al aplicarse. La migración final de restricciones será una revisión posterior.

`backend/scripts/backfill_cierre_009.py` primero genera un plan privado0600 sin cambios. Incluye registros/estado seguro, acciones, pendientes y retención propuesta cuando la propiedad pudo comprobarse. `--aplicar` exige el archivo revisado, su SHA canónico, operador y referencia de una copia comprobada. Relee los datos bajo el lock común de capacidad y bloqueos de fila; si cambian el registro, identidad, acciones aplicables o retención observada, rechaza el plan. No ejecutar contra la base de demostración predeterminada. El procedimiento se ensaya sobre copia con API/worker detenidos antes de la actualización operativa.

```bash
# Con configuración explícita de la copia y keyring externo ya instalado:
backend/venv/bin/python backend/scripts/backfill_cierre_009.py --plan /directorio/privado/plan.json
# --sondear es optativo: consulta inventario PVE, nunca modifica invitados.
# Después de revisar el plan y conservar la copia:
backend/venv/bin/python backend/scripts/backfill_cierre_009.py --plan /directorio/privado/plan.json \
  --aplicar --sha256 SHA_DEL_PLAN --operador OPERADOR --referencia REFERENCIA_DEL_CORTE
```

El material de `credenciales_acceso` anterior pasa a cuarentena cifrada y se comprueba su descifrado antes de limpiar el origen. No se convierte en credenciales entregables ni se comunica acceso verificado. El factor TOTP confirmado se conserva cifrado; si su material es inválido, permanece activado y se marca recuperación necesaria. Nunca se desactiva MFA por conveniencia de migración. La bitácora no revela secretos, y preflight comprueba también sus versiones de keyring/contexto.

Las cantidades autorizadas conservadas del pedido pueden generar un snapshot histórico parcial con origen explícito. No se copia una plantilla actualmente editable ni se inventa versión de producto/imagen. Una asignación o vigencia completas sólo se recuperan de una decisión congelada y su evento de aprobación coincidente, con revisión, actor y fechas UTC/locales coherentes. Las fechas académicas incompletas permanecen pendientes; `deployed_at` no determina su duración. Los timestamps técnicos conocidos se expresan como UTC en la bitácora. No se deduce un período por semestre,180d u otro valor por defecto.

Un ledger faltante sólo se crea si ya existe identidad ligada al mismo servicio y el inventario actual verifica marca/nonce/pool/clúster/VMID/nodo y destino de almacenamiento. Se retienen cantidades conservadoras en estado incierto; no se libera capacidad, inventa un UUID, completa hashes históricos, cambia EN_DESPLIEGUE/ERROR ni crea invitados. Duplicados y recursos sin prueba quedan pendientes. Repetir sobre el estado ya procesado no duplica bitácoras; sigue informando sus pendientes. Un plan anterior a cambios debe regenerarse y revisarse.

Validación:9 pruebas de backfill aprobadas en4,75s; cinco comprobaciones PostgreSQL de migración fresh/upgrade, READ ONLY y dos sesiones concurrentes aprobadas en5,78s. La carrera real permite una sola migración y cuarentena; la otra sesión recibe conflicto de plan desactualizado. La prueba de recuperación de período falló antes de implementar ese comportamiento y luego aprobó; conserva exactamente el intervalo aprobado. Sólo se ejecutó sobre SQLite y esquemas PostgreSQL aislados. Ningún backfill se aplicó a la DB operativa ni al clúster real.

Pendiente: la regularización administrativa explícita de fechas, asignación y conflictos de propiedad en T125; restricciones/retirada de columnas en T126; el bloqueo de restauración y la reconciliación de copias en T130. Esta bitácora no acredita restauración ni habilita una instancia por sí sola.
