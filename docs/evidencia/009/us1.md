# US1 — permisos actuales y cambios de consola

Validación local del 20/10/2026. No se consultó Proxmox ni se modificaron cuentas institucionales.

- 62 pruebas backend aprobadas: aislamiento entre cátedras, permisos administrativos incluso en pedidos propios, bloqueo inmediato del alcance pendiente, revocación declarada, retiro lógico e historial, y acciones nombradas. El PATCH genérico devuelve 405 sin transicionar ni liberar reservas.
- 4 pruebas PostgreSQL aprobadas en esquemas descartables de PostgreSQL 16: dos transferencias concurrentes, degradaciones pendientes que conservan administración, actualización desde la revisión previa y esquema nuevo. No se usa SQLite como prueba de exclusión entre procesos.
- 7 validaciones del importador comprueban identidad individual, ausencia explícita, duplicados, root compartido y campos no admitidos.
- 3 pruebas Vitest aprobadas: administración exclusiva, registro de evidencia separado de la confirmación y cambio pendiente sin entrega anticipada. Lint sin errores (16 advertencias previas) y build correcto.

Las cuentas legadas comienzan con inventario desconocido: no se retiran sus permisos hasta importar un inventario comprobado. Las cuentas nuevas del portal se registran sin identidad nativa porque el alta NAP no concede derechos Proxmox. Antes de concederlos, infraestructura debe importar la identidad individual con actor y referencia. El importador nunca reemplaza una identidad asignada de manera implícita. Los retiros conservan la cuenta desactivada y su identidad de auditoría, también si no había pedidos.

Un trámite conserva revisión, alcance anterior, permisos que se deben mantener, propuesta y estado. El portal bloquea el alcance antes de completar; un operador institucional revoca sesiones y permisos externos y registra evidencia tipada. Solo después se aplica el cambio académico. Un fallo mantiene el trámite abierto y el titular anterior; la autorización no entrega información de su servicio. Los alcances retenidos son la intersección de los anteriores y los propuestos: conceder permisos nuevos corresponde a una intervención posterior.

Pendiente de aceptación externa en T101/T102: demostrar con identidades reales que tickets, enlaces y sesiones nativas anteriores quedan revocados, sin retirar otros pools legítimos. FakeConsoleDirectory y documentos con simulation=true solo acreditan comportamiento local del protocolo y no esa revocación real.
