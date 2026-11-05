# US6 — Verificar y entregar acceso

T097 implementada localmente. POST verificar-acceso consume una referencia UUID del registro inmutable, sin descargar URLs ni aceptar un booleano de disponibilidad. Revalida integridad/tipo, identidad/nonce, preparación más reciente confirmada, endpoint, fecha exacta, cobertura actual y de observación, estado encendido y pruebas funcionales. Solo acepta entorno real, incluso en modo test.

Para BookStack se explicitan por instancia los resultados `permisos_lectores`, `revocacion_individual`, `archivos_privados`, además de publicación, lectura y persistencia. El contrato de evidencia conserva los identificadores de estas pruebas. Registrar un ensayo sintético marcado como real en tests no acredita una aceptación externa; el operador y las comprobaciones reales siguen siendo gate T102.

La entrega actualiza disponibilidad/evidencia/fecha, activa el pedido y agrega historia/evento de seguridad/aviso en la misma transacción. Repetir con otra clave HTTP o dos transacciones concurrentes no duplica entrega ni aviso. La outbox conserva únicamente un texto/referencia sin contraseñas, APP_KEY, credenciales o endpoints. Se corrigió la deserialización del payload genérico del dispatcher, necesaria para procesar este primer aviso de negocio; las demás notificaciones de T110 continúan pendientes.

**Consola Linux:** el endpoint y la entrega de Linux siguen cerrados hasta completar el gate institucional T101. T101 debe implementar la comprobación de su evidencia de instalación/revocación y habilitar la ruta nativa concreta; una evidencia individual de login/sudo no salta esa condición. No se dio por comprobada la revocación de permisos PVE ni de sesiones abiertas.

## Verificación

- Pruebas previas: cinco fallos por endpoint de verificación ausente (`/tmp/nap009-us6-verificacion-red.txt`).
- Entrega, preparación, probes, outbox de bienvenida y evidencia: **40 aprobadas en 18,13 s**, `/tmp/nap009-us6-verificacion-second.txt`.
- Entrega ampliada con BookStack: **10 aprobadas en 7,92 s**, `/tmp/nap009-us6-entrega-verified.txt`.
- PostgreSQL 16 aislado: **una prueba de dos transacciones independientes aprobada en 1,68 s**, `/tmp/nap009-us6-entrega-postgres.txt`. Comprueba una entrega, historia/evento y aviso portal.
- La fixture de simulación renueva la cabecera de autenticación al cambiar APP_ENV, porque cambia el nombre de cookie. No se debilitó el contrato de cookie para hacer pasar el ensayo.

Ninguna prueba usa SMTP/PVE/SSH reales ni otra computadora. La UI de T098/T099 y las comprobaciones reales T101/T102 siguen pendientes. No declarar US6 aceptada por esta evidencia local.
