# Configuración de producción y ensayo aislado — T127

Fecha: 2026-10-21. Se implementaron compose autónomo, proxy HTTPS/SPA/API, archivos privados montados, separación release/API/worker y rol runtime sin DDL. Ver [DOCKER.md](../../../DOCKER.md) y [resultado estructurado](produccion-smoke.json).

No se levantó producción ni se modificaron la base operativa o Proxmox. El ensayo usó el proyecto Docker exclusivo `nap009-produccion-smoke-20261021`, PostgreSQL temporal en tmpfs, puertos de visitante 18080/18443 limitados a loopback, DNS de prueba resuelto sólo en el proceso cliente, CA/credenciales/keyring exclusivos y ningún artefacto o servicio real. El cliente verificó TLS con su CA de prueba; no se desactivó la verificación. Worker no iniciado, SMTP/PVE reales no probados.

Se construyeron las imágenes de backend y web con las bases fijadas por digest. El backend instala el lock con hashes; el proxy sirve el build compilado. Antes de crear expresamente el usuario fixture se comprobó que migrar/arrancar no creó cuentas. Se creó un rol runtime distinto del propietario y se ejecutó el script de permisos. Se comprobó rechazo de CREATE TABLE, modificación/borrado de historia y modificación de alembic_version con ese rol.

HTTPS comprobado: SPA con navegación directa, assets inmutables, cabeceras de seguridad, API bajo el mismo origen, login y cambio de contraseña inicial, 2FA opcional, cookies Secure/HttpOnly/SameSite, CSRF exigido y logout con revocación. El preflight readonly resultó apto para configuración/datos/claves/catálogo vacío del fixture, sin sondeo PVE. La API respondió también después de cambiar su IP Docker; el proxy usa resolución DNS dinámica. Un reinicio posterior de API/proxy conservó exactamente las cuentas/versiones/hash de contraseña y no creó operaciones.

Incidencias encontradas y corregidas antes de aceptar el ensayo:

- La lista YAML en línea separaba por comas una opción tmpfs; se convirtió en una cadena única.
- La IP fija del proxy se asignaba antes a la API por el pool automático. Se delimitó un rango dinámico que la excluye y se repitió desde base temporal vacía.
- El log de acceso predeterminado de Nginx se heredaba además del formato seguro e incluía el canario de parámetros de URL. Se configuró el formato por servidor y se desactivó el acceso duplicado de Uvicorn. Se repitieron consultas canario a SPA/API/HTTP y se verificó que no aparecieran en logs finales. No se encontraron contraseñas, keyring ni tokens del fixture en los logs revisados.

Pruebas adicionales: 32 pruebas de archivo privado/preflight aprobadas en 3,88 s; diez de archivo/arranque PostgreSQL aprobadas en 2,23 s (esquema exacto, rechazo de rol propietario, lectura sin migración). Los tests de esquema aíslan la validación de rol/configuración; el ensayo Docker prueba conjuntamente el rol limitado y el arranque real. Compilaciones y `docker compose config` correctos.

El proyecto temporal se detiene y elimina al terminar, conservando sólo evidencia/configuración privada del ensayo fuera del repositorio. Las imágenes de este resultado corresponden al cierre T127, anterior a la actualización de dependencias de T128; esa actualización requiere sus propias regresiones. Estos resultados no acreditan integración PVE/SSH, consola, SMTP, DNS/TLS del visitante, aplicaciones, restauración ni aceptación institucional.
