# Base común 011 — avance del 26/10/2026

Implementación parcial de Phase 2. No habilita perfiles ni ofertas y no acredita
el despliegue definitivo de aplicaciones. Draw.io conserva su camino existente.

## Contratos y perfiles

- `nap-deployment/1`: dos orígenes discriminados, datos estrictos, límites de
  recursos/variables/persistencia, probes tipados y errores sin entradas privadas.
  Hash canónico y pruebas de equivalencia entre validación de portal y nodo.
- `nap-application-job/1`: requests por acción; respuestas cerradas y correlacionadas
  con la identidad completa. Rechaza comandos, rutas, unidades y cursores inválidos.
  La huella liga configuración y referencias/versiones; excluye valores privados
  y generación del controlador. Todavía falta el supervisor y el cliente SSH.
- Registro institucional compartido: hash de definición, plataforma/base/runtime
  exactos, estados explícitos, evidencia referida al hash final, 2700 s y dos trabajos
  por nodo. Registro vacío por defecto; no activa capacidades por ejecutar pruebas.
  El instalador futuro debe empaquetar el contrato común y `jsonschema` explícitamente.

## Persistencia y secretos

Migración aditiva `011_01_despliegue_aplicaciones` desde `010_06_acceso_aplicacion`:
seis tablas nuevas, vínculos nullable, agenda sin backfill y exclusión de origen.
Las revisiones validadas son inmutables por ORM y trigger PostgreSQL, con retirada
lógica definitiva. Se conserva el contador de reclamaciones histórico separado
del número de intento efectivo. La consola liga raíz/intento/ejecución y diferencia
eventos portal/runner; cuota y secuencia quedan restringidas en el esquema.

La prueba PostgreSQL compara todos los valores anteriores de usuarios, cátedras,
templates, pedidos, servicios, identidades y operaciones terminales antes/después.
Comprueba FK, índices parciales, exclusión, trigger y downgrade sin pérdida silenciosa.
También se ejecutó el upgrade en el portal local, con respaldo privado `pg_dump`
verificado previamente. `/api/v1/health` respondió 200 después de la migración.
No se crearon invitados ni reservas como efecto de migrar.

`SecretoDespliegue` usa el keyring existente con contexto pedido/nombre/revisión.
Creación serializada por pedido; otro alta recibe otros valores. Un reintento conserva
referencias/valores aunque cambie VMID; una renovación reutiliza los del alta original.
Entrada aportada write-only, replay que no reemplaza secretos y HMAC contextual con
soporte de clave anterior tras rotación. Descifrado sólo tras autorización vigente
de acceso, o lease actual y referencias/snapshot coincidentes para dispatch privado.
No se copian valores a snapshots, contexto, oferta o campos legacy de Servicio.

## Depuración previa a consola

`redaction.py` es una biblioteca todavía sin integrar al ejecutor definitivo.
Procesa UTF-8 incremental y controles ANSI/OSC/bidi; cubre representaciones declaradas,
fronteras entre chunks y prefijos truncados. El texto desconocido se descarta incluso
si no contiene un secreto registrado. Sólo eventos cerrados y paquetes admitidos por
el perfil producen mensajes; entradas/colas de memoria tienen límites explícitos.
Faltan el spool, la ingesta transaccional, el servicio systemd y la comprobación real
de ausencia de secretos en journal/archivos durante despliegues completos.

## Validación

- Suite completa de backend ordinaria: **860 aprobadas**, antes de añadir la prueba
  adicional de rotación HMAC. Ninguna prueba conecta al Proxmox real.
- Selección 011 posterior y regresión de runner: resultados registrados al completar
  este bloque en `tasks.md`.
- Migraciones 009/010/011: se corrigió el backfill previo a 010 para diferir columnas
  011; las fixtures de un esquema congelado 009 usan SQL de esa versión.
- PostgreSQL 16 temporal, puerto 55432/esquemas aleatorios: carreras de secretos,
  unicidad de intento/dirección activa y takeover sin renumeración. Las restricciones
  no sustituyen las pruebas pendientes del asignador/admisión de T012/T023/T030.
- Laboratorio 011: **98 aprobadas**, incluye Core real en Docker sin red; sigue
  siendo distinto de los ensayos físicos documentados en `compuertas.md`.

No se certificó la red o el clúster universitario. El uso productivo de perfiles
continúa condicionado a T028, T050 y T061 y a las aceptaciones de cada historia.
