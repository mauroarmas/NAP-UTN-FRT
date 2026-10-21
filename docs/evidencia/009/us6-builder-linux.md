# US6 — Constructor, saneamiento y Linux: verificación local

Fecha: 2026-10-20, zona institucional. T089/T090 implementadas con archivos de prueba y ejecutor doble. No se construyó ni desplegó una imagen operativa.

El constructor trabaja sobre una copia privada identificada. Comprueba el checksum de la base sobre los mismos bytes privados que después extrae; rechaza rutas que escapan, dispositivos, duplicados y límites excesivos. Produce tar.gz reproducible, inventario Ubuntu 24.04 amd64 con versiones exactas, digest de imagen y bundle. La ejecución real exige plan, lock completo y recetas coincidentes con una revisión Git; solo invoca comandos y scripts fijos. Las salidas no permiten escritura de grupo/otros y no se sobrescriben artefactos anteriores.

El saneamiento elimina cuentas humanas anteriores, hashes de contraseña, claves host, identidades cloud/machine-id, datos PostgreSQL/MariaDB/BookStack, sesiones, uploads y logs. No sigue directorios simbólicos ni admite montajes. Las pruebas incluyen un enlace malicioso hacia el host y comprueban que se rechaza antes de modificar las cuentas.

La salida inicial es un borrador. El comando de evidencia exige al menos dos UUID distintos, imagen/receta coincidentes y todos los resultados satisfactorios del producto. No rellena checks por defecto. El documento se importa en el portal; `finalize` coteja su checksum y añade el UUID registrado al manifiesto. Un reporte simulado sigue etiquetado como simulado y no habilita publicación operativa.

El runtime de invitado conserva pasos y una huella HMAC sin contraseñas ni nonce en claro; limita bootstrap por recurso. Linux crea `napadmin`, mantiene root bloqueado, configura sudo con contraseña y login mediante agetty sin autologin. Un usuario preexistente no se adopta. Repetir la operación o cambiar su UUID no restablece la contraseña después de completar; cambiar los secretos originales produce conflicto. Inspeccionar no crea estado. Secretos por stdin, sin valores en argv o respuestas.

Verificaciones:

- **17 pruebas aprobadas, 1,12 s**, ejecutando explícitamente `backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/services/tests`: `/tmp/nap009-us6-images-linux-verified.txt`.
- CLI `PYTHONPATH=backend:. backend/venv/bin/python -m infra.services.build_image --help` comprobada; no ejecuta instalación ni red.
- Ambas suites infra ejecutadas antes de completar el runner: **15 aprobadas y 9 errores por el módulo runner todavía inexistente**, `/tmp/nap009-us6-infra-current.txt`. Esos casos pertenecen a T093 y no se declaran aprobados.
- Los fixtures bloquean red y subprocess reales. `git diff --check` sin errores.

Las recetas PostgreSQL/BookStack y el wrapper/cliente de ejecución siguen pendientes. Los builds reales requieren sus scripts completos, lock y revisión comprometida, host de construcción y posterior prueba de dos instancias. Los gates T101/T102 permanecen sin marcar; estas pruebas no acreditan sudo/login por consola ni conectividad académica reales.

Referencias: [filtros tar de Python 3.12](https://docs.python.org/3.12/library/tarfile.html#extraction-filters), [base Ubuntu Minimal 24.04](https://cloud-images.ubuntu.com/minimal/releases/noble/release/), [console-getty de systemd 255](https://raw.githubusercontent.com/systemd/systemd/v255/units/console-getty.service.in), [container-getty](https://raw.githubusercontent.com/systemd/systemd/v255/units/container-getty@.service.in) y [agetty](https://man7.org/linux/man-pages/man8/agetty.8.html). La base efectiva se fija por fecha y SHA-256 al preparar el build; no se usa un enlace `release` flotante como identidad del artefacto.
