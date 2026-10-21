# Ejecución con Docker

## Desarrollo local

`docker compose up --build` usa `docker-compose.yml` y, si existe, su override de desarrollo. Publica el frontend Vite en http://localhost:5174, API en http://localhost:8001 y PostgreSQL en el puerto 5434. Mailpit es un buzón de prueba. Este entorno tiene valores de demostración y conexión PVE de desarrollo; no se publica como instalación operativa.

El arranque espera la base y ejecuta la API. No migra, no siembra catálogo, no crea cuentas y no restablece contraseñas. Migraciones/bootstrap son intervenciones explícitas. El frontend usa el target `dev`; la imagen estática HTTPS se construye mediante el target `production`.

## Producción: preparación

Usar exclusivamente `docker-compose.production.yml`, pasando `-f` explícitamente. No combinarlo con el compose ni el override de desarrollo. Requiere Docker con Compose, almacenamiento persistente, DNS accesible a los visitantes, certificado TLS de ese nombre y CA pública de PVE comprobada. Los puertos publicados son 80/443; API y base no se publican en el host.

1. Copiar `infra/production/compose.env.example` fuera del repositorio. Contiene sólo rutas e identificadores, nunca contraseñas. Elegir una subred Docker sin solapamiento, una IP fija de proxy y un rango dinámico que la excluya. Por ejemplo, proxy `.2` y rango `.128/25` dentro de una `/24`.
2. Preparar directorios privados fuera del repositorio: secretos, TLS, clave SSH dedicada/known_hosts y artefactos. Elegir `NAP_RUN_UID`/`NAP_RUN_GID` no root. Los archivos privados deben pertenecer a ese UID, con modo 0600 y directorios de acceso restringido. Compose monta los secretos como archivos; no confiar en que cambie su propietario o permisos. La lectura de configuración comprueba propietario, modo, tipo, tamaño y formato; rechaza enlaces simbólicos.
3. Copiar `infra/production/settings.example.json` como `runtime.json` y `release.json` dentro de `NAP_SECRETS_DIR`. El ejemplo contiene claves/credenciales vacías y no permite arrancar. Completar mediante el procedimiento institucional, sin pegar secretos en chats, argumentos de comandos o archivos versionados.
4. Instalar claves JWT/CSRF propias e independientes y un keyring Fernet versionado. API, worker y release deben compartir ese keyring y conservar todas las versiones aún utilizadas. No regenerarlo al reiniciar. La clave de PVE pertenece a una cuenta/token dedicada, con permisos mínimos comprobados; no usar root. Activar verificación TLS y montar su CA pública en `/run/pve-ca.pem`.
5. Usar `app_env=production`, `app_debug=false`, origen HTTPS real en `app_frontend_url`/`auth_allowed_origins` y únicamente la IP fija del proxy como red confiable `/32`. Si cambian las rutas del host, las rutas internas de los JSON siguen siendo `/run/pve-ca.pem`, `/run/nap-artifacts` y `/run/nap-runner`. Registrar artefactos/perfiles sólo con destinos y hashes comprobados; la configuración no publica ofertas por sí sola.
6. Configurar SMTP autenticado con un único modo TLS y una dirección de remitente institucional. Mailpit no forma parte de este archivo operativo. Completar las pruebas reales de entrega/acceso aparte.

`runtime.json` usa un rol PostgreSQL de aplicación sin privilegios de dueño ni DDL. `release.json` cambia únicamente la conexión de base por la del propietario autorizado a migrar. Las URL de base se guardan exclusivamente en esos archivos; sus contraseñas deben estar correctamente codificadas como URL. `postgres_password` contiene la contraseña inicial del propietario de la base, no la del rol de aplicación.

El certificado completo y su clave se montan como `/run/tls/fullchain.pem` y `/run/tls/privkey.pem`. Deben ser legibles por el UID elegido sin abrir lectura pública de la clave. La CA de la conexión PVE y la cadena TLS del portal tienen funciones diferentes. El visitante debe poder verificar la cadena del portal; no desactivar la verificación para aceptar la entrega.

La clave SSH se monta sólo donde se usa el runner/preflight; la intervención de migración no recibe ese directorio. Es la cuenta dedicada de protocolo cerrado con huella fijada; no una credencial root ni una shell libre. Los manifiestos y bundles ya comprobados se montan de sólo lectura.

## Release explícita

En los comandos siguientes, sustituir `/ruta/privada/compose.env` por el archivo preparado. No poner valores secretos en la línea de comandos.

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml build
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml up -d --wait db
```

Sobre una base existente: detener API/worker, obtener copia verificada y ejecutar primero el preflight/backfill revisado en una copia. Las revisiones aditivas permiten regularizar; `009_13_cierre_constraints` rechaza retirar columnas que aún contengan secretos pendientes de cuarentena. No inventar fechas, adoptar por VMID ni borrar historia para forzar la migración. Ver [backfill](docs/evidencia/009/us8-backfill.md), [regularización](docs/evidencia/009/us8-regularizacion.md) y [esquema final](docs/evidencia/009/us8-esquema-final.md).

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml run --rm migrate
```

