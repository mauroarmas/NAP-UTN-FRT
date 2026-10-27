# Pools automáticos por cátedra — 25/10/2026

Se implementó la preparación automática de `catedra-{id}` antes de crear el invitado, la consulta administrativa sin efectos `GET /catedras/{id}/infraestructura` y el ID como primera columna en la tabla de Cátedras. La consulta diferencia preparado, pendiente del primer servicio y requiere atención; antes de consultar, la UI indica sin verificar.

## Validación aislada

- Creación y reutilización deterministas; respuesta perdida después de crear.
- Permisos insuficientes y conexión no verificable sin POST de creación.
- Miembros ajenos conservados y despliegue bloqueado, sin adoptar o mover recursos.
- Recuperación del despliegue al corregir permisos: misma operación y reserva, un pool y un contenedor.
- Consulta de administración sin efectos, denegación docente y 404 para cátedra inexistente.
- Tabla con ID primero, modal operable con teclado, foco devuelto al cerrar y fallo posterior que reemplaza un estado preparado anterior.
- Regresión de operaciones durables, reintentos y reserva de VMID.

Resultados: regresión general de backend con 711 pruebas aprobadas (`tests`, excluyendo `tests/postgres`), 9 pruebas específicas del pool tras el ajuste final, 28 recorridos de navegador y 44 pruebas de componentes. Las pruebas del servidor usan bases aisladas; no acreditan concurrencia PostgreSQL ni una creación real en la VM. Las creaciones de pools y contenedores se probaron mediante el doble aislado de Proxmox.

## Consulta real sin mutaciones

Se consultó la instalación actual mediante el cliente configurado:

- Cátedra 2: `catedra-2`, preparado; permisos efectivos comprobados y pool vacío.
- Cátedra 5: `catedra-5`, sin servicios; se preparará en el primer despliegue.
- Los nombres de pools y el inventario de contenedores (ID, estado y pool) fueron idénticos antes y después.

No se eliminaron pools existentes ni se crearon invitados reales. El catálogo y el calendario continúan vacíos tras la limpieza autorizada; esta validación no sustituye la aceptación de despliegues y accesos reales pendiente de la spec 009.
