# US6 — Acceso inicial autorizado

T096 implementada en `service_access_service` y rutas/schemas de servicio. GET devuelve metadatos tipados sin claves; POST revelado exige permiso actual, preparación confirmada vigente, servicio encendido y cobertura. Antes de verificar red, solo administración revela con `solo_validacion`; después podrá revelar el responsable. BookStack entrega únicamente contraseña docente, nunca APP_KEY ni contraseña MariaDB. Se informa que las credenciales son iniciales y pueden haber cambiado en la aplicación.

Ambas respuestas correctas usan no-store. Cada revelado genera un evento de seguridad con referencia/actor/estado, sin valores. La autorización ocurre antes de descifrar. No se consulta PVE, envía correo, abre consola, cambia contraseña o dispara infraestructura al revelar. La consola sigue cerrada hasta T101.

El detalle administrativo incluye identidad/UUID de preparación y nonce_sha256 cuando la preparación nueva lo conservó; no expone el nonce original. Permite confeccionar el documento de evidencia sin consultas SQL ni revelar secretos de aplicación. Los datos técnicos de verificación no se incluyen en el detalle docente.

Pruebas antes del código: cuatro fallos (`/tmp/nap009-us6-revelado-red.txt`). Después: **4 aprobadas en 3,23 s**, `/tmp/nap009-us6-revelado-first.txt`: revelado de validación/auditoría/no-store, pertenencia antes de descifrar, secretos internos BookStack omitidos y servicio detenido sin revelado. La verificación de red y entrega ordinaria permanecen pendientes de T097, y la UI de T099.
