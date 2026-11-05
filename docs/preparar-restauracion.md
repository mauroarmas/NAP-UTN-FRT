# Preparación de una copia restaurada

Este procedimiento corresponde a T130. No descarga ni restaura dumps, no crea cuentas y no administra respaldos desde el portal. El conjunto externo y la prueba completa de las tres aplicaciones siguen pendientes de T131. Ejecutar sólo sobre una copia aislada, con autorización y referencia de corte; conservar el origen.

## Aislamiento previo

1. Restaurar base y volúmenes en un destino separado con la versión correspondiente. Recuperar el keyring completo, JWT/CSRF y configuración del corte. Detener API, worker, outbox y cualquier otro escritor de esa copia; bloquear SMTP y mutaciones PVE en la red/cuenta de ensayo. No dejar un worker anterior a la restauración ejecutándose.
2. Crear un archivo privado propio 0600 para la copia, mediante el formato de `NAP_SETTINGS_FILE`. Cambiar `database_url` a la base separada y asignar **una nueva** `restauracion_referencia` por cada restauración. Usar esa misma referencia en runtime, release y CLI. No reutilizar la referencia de una recuperación ya habilitada.
3. Aplicar migraciones explícitas y permisos de release sobre la copia. `009_14_restauracion` crea controles independientes; no modifica cuentas ni supone que una migración equivale a preparar la restauración. API/worker con una referencia externa no habilitada rechazan el arranque; login, autenticación, scheduler, claim de operaciones y outbox también consultan el bloqueo.

La base no puede detectar por sí sola que fue copiada. La referencia externa nueva y el aislamiento se configuran **antes del primer arranque**. Nunca arrancar una copia conservando sin revisión la configuración operativa del origen.

## Inspeccionar y preparar

Ejemplos con nombres de copia ficticios, sin contraseñas ni DSN en argumentos. `NAP_SETTINGS_FILE` contiene sólo la ruta del archivo privado:

```bash
export NAP_SETTINGS_FILE=/ruta/privada/copia.json
cd backend
venv/bin/python scripts/preparar_restauracion.py \
  --base-copia nap_recuperacion --referencia CORTE-RECUPERADO-001
```

El modo anterior no cambia datos. Comprueba base explícita, revisión de esquema y descifrado; muestra cantidades y acciones pendientes. Revisar el informe y el aislamiento. Para preparar:

```bash
venv/bin/python scripts/preparar_restauracion.py \
  --base-copia nap_recuperacion --referencia CORTE-RECUPERADO-001 \
  --operador OPERADOR-AUTORIZADO --aplicar
```

Preparar el mismo corte pendiente es idempotente y no vuelve a incrementar versiones. Otra referencia mientras hay un corte pendiente, o reutilizar una referencia ya habilitada, se rechaza. Un keyring ausente o que no abre cualquier secreto del corte aborta antes de cambiar credenciales.

La transacción incrementa versiones de autenticación y generación de recuperación, revoca SID, desafíos y códigos recuperados, elimina secretos de inscripción pendientes y cancela todo correo antiguo pendiente/fallido/en envío. Borra secretos temporales del outbox y anula sus leases. Conserva hashes de contraseña, factores MFA activos, datos de servicio e historia. El contador TOTP avanza más allá de la ventana del corte: un factor activo puede necesitar esperar hasta dos pasos de 30 segundos antes de aceptar un código nuevo. No se desactiva ni se obliga a habilitar 2FA.

Las cuentas que estaban cambiando su contraseña inicial quedan con entrega pendiente: una contraseña temporal recuperada no permite login. Un administrador habilitado puede restablecerla desde la gestión de usuarios; la contraseña nueva debe ser distinta. Si es la única cuenta administradora, un operador con identidad comprobada puede reemitir **esa cuenta existente** en su terminal privada:

```bash
venv/bin/python scripts/preparar_restauracion.py \
  --base-copia nap_recuperacion --referencia CORTE-RECUPERADO-001 \
  --operador OPERADOR-AUTORIZADO --aplicar --reemitir-inicial 17 \
  --referencia-identidad ACTA-IDENTIDAD-001
```

Pide la nueva contraseña dos veces mediante entrada oculta; no la imprime, no la recibe por argumentos ni reenvía correos del corte. Entregarla por el canal institucional. Preserva el segundo factor: si también se perdió, usar el procedimiento de recuperación asistida existente, con identidad comprobada. No recrear un administrador predeterminado.

## Reconciliar y conservar incertidumbre

Generar un informe nuevo privado de sólo lectura. Este paso sí realiza consultas PVE acotadas; habilitar exclusivamente las lecturas necesarias desde el entorno aislado:

```bash
venv/bin/python scripts/preparar_restauracion.py \
  --base-copia nap_recuperacion --referencia CORTE-RECUPERADO-001 \
  --evaluar --salida /ruta/privada/reconciliacion-001.json
```

