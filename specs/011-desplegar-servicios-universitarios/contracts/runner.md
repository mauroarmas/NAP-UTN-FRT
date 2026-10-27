# Protocolo de trabajos `nap-application-job/1`

Nueva rama del dispatcher de SSH forzado; conservar intactos `nap-guest-runner/1` y build-runner.
No hay servidor shell general ni comandos del navegador. La cuenta dedicada sólo invoca el wrapper
fijo validado por root. Requests/responses JSON estrictos por stdin/stdout, límites explícitos,
hostkey fijada y destino institucional; errores de protocolo devuelven códigos seguros.

## Acciones

| Acción | Efecto |
|---|---|
| profiles | Capacidades/revisiones habilitadas y motivo seguro de bloqueo; sin secretos |
| start | Admite un trabajo nuevo o devuelve el mismo execution_id ya existente |
| status | Estado durable, fase, identidad, fingerprint, boot_id y resultado seguro |
| read | Status y fragmentos depurados posteriores al cursor, hasta 64 KiB |
| ack | Confirma cursor ya almacenado por el portal y permite purgar spool |

No aceptar shell, argv, rutas libres, unit names, URLs de código o flags Docker/PVE externos.
No hay escritura de consola ni cancelación por desconectar al lector.

## Identidad y fencing

Toda acción sobre un recurso incluye: protocol, operation_id, operacion_raiz_id, intento_id,
execution_id, lease_generation, cluster_uuid, node, VMID, resource_uuid, pool, nonce de propiedad,
configuracion_sha256 y perfil con revisión/hash. El wrapper valida formato, perfil registrado,
marcador JSON exacto del LXC, destino, recurso y relación del trabajo antes/después de efectos.
El nonce original sólo pertenece al request privado. Las respuestas y los manifiestos
incluyen `nonce_sha256` en su lugar; nunca devuelven el secreto de propiedad.

`start` añade la configuración aprobada y, por canal privado, sus secretos efectivos. El hash del
trabajo incluye configuración no sensible y referencias/versiones de secretos; no se registran
valores ni hashes simples de contraseñas de baja entropía. Mismo execution_id/mismo fingerprint
es replay del mismo trabajo; contenido distinto devuelve conflicto. Una generación de controlador
menor a la aceptada se rechaza. Un cambio de lease no vuelve a ejecutar ni mata el trabajo existente.

Per-resource lock para admisión y transiciones de efecto; no mantener un flock que impida leer
status durante toda la instalación. Estados/manifest/tombstone privados se escriben atómicamente,
con rutas derivadas sólo de UUID validados y sin seguir symlinks. Conservar tombstone aunque se
purgue el texto para que un request antiguo no produzca un efecto nuevo.

## Ejecución duradera

1. El portal persiste operación, intento, execution_id, snapshot y cabecera de consola antes de
   crear el CT. Registra los hitos seguros de creación aunque falle antes de enviar `start`.
2. El nodo verifica pertenencia, perfil/base, red y fingerprint; persiste el manifiesto del trabajo.
3. Arranca una unidad systemd de nombre derivado del UUID, ejecutable fijo y `Type=exec`, sin PTY,
   `--pipe` ni `--wait`. Entrada no interactiva; no poner secretos en argumentos, descripción o
   propiedades de unidad. Credenciales por archivo efímero privado en `/run` y mecanismo de
   credenciales del servicio, retirando el origen tras su carga. No guardarlas en el spool.
4. La unidad conduce el trabajo aunque termine SSH/worker/pestaña. Configurar stdout/stderr para
   pasar por el colector seguro, nunca por journal o un archivo crudo como efecto por defecto.
5. El resultado durable se escribe antes de la finalización de unidad. `exit 0` es una observación,
   no entrega del pedido. El portal comprueba recurso, configuración y disponibilidad después.
6. Nodo reiniciado/unidad desaparecida sin resultado probado: `incierto`; reconciliar antes de otro
   intento. No usar `Restart=always` para reinstalar ni identificar trabajo sólo por PID.

Presupuesto inicial de instalación: 45 minutos, configurado en el perfil institucional. Su
vencimiento produce resultado explícito y reconciliación; no borra el LXC ni libera ledger por
sí mismo. Es un watchdog de operación, no vencimiento de oferta ni ensayo de servicio.

