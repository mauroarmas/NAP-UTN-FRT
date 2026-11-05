# US6 — Receta BookStack

Implementación local, 20 de octubre de 2026. T092 terminada. Imagen operativa y aceptación real pendientes de T101/T102.

## Implementación

`infra/services/bookstack/{build.sh,bootstrap.py,configure.php}` fija BookStack 26.09.1, PHP 8.3 y MariaDB 10.11. El build contrasta las versiones exactas del manifiesto, instala Composer desde su lock sin plugins/scripts y verifica código fuente, revisión y lock antes de instalarlo. No ejecuta un instalador remoto flotante.

Se descargó el archivo oficial únicamente para inspección y verificación local, sin ejecutar su código:

- Revisión: `31d94dd8b98e3334dc01b66bed6d514719a2f85d`.
- SHA-256 del archivo codeload: `5b16eae97d3de86a56a9e9ca46fd263713fecb5c4ae32e67c9f22e0667780378`.
- SHA-256 de composer.lock: `66ddc7f4a71a8ea761ab9db1b0e978bd8f5b18c70571c789e219123c6a7b8ea6`.

Nginx/PHP/MariaDB permanecen enmascarados en la imagen. La preparación crea MariaDB nueva, accesible por socket local, con usuario limitado a la base BookStack. Recibe APP_KEY de 256 bits y claves de instancia por stdin; guarda `.env` con permisos 0640 sin contraseña docente. La red y los certificados provienen de infraestructura; valida certificado, clave y CA, sin crear DNS o certificados ficticios.

Las migraciones oficiales crean una cuenta conocida: antes de arrancar Nginx se sustituye mediante la API UserRepo de la revisión fijada, dentro de una transacción con marcador persistente de instancia. Si se pierde la respuesta después del commit, el marcador impide volver a cambiar su contraseña. Se desactivan público/registro abierto, se verifica el rol administrador local y se exige local_secure para imágenes/adjuntos. Las rutas de almacenamiento y archivos PHP distintos del controlador frontal no se sirven directamente. No se crean alumnos NAP.

Los probes comprueban ajustes/identidad, contenido de `/status` y HTTP 200 del login con CA/nombre verificados. No equivalen a login del docente o comprobación de permisos de lectores. Las consultas inspect/verify solo reciben configuración pública de red y rechazan cambios de endpoint/CIDR respecto de la preparación, sin necesitar claves TLS privadas.

También se corrigió DNS del chroot de build: usa el resolver del host temporalmente y restaura el enlace/configuración original del guest incluso ante un fallo. No se ejecutó un build real.

## Verificación

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/services/tests
```

**37 aprobadas en 2,20 s**, log `/tmp/nap009-us6-recipes-verified.txt`. Incluye nueve BookStack, diez PostgreSQL, cuatro Linux y saneamiento/builder/aislamiento. Antes del código BookStack: ocho fallos esperados por módulo ausente (`/tmp/nap009-us6-bookstack-red.txt`). La prueba adicional del resolver falló antes de implementarse (`/tmp/nap009-us6-builder-resolver-red.txt`).

`bash -n` aprobó los tres build.sh. `configure.php` pasó `php -l` en un contenedor PHP 8.3 efímero, sin red, filesystem de solo lectura y capacidades retiradas; imagen de comprobación `php@sha256:8dbeb51c352cf1f70d5d50f3642c9fbed311e914475ea2382f5bc1525bef7bb3`. No es la imagen del producto.

La extracción local del archivo oficial verificó versión, hashes y bundle con `common.py`, `bootstrap.py`, `configure.php`. Las pruebas de preparación usan dobles: no acreditan SQL real, Composer instalado, login, lectores/revocación, imágenes/adjuntos privados desde otra computadora, persistencia o restauración. Esas comprobaciones siguen pendientes. Runner/cliente/acceso y suites completas todavía requieren las tareas posteriores.

Fuentes: [release](https://github.com/BookStackApp/BookStack/releases/tag/v26.09.1), [instalación](https://www.bookstackapp.com/docs/admin/installation/), [archivos seguros](https://www.bookstackapp.com/docs/admin/upload-config/), [UserRepo de la revisión fijada](https://github.com/BookStackApp/BookStack/blob/31d94dd8b98e3334dc01b66bed6d514719a2f85d/app/Users/UserRepo.php), [configuración de almacenamiento](https://github.com/BookStackApp/BookStack/blob/31d94dd8b98e3334dc01b66bed6d514719a2f85d/app/Config/filesystems.php), [MariaDB install-db](https://mariadb.com/docs/server/clients-and-utilities/deployment-tools/mariadb-install-db) y [ACL Nginx](https://nginx.org/en/docs/http/ngx_http_access_module.html).
