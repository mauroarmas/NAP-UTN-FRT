# Limpieza del entorno de desarrollo — 25/10/2026

El usuario confirmó que todos los datos eran ficticios y autorizó limpiar la base, exceptuando Usuarios y Cátedras.

Se detuvo brevemente la API y se generó un respaldo completo privado con permisos restringidos en `/home/mauro/.local/share/nap009/limpieza-portal-tp9kjgs4/portal-antes-de-limpiar.dump`. Se restauró en una base temporal, se compararon los recuentos de todas las tablas y las huellas de los datos protegidos y se eliminó esa base temporal.

La limpieza se ejecutó en una transacción, sin CASCADE ni reinicio de secuencias. Se comprobaron huellas antes/después de las tablas protegidas. Se preservaron los 7 usuarios, las 24 cátedras, sus relaciones y los datos de autenticación (sesiones, desafíos y códigos de recuperación), además de la versión de migración. No se cambiaron contraseñas ni preferencias.

Se vaciaron 27 tablas operativas/de prueba: entre ellas los 29 pedidos, 8 servicios, catálogo, definiciones, evidencias, métricas, avisos y calendarios. Se verificaron cero registros en esas tablas antes de reanudar la API. Los trabajos posteriores pueden generar nuevos registros operativos. Catálogo y calendario requieren una configuración nueva para la siguiente demostración.

## Proxmox: consulta de inventario, sin mutaciones

- Todos los invitados estaban detenidos.
- `nap009-staging`: contenedores 100, 102, 104, 105, 106 y 107.
- Sin pool: contenedores 101 y 103, con nombres históricos `cat11-svc26` y `cat11-svc16`.
- Pools `catedra-1`, `catedra-11`, `catedra-13`, `catedra-2` y `catedra-4`: vacíos.

No se eliminaron ni movieron invitados, pools, identidades o permisos nativos de Proxmox. El respaldo conserva las referencias de la base anterior. Los ensayos independientes permanecen en la VM y no aparecen como servicios del portal después de esta limpieza. Una eliminación de esos invitados es una operación distinta a la limpieza de la base.

El flujo nuevo crea cada contenedor con el pool `catedra-{id}` y comprueba su pertenencia antes de continuar. La vista Server View agrupa por nodo; Pool View agrupa por pool.

## Aclaraciones y correo

Administración solicita una aclaración; el titular actual puede responder exclusivamente un pedido propio en `requiere_ajuste` y devolverlo a `solicitado`, sin asignación de hardware. Se conserva la decisión de aprobación/reserva en administración. Los avisos utilizan portal y outbox de correo según preferencias; la respuesta avisa a administración.

Se añadió el servicio de desarrollo `notificaciones`, que ejecuta `python -m app.worker --solo-notificaciones`. Despacha la cola cada minuto y no registra trabajos de métricas, despliegue, vencimientos o reconciliación. Se verificó su ejecución separada; no sustituye al worker completo de infraestructura.
