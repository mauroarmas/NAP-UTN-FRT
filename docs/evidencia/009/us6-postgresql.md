# US6 — Receta PostgreSQL 16

Implementación local, 20 de octubre de 2026. T091 terminada; no constituye evidencia de acceso real ni de una imagen construida.

`infra/services/postgresql/build.sh` verifica PostgreSQL 16 y deja el servicio bloqueado en la imagen. `bootstrap.py` inicializa un clúster nuevo después de validar material TLS institucional; nunca adopta datos sin su marca de preparación. Crea base/rol de instancia sin superusuario, creación de bases/roles, replicación, bypass RLS ni membresías. Las conexiones remotas exigen TLS/SCRAM y CIDR autorizado. La base del portal no interviene.

La contraseña se transforma en verificador SCRAM antes de enviar SQL por stdin. La prueba inicial autentica al propietario, crea/inserta/lee una tabla temporal y revierte la transacción. El archivo de contraseña de esta prueba se elimina incluso si falla. El monitoreo autentica un rol separado, limitado a una base de salud, y ejecuta SELECT; un reintento no cambia la clave del docente ni recrea datos. No se generan DNS ni certificados ficticios. El runtime compartido valida cadena/nombre/vigencia/clave y bloquea root/autologin en los tres productos.

Se amplió el saneamiento para quitar estado de preparación, claves y credenciales de monitoreo de imágenes reutilizadas. El builder vuelve a generar metadatos de imagen después del saneamiento.

## Pruebas

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/services/tests
```

Resultado: **26 aprobadas en 1,52 s**, incluidas nueve PostgreSQL; log `/tmp/nap009-us6-postgresql-verified.txt`. La ejecución inicial, antes del código, produjo nueve fallos de importación: `/tmp/nap009-us6-postgresql-red.txt`.

Los dobles verifican configuración y comandos, restricciones, derivación SCRAM, rechazo de datos preexistentes/perfiles inválidos, rollback solicitado y reintentos sin cambios de credenciales. No ejecutan PostgreSQL guest, OpenSSL, systemd, red ni chroot. TLS efectivo, SQL real, aislamiento, persistencia tras reinicio y acceso desde la red prevista requieren las instancias reales de T101/T102. No hay despliegue ni migración operativa.

Fuentes primarias: [SCRAM PostgreSQL 16](https://www.postgresql.org/docs/16/auth-password.html), [roles](https://www.postgresql.org/docs/16/sql-createrole.html), [TLS del servidor](https://www.postgresql.org/docs/16/ssl-tcp.html), [verify-full](https://www.postgresql.org/docs/16/libpq-ssl.html), [pgpass](https://www.postgresql.org/docs/16/libpq-pgpass.html) y [pg_createcluster](https://manpages.debian.org/bookworm/postgresql-common/pg_createcluster.1.en.html).