Comprueba configuración, datos, descifrado, ofertas/archivos, inventario y propiedad por UUID/nonce/pool/clúster. Compara asignación observada, volúmenes, ledger y vigencia de recursos encendidos. Un marcador NAP fuera del corte, ausencia/fallo de consulta, asignación diferente o capacidad retenida insuficiente bloquean la habilitación. No adopta por nombre/VMID, libera capacidad, crea invitados ni manda órdenes PVE.

Las operaciones abiertas recuperadas quedan `incierta/restauracion_pendiente`, con generación nueva, lease anulado, UPID/contexto conservados y capacidad sin liberar. El CLI no autoriza su reenvío ni declara su éxito. Si aparecen:

1. Revisar en el origen y en la historia PVE la referencia, UPID, hora y resultado terminal, junto con identidad/configuración/volúmenes reales y cualquier cambio posterior al corte. Contrastar también accesos nativos, que pueden haber cambiado fuera de la base recuperada.
2. Si el origen está disponible, reconciliar allí mediante el ejecutor normal y obtener un **nuevo corte sin operaciones abiertas**, detenido de forma coordinada. Volver a restaurarlo como una copia nueva, sin mezclar sus datos con la anterior.
3. Si no hay origen o el resultado no puede probarse, conservar la copia bloqueada y escalar al responsable para una corrección específica revisada con evidencia. Este CLI no incluye una corrección genérica de historia incierta ni una opción de forzar la habilitación. Un ensayo con esos pendientes no cumple T131.

El informe apto es necesario pero no prueba que PostgreSQL/BookStack recuperaron datos, imágenes, adjuntos y permisos. Completar las comprobaciones de datos/keyring y de ambas aplicaciones en el entorno separado descrito en [operacion-respaldos.md](operacion-respaldos.md). `portal_keyring` atestigua datos/descifrado y revocación del corte, sin afirmar que ya se completó login del portal bloqueado. Tras habilitar el control, arrancar la API **todavía aislada de visitantes**, probar autenticación, MFA conservado, nuevas sesiones y revocación del acceso previo; sólo después decidir la apertura operativa. Mantener worker/SMTP reales detenidos durante el ensayo. No utilizar el CLI de habilitación para eludir la evidencia o abrir el servicio antes de la revisión final.

## Habilitación explícita

Conservar una atestación JSON propia 0600, respaldada por el informe/evidencia de ese ensayo. Campos cerrados:

```json
{
  "restauracion_id": "UUID-DEL-INFORME",
  "referencia_corte": "CORTE-RECUPERADO-001",
  "referencia_ensayo": "ENSAYO-SEPARADO-001",
  "entorno": "real",
  "estado_sha256": "SHA256-DEL-INFORME-RECIENTE",
  "conjunto_sha256": "SHA256-DEL-CONJUNTO-RECUPERADO",
  "inicio_at": "2026-10-21T12:00:00Z",
  "fin_at": "2026-10-21T12:30:00Z",
  "portal_keyring": true,
  "postgresql_dato": true,
  "bookstack_libro_imagen_adjunto_cuentas_permisos": true,
  "inventario_operaciones_capacidad_acceso_reconciliados": true
}
```

Son marcadores de ejemplo, no una atestación válida. Sustituir UUID, hashes y tiempos **observados**, con comienzo posterior a la preparación y fin no futuro. Es una declaración de un operador autorizado respaldada por evidencia revisada; el código no fabrica ni certifica el ensayo de aplicaciones. `simulado` sólo se admite en entornos no operativos.

Calcular el SHA canónico del JSON revisado en una terminal privada (JSON con claves ordenadas, UTF-8, `ensure_ascii=False`, separadores `,`/`:` y sin valores no finitos), sin imprimir su contenido. Conservar ese SHA en el acta; el CLI exige coincidencia:

```bash
venv/bin/python scripts/preparar_restauracion.py \
  --base-copia nap_recuperacion --referencia CORTE-RECUPERADO-001 \
  --operador OPERADOR-AUTORIZADO --aplicar --habilitar \
  --prueba /ruta/privada/ensayo-001.json --sha256 SHA256-CANONICO-REVISADO
```

Antes de habilitar vuelve a realizar todas las lecturas y compara el hash del estado relevante/configuración/inventario con el informe. Cambios de cuentas, asignaciones, claves o recursos exigen nuevo informe y revisión. Guarda actor, fecha, referencia del ensayo y hash de la atestación. El rol runtime no puede escribir `restauraciones`; la habilitación requiere el rol de mantenimiento autorizado.

Finalmente revisar permisos runtime tras la migración, arrancar API, comprobar ingreso nuevo y MFA cuando corresponda; reanudar worker/outbox sólo cuando operación autorice el retorno. No se reenvían correos anteriores: los avisos nuevos nacen de eventos nuevos. Conservar las evidencias/RPO/RTO y la copia original hasta aceptar el retorno.
