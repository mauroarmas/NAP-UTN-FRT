# Abrir Draw.io con NAP

Ingresá al portal y elegí **Servicios → Ver acceso → Abrir aplicación**. El editor se abre en
una pestaña nueva, usando la sesión actual. No necesitás otra contraseña ni volver a crear el servicio.
Guardá los diagramas como archivos en tu equipo; esta integración no agrega almacenamiento compartido.

El permiso corresponde al responsable actual de la cátedra y a administración. Al cerrar NAP, vencer
su sesión o retirarse el permiso, las siguientes consultas a la aplicación requieren volver al portal.
Un editor ya cargado puede conservar lo que está en memoria: cerrar la sesión no borra diagramas.
Las direcciones anteriores del contenedor mantienen su protección interna; usá el botón del portal.

Esta integración corresponde a **Draw.io**. No crea una cuenta dentro de cualquier otro software.
BookStack y PostgreSQL conservan sus mecanismos propios de acceso.

## Instalación de infraestructura, una vez

El gateway es una aplicación ASGI separada (`app.application_gateway:app`). No montar el editor en
una ruta del portal o de su API: cada instancia debe tener su propio origen HTTPS. En la configuración
privada común de API, worker y gateway se incorporan:

```json
{
  "application_gateway_domain": "apps.example.edu",
  "application_gateway_port": 8443,
  "application_gateway_ca_file": "/run/nap/applications-ca.pem"
}
```

- DNS `app-<id de servicio>.apps.example.edu` hacia el gateway y certificado TLS para
  `*.apps.example.edu` (archivos `server.crt` y `server.key`). El dominio de aplicaciones debe quedar
  fuera del host del portal; por ejemplo, portal `nap.example.edu` y aplicaciones `apps.example.edu`.
- CA pública de los contenedores en `applications-ca.pem`. El gateway valida su certificado, SNI,
  propiedad, dirección fija y perfil de red; no utiliza destinos elegidos por el navegador.
- Configuración y clave TLS privadas, legibles por UID 10001; `settings.json` y `server.key` con
  modo 0600. La CA pública puede tener modo 0644. El directorio TLS no se comparte por NFS.
- La imagen de backend debe incluir la migración `010_06_acceso_aplicacion`. Respaldar y ejecutar
  `alembic upgrade head` antes de habilitar el gateway. API, worker y gateway usan la misma base y
  el mismo keyring institucional. No copiar claves ni identidades de este laboratorio.

[Complemento de Compose](../infra/application-gateway.compose.yml): definir rutas absolutas
`NAP_SETTINGS_DIR`, `NAP_APPLICATION_TLS_DIR` y, si corresponde, `NAP_BACKEND_IMAGE`,
`NAP_GATEWAY_BIND` y `NAP_GATEWAY_HTTPS_PORT`. Construir `api` con ese complemento antes de
arrancar el gateway; no usar una imagen antigua. El puerto publicado debe coincidir con
`application_gateway_port`. TLS termina en el propio gateway; no se confía en cabeceras reenviadas.
La publicación en la red universitaria requiere los datos de infraestructura reales.

## Controles y pruebas

La apertura usa un código de un solo uso, válido hasta 60 segundos, enviado por POST. Se guarda
sólo su hash. La cookie de la aplicación es `__Host-nap_app`, segura, HttpOnly y limitada a su host;
no contiene la contraseña de NAP. Cada solicitud revalida sesión, MFA si está habilitado, usuario,
cátedra, vigencia y estado de la instancia. Las credenciales internas del contenedor quedan en el
servidor y no se entregan al navegador. Los códigos vencidos se eliminan después de un día.

Una respuesta HTTPS correcta del editor completa la entrega y genera el aviso del pedido, una sola
vez por entrega. Esta comprobación se vincula a la preparación concreta; no sustituye evidencias
externas ni acredita la red universitaria. Los fallos TLS, de autenticación o de contenido no entregan
el servicio. Se impiden redirecciones externas y la instalación de service workers para que una caché
no oculte el cierre de sesión.

Prueba manual:

1. Como responsable, abrir el servicio: debe aparecer Draw.io, sin el texto BookStack ni otro login.
2. Crear un diagrama y guardarlo en el equipo. Volver a abrir el archivo en el editor.
3. Cerrar la sesión de NAP y recargar el editor: debe pedir volver al portal.
4. Otra cátedra no debe ver ni abrir ese servicio; administración sí puede hacerlo.

Pruebas automatizadas: `tests/test_acceso_aplicacion.py`, `tests/postgres/test_acceso_aplicacion.py`
y `frontend/tests/acceso-aplicacion.test.jsx`. Las pruebas PostgreSQL incluyen dos consumos
concurrentes del mismo código y dos confirmaciones simultáneas sin duplicar la entrega.

Referencias: [cookies y prefijo __Host](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie),
[parámetros de Draw.io](https://www.drawio.com/docs/reference/supported-url-parameters/) y
[bloqueo de scripts de service worker](https://chromium.googlesource.com/chromium/src/+/main/docs/security/service-worker-security-faq.md).