Crear una vez el rol de aplicación en una terminal del operador, como propietario de la base. Los nombres del ejemplo deben coincidir con los configurados; `-W` pide la contraseña sólo en esa terminal:

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml exec db psql -U nap_owner -d nap_portal -W
```

```sql
CREATE ROLE nap_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password nap_app
```

Configurar la contraseña elegida sólo en `runtime.json`. Aplicar `infra/production/permisos.sql` como propietario tras cada release, con la variable psql `nap_runtime_role` que identifique ese rol. El script permite DML del dominio, conserva evidencias/bitácora/historia como sólo agregado y no permite cambiar la versión de esquema. No otorga propiedad ni CREATE de esquema. Una forma de ejecutarlo, usando la contraseña ya montada en el contenedor de base y sin ponerla en argumentos, es:

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml exec -T db sh -c 'PGPASSWORD="$(cat /run/secrets/db_password)"; export PGPASSWORD; exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v nap_runtime_role=nap_app' < infra/production/permisos.sql
```

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml run --rm preflight
```

El preflight de release inspecciona configuración, datos, claves y ofertas en modo de sólo lectura. No realiza sondeo PVE salvo que se invoque expresamente `python -m scripts.preflight --datos --inventario`. Los hallazgos de legado requieren revisión administrativa y no se consideran aceptación aprobada. El arranque de API/worker comprueba configuración, rol sin DDL, revisión Alembic exacta, descifrado y ofertas, sin migrar ni sembrar. Las guardas individuales mantienen bloqueados los nuevos inicios de registros sin regularizar.

Si la base está vacía y aún no tiene administrador, realizar el bootstrap explícito desde una terminal interactiva:

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml run --rm api python -m scripts.bootstrap_admin
```

Solicita usuario, nombre, correo y contraseña sin mostrarla. Rechaza recrear administración existente. El primer acceso cambia la contraseña; 2FA es opcional para ambos roles. Si ya estaba activo, sigue exigiéndose.

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml up -d --no-build api proxy
```

Comprobar DNS/certificado desde el equipo visitante y el recorrido de ambos roles. El proxy sirve la SPA compilada y `/api/` bajo el mismo origen HTTPS, admite Upgrade de WebSocket y vuelve a resolver la API cuando cambia su dirección Docker. Sobrescribe cabeceras de proxy con el origen observado. Las decisiones llevan `no-store`; los assets con hash permiten caché inmutable. Cookies HttpOnly/Secure/SameSite y Origin/CSRF siguen siendo responsabilidad del backend.

Los logs de acceso del proxy excluyen parámetros de URL. Uvicorn no duplica el registro de acceso; la auditoría de negocio/seguridad persiste en la base. No activar trazas SQL ni imprimir configuración privada para diagnosticar errores.

## Worker y reinicios

El worker tiene perfil separado y no se inicia con el comando anterior. Habilitarlo sólo cuando estén comprobados configuración, inventario, runner, red y propiedad. Una restauración requiere además su procedimiento de revocación/reconciliación antes de reanudar trabajos; no conectar un corte restaurado directamente a los recursos reales.

Para una copia restaurada, configurar una nueva `restauracion_referencia` en los archivos privados de runtime/release **antes de arrancar** y seguir [preparar-restauracion.md](docs/preparar-restauracion.md). El preparador se ejecuta como mantenimiento sobre la copia; no migra ni crea cuentas. API/worker/outbox permanecen bloqueados hasta la habilitación explícita con ensayo separado y reconciliación. Reaplicar `infra/production/permisos.sql` después de la migración: el rol runtime sólo lee el control de restauración.

```bash
docker compose --env-file /ruta/privada/compose.env -f docker-compose.production.yml --profile worker up -d --no-build worker
```

API no contiene scheduler. Reiniciar API, proxy o worker no migra, no cambia cuentas ni recrea el catálogo. Para actualizar una release, detener el worker, obtener respaldo y ejecutar nuevamente migración explícita, permisos, preflight y comprobaciones. No usar `down -v` en la instalación operativa: eliminaría su volumen persistente.

La base usa volumen persistente sin puerto publicado, autenticación SCRAM y una red interna. El proxy no recibe credenciales de base ni de PVE. API/worker y proxy se ejecutan sin root, con sistema de archivos de sólo lectura, directorios temporales delimitados, capacidades eliminadas y sin elevación de privilegios.

## Alcance de la validación

Las imágenes base tienen digest fijo; Python instala `requirements.lock` con hashes y frontend usa `npm ci`. La revisión de advisories/dependencias se registra aparte en la tarea T128. Un build correcto no acredita por sí solo las integraciones externas.

El ensayo Docker/HTTPS aislado se documenta en `docs/evidencia/009/produccion.md`. Usa CA, keyring, datos y credenciales exclusivos de prueba. La entrega operativa conserva pendientes sus pruebas reales de PVE/SSH/permisos/consola, DNS/TLS visitante, SMTP, aplicaciones, respaldo/restauración y ensayo con el responsable de cátedra.

Referencias técnicas consultadas: [secretos de Compose](https://docs.docker.com/compose/how-tos/use-secrets/), [proxy WebSocket de Nginx](https://nginx.org/en/docs/http/websocket.html), [privilegios PostgreSQL 16](https://www.postgresql.org/docs/16/sql-grant.html).
