# Reparación del entorno local y limpieza Proxmox

Fecha: 2026-10-25. El usuario notificó que incorporar Draw.io no mostraba resultado y que permanecían los recursos ficticios cuya limpieza esperaba.

## Causa y corrección de la incorporación

La base operativa estaba en `009_14_restauracion`, mientras que el código cargado era de 010. Faltaban `incorporaciones_aplicacion` y la columna `pedidos.seleccion_oferta_snapshot`; por ello la incorporación y otras consultas respondían con errores. El feedback se encontraba por encima del área visible del modal y la recuperación inicial de fichas ignoraba su error.

Se generó una copia completa privada, se restauró en una base temporal y se compararon las huellas de Usuarios/Cátedras antes de eliminar esa base temporal. Luego se aplicaron explícitamente las migraciones 010_01, 010_02 y 010_03 y se reinició la API. Se comprobaron 7 usuarios y 24 cátedras con las mismas huellas antes/después.

El botón ahora indica «Incorporando…». Los errores de incorporación aparecen junto a la acción, reciben foco y quedan visibles; una respuesta confirmada desplaza el modal a la ficha y muestra que aún falta preparar/publicar. También se informa el fallo de recuperación inicial de fichas. Los reintentos conservan la clave de idempotencia.

Se completó la incorporación solicitada de Draw.io usando la fuente real y el servicio de dominio con el administrador existente: respuesta 201 y una única ficha guardada, UUID `e33ba2be-aa64-4ba4-8a3d-414ba0aeeea0`. No se construyó una imagen ni se instaló/publicó una instancia por incorporar la ficha.

## Recursos ficticios eliminados

Antes de mutar se comprobaron cero servicios, pedidos, identidades, compromisos, operaciones y ensayos en el portal; los ocho invitados estaban detenidos, con nombres/nodo/pools esperados y configuraciones sin modificaciones. Se guardaron inventario y configuraciones en un directorio privado. Se revalidó la configuración de cada contenedor antes de su eliminación.

| VMID | Nombre |
|---|---|
| 100 | nap009-linux-ensayo-1 |
| 101 | cat11-svc26 |
| 102 | nap009-linux-ensayo-2 |
| 103 | cat11-svc16 |
| 104 | pg1.nap009.lab |
| 105 | pg2.nap009.lab |
| 106 | bookstack1.nap009.lab |
| 107 | bookstack2.nap009.lab |

Cada eliminación se confirmó mediante su tarea Proxmox y ausencia posterior en inventario. Después se eliminaron, ya vacíos, `catedra-1`, `catedra-11`, `catedra-13`, `catedra-2`, `catedra-4` y `nap009-staging`.

Comprobación final: cero invitados LXC/QEMU, cero pools y cero ACL residuales asociadas a esos invitados o pools. Las plantillas/imágenes y recetas reutilizables no formaban parte de esta eliminación. La bitácora privada conserva las tareas y el resultado de cada paso; no se publican configuraciones ni credenciales.

Respaldo restaurado y verificado, huellas, inventario, configuraciones y bitácora: `/home/mauro/.local/share/nap009/reparacion-010-o47et8no/`, directorio 0700 y archivos privados 0600.

## Pruebas

- 55 pruebas de interfaz aprobadas en 14 archivos (29.68 s).
- 8 recorridos de navegador aprobados (27.7 s), incluido fallo 500, error visible y enfocado, reintento con la misma clave y confirmación enfocada. Incluye build Vite.
- Lint sin errores; permanecen ocho advertencias anteriores. `git diff --check` correcto.
- Verificación real de migraciones, preservación de datos, incorporación y limpieza descrita arriba; los recorridos del navegador utilizan fixtures y no sustituyen esa comprobación operativa.
