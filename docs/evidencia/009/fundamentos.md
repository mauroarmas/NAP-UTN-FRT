# Fundamentos compartidos — T008–T019

Fecha: 2026-10-20. Implementación aditiva; la entrega completa y las integraciones institucionales siguen pendientes.

- T008–T010: pruebas escritas y ejecutadas antes de los servicios correspondientes. Se observaron fallos por contratos/módulos faltantes y por rutas que todavía devolvían 404; los cuatro casos del schema existente pasaban.
- T011–T013: diez tablas compartidas, snapshots/revisiones y vínculos nuevos; Alembic `009_01_base_cierre` sobre `8b9c0d1e2f3a`, con DDL congelado sin importar modelos al ejecutar. Fresh y upgrade pasan en esquemas PostgreSQL temporales; preservan titular anterior y no inventan identidades/evidencias. Las pruebas entregan la conexión aislada a Alembic, sin resolver una base desde el entorno operativo.
- T014–T015: contratos cerrados, unidades GiB/MiB, errores públicos estructurados y fechas UTC con fin exclusivo; se rechaza activar sin período fiable y se conserva el receso entre vigencias aprobadas aunque cambie el calendario.
- T016: tres casos PostgreSQL pasan: misma clave simultánea produce un solo efecto, payload diferente genera 409, rollback elimina efecto y clave juntos. El servicio no hace commits internos.
- T017: cifrado Fernet versionado y ligado a contexto, rotación conservando lectura, rechazo de claves compartidas con JWT/CSRF y redacción. Tres casos pasan. Los secretos de configuración tampoco aparecen en repr(Settings).
- T018: registro administrativo POST/GET de evidencias, máximo 64KiB, JSON canónico inmutable, hash/actor/instante de servidor y referencia UUID. Se prueban definición, trámite e instancia preparada, nonce/endpoint/función, roles, replay, tamaño/duplicados, simulación operativa y alteración directa del JSON almacenado. Los schemas se empaquetan en backend y el verificador exige igualdad con sus contratos.
- T019: una sola asignación de estado de pedidos existentes en pedido_service.transicionar, historial con actor usuario/sistema y evento único, sin commit en la transición. Diez pruebas de historia/rollback, fallo PVE y concurrencia existente pasan; los locks PostgreSQL de capacidad de US3 requieren sus propias pruebas posteriores.

Validaciones por grupo: contratos/vigencias/cifrado 17/17; idempotencia PostgreSQL 3/3; migraciones PostgreSQL 2/2; schemas y evidencias 17/17; historia/fallo/capacidad existente 10/10. Los grupos comparten algún escenario y no se suman como pruebas únicas. Metavalidación Draft 2020-12, trece ejemplos JSON, sintaxis Python y git diff --check pasan.

La primera regresión completa devolvió 359 aprobadas y doce fallos: once aserciones de mensajes antiguas y el fallo del tope de disco conocido. Se adaptaron las aserciones a detail.mensaje manteniendo sus estados/reglas; las 41 regresiones afectadas pasan. El fallo del tope continúa pendiente de T134, visible en CI. La transición central no introduce una nueva aprobación pública que omita la reserva.

Compatibilidad de UI: se reprodujo un fallo real al renderizar detail como objeto en ingreso; mensajeError conserva el error estructurado para decisiones y entrega texto al componente. Pasa con formato anterior y nuevo (2/2); lint/build terminan correctamente con las advertencias conocidas. Los flujos completos de sesión/2FA y las pruebas funcionales del resto de pantallas se implementan en sus historias.

No se ejecutaron migraciones en una base operativa ni comandos en Proxmox. La prueba de revocación nativa, el acceso desde red alumno, carga y restauración siguen siendo gates de sus tareas de aceptación.
