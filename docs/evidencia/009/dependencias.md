# Dependencias — T128

Fecha: 2026-10-21. Auditorías completas de los locks, incluidas dependencias de desarrollo. No se ignoraron advisories ni se aplicó `npm audit fix --force`.

| Auditoría | Antes | Después |
|---|---|---|
| pip-audit | 14 identificadores únicos, cinco paquetes afectados; 27 entradas por duplicación de referencias | Cero vulnerabilidades conocidas entre 116 dependencias |
| npm audit | Ocho paquetes afectados | Cero vulnerabilidades conocidas, todas las severidades |

Informes sanitizados: `deps-pip-antes.json`, `deps-pip-despues.json`, `deps-npm-antes.json` y `deps-npm-despues.json`. Conservan versiones, identificadores, correcciones y hash del informe original. El resultado depende de la base de advisories consultada; no acredita ausencia de vulnerabilidades desconocidas.

## Correcciones y alcance

- FastAPI 0.157.0 y Starlette 1.9.0. El formulario de login usa el parser URL encoded afectado por el agotamiento de recursos de Starlette; una regresión comprueba el rechazo de un exceso de campos antes del verificador de contraseña. [Advisory de Starlette](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).
- Se reemplazó python-jose por PyJWT 2.15.1 y se retiraron sus transitivas ecdsa/rsa/pyasn1. El reporte de confusión de algoritmo afecta una configuración con clave pública DER admitida como secreto HMAC. NAP ya restringía HS256 con secreto compartido; no se afirma explotación de esa configuración. Se conservan el formato de tokens HS256, el reloj de servidor inyectable, la lista de algoritmos permitidos y las comprobaciones SID/versión/propósito. [Reporte original](https://github.com/mpdavis/python-jose/issues/414).
- Requests 2.34.2. El advisory afecta extracción de certificados empaquetados mediante `extract_zipped_paths`; NAP usa una CA PEM configurada. Se actualizó igualmente el lock. [Advisory de Requests](https://github.com/psf/requests/security/advisories/GHSA-gc5v-m9x4-r6x2).
- Axios 1.20.0, React Router DOM 7.18.4 y Vite 8.3.5; transitivas corregidas mediante resolución normal del lock. El frontend usa BrowserRouter y se publica como archivos estáticos en Nginx: no ejecuta RSC/SSR ni el adaptador HTTP Node de Axios en producción. Las dependencias de desarrollo y construcción también se actualizaron. [Axios](https://github.com/axios/axios/security/advisories/GHSA-vh66-26gq-q6x8), [React Router](https://github.com/remix-run/react-router/security/advisories/GHSA-qwww-vcr4-c8h2), [PostCSS](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp), [launch-editor](https://github.com/vitejs/launch-editor/security/advisories/GHSA-r825-w8mm-5pxw).

`backend/requirements.lock` se regeneró para Python 3.12 con hashes y se instaló mediante `--require-hashes`. `frontend/package-lock.json` fija la resolución comprobada.

## Verificación

- 54 pruebas de backend aprobadas: tokens compatibles, algoritmos/expiración, sesiones/CSRF/MFA, formularios, transporte de infraestructura, runner, entrega de acceso y autoridad de capacidad. 21,72 s.
- Las 41 pruebas de frontend aprobaron, 13,90 s. Cuatro recorridos Chromium aprobaron: dos de regularización y dos de autenticación, 7,0 y 6,4 s.
- Compilación de las dos imágenes operativas con los locks nuevos aprobada. Lint sin errores; quedan ocho advertencias existentes de Fast Refresh/dependencias de hooks.
- Ensayo Docker aislado con PostgreSQL 16, migración explícita, rol runtime restringido, bootstrap explícito de una cuenta fixture y HTTPS con CA verificada. Login, cambio inicial, 2FA opcional, cookie Secure/HttpOnly/SameSite, CSRF negativo, logout, SPA/assets, cabeceras y redirección aprobados. El canario en query string no aparece en los logs. Imágenes y resultados en `dependencias-smoke.json`.

El proyecto temporal se cerró al finalizar. No se inició worker ni se contactó PVE/SMTP real. No es aceptación de servicios ni de la suite backend completa: esa regresión y SC-008 actualizada corresponden a T134.