## Creación y etapas

La orquestación de NAP crea exactamente un CT con `start=0` y su marcador. El wrapper no ejecuta
el wrapper host de Community Scripts. Antes de iniciar se verifica firewall/red y, para Docker,
una acción interna fija establece sólo `nesting=1,keyctl=1` del perfil aprobado sobre el CT detenido.
No se amplía el token API a root ni se aceptan features provenientes de campos de usuario.

Etapas comunes: preparar → crear recurso → habilitar entorno → descargar/instalar → configurar →
arrancar → comprobar. Los caminos históricos conservan sus fases; la API publica una descripción
normalizada y etapas confirmadas, no un porcentaje temporal inventado.

- Docker: verificar daemon/perfil; pull por digest con credencial efímera; crear volúmenes propios y
  container etiquetado con identidad/configuración; quitar credenciales de registry; arrancar y
  comprobar. Mantener ENTRYPOINT/CMD, sin comandos libres o HEALTHCHECK que retenga salida insegura.
- Community: ejecutar instalador guest/paquete Core/harness comprobados; respuestas cerradas,
  dependencias fijadas y configuración final de acceso tipada. No cargar código del backend host.
- Reinicio del mismo servicio: inspeccionar LXC, container/volúmenes cuando corresponda y snapshot;
  no volver a instalar, resolver tags o regenerar secretos.

## Registro y depuración

Fragmento del nodo: execution_id, source_seq, captured_at, fase, stream, texto depurado. El productor
incrementa source_seq en orden de captura; si descarta, comunica el rango/contador omitido.
Flush <=250 ms, fragmentos <=8 KiB y memoria/spool acotados. Mantener flujo aunque no haya lector.

Al ingerir, el portal fija source=runner y source_key derivada de source_seq. Sus propios hitos
anteriores a start usan source=portal, source_seq nulo y clave estable por intento/fase/hito;
ambos se deduplican por (execution_id, source, source_key) y comparten secuencia global bajo lock.
Los eventos portal son de esquema cerrado y se guardan con su cambio de fase; nunca se envían
como salida del nodo ni avanzan su ACK. Un fallo de creación sin job deja consola legible y
resumen seguro. Si hubo job, antes del evento final de entrega/fallo ingerir su último cursor
confirmado para preservar el orden causal, sin ordenar retrospectivamente por timestamps de hosts distintos.

Sólo eventos propios de esquema cerrado y salida admitida por el perfil. Registrar secretos antes
de ejecutar; redactor incremental con ventana suficiente cubre tokens partidos entre chunks y
representaciones declaradas. Descartar salida desconocida, secuencias de terminal y contenido que
podría contener secretos no registrados antes de persistir/transmitir. Mensaje fijo de supresión.

El harness reemplaza logging/error artifacts de Core y desactiva tracing/telemetría; Docker no
usa su retención cruda de stdout. Es obligatorio probar DB, spool, journal y archivos operativos
del guest/nodo. Los archivos privados que necesita la propia aplicación no son la consola NAP
ni se exportan como registro técnico.

`read` se puede repetir; ACK sólo tras transacción de ingesta confirmada. Si el spool se llena,
señalar pérdida y continuar sin bloquear al instalador. Un lector caído no habilita ni detiene
la ejecución. No incluir contraseñas generadas por instaladores en el resultado de protocolo.

## Resultados e incidencias

Estados de trabajo: `preparado`, `ejecutando`, `confirmado`, `fallido`, `incierto`. Confirmado sólo
acredita las comprobaciones que enumera el resultado. Status incluye identidad/configuración,
última fase, último cursor, node_boot_id y resultado/errores seguros; no incluye request sensible.

Incidencias cerradas: INVALID_REQUEST, PROFILE_UNAVAILABLE, IDENTITY_MISMATCH, STALE_CONTROLLER,
EXECUTION_CONFLICT, DEPENDENCY_UNAVAILABLE, NO_SPACE, DEADLINE_EXCEEDED, UNCONFIRMED.
La recepción de un error no prueba que el recurso esté ausente. Ninguna limpieza toca invitados
sin propiedad demostrada. El reconciliador del portal decide transiciones y capacidad.
