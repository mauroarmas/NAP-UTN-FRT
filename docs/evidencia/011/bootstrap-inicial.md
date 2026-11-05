# Bootstrap 011 — avance de T004

Fecha: 2026-10-26. Laboratorio local, no clúster universitario.

## Controlador verificado

Registry nuevo `nap011-registry`, en `https://172.16.36.1:5443`, con TLS propio,
autenticación y fixture `nap/campus-demo:acceptance` publicada. Se verificaron:

- TLS con la CA explícita, 401 sin autenticación y 200 con la cuenta de lectura.
- HEAD del manifiesto de la imagen y rechazo de escrituras autenticadas.
- UID/GID 1000:1000, rootfs de lectura, capabilities retiradas y logs deshabilitados.
- Clave CA y authfile del publicador fuera de los montajes del registry.
- Repetición del bootstrap sin recrear el servicio ya preparado.

Credenciales, claves y paquetes del operador permanecen fuera del repositorio.
No se agregó un registry de escritura al portal ni una CA al sistema del usuario.
La política de sólo lectura se aplica también tras un fallo de copia de la fixture.

## Nodo verificado

Se preparó el lanzador privado `~/.local/share/nap011/preparar-nodo.sh`, validado con
`bash -n`. Usa la hostkey existente, valida el hash del paquete, admite cuatro archivos
regulares exactos y retira el directorio root temporal al finalizar. El secreto de lectura
se usa sólo para verificar TLS/autenticación y no queda en los archivos del nodo.

El operador lo ejecutó; el primer recibo devolvió `REGISTRY_NOT_CONFIRMED` antes de escribir
el namespace del nodo. El diagnóstico posterior confirmó conexión TCP y rechazo del certificado.
Se reprodujo en esta PC con OpenSSL estricto: faltaban AKI en servidor y SKI en CA (códigos 85/86).

Se corrigió la generación de certificados y se reemitió únicamente la cadena del registry con
respaldo privado, conservando claves, credenciales y fechas de vigencia. Pasaron OpenSSL
`-x509_strict`, una conexión HTTPS estricta autenticada y una prueba TLS con BIO en memoria.
La política de lectura y los montajes mínimos del registry permanecen verificados. No se cambió
el firewall ni la confianza TLS del sistema.

El nuevo recibo confirmó `node_bootstrap_staged` y ningún perfil habilitado. T004 completada.
La política de red quedó staged, no aplicada ni acreditada; se exige antes de arrancar cada guest.
Los candidatos y la política de red permanecen pendientes; no se crearon invitados
ni se modificaron puentes, SSH, cuentas, pools o recursos de Draw.io.

## Verificación automatizada

- 6 pruebas de fixtures backend aprobadas.
- 23 pruebas sin nodo de campus-demo, preflight, bootstrap e infraestructura del registry
  aprobadas (incluyen fallo de disco/TLS/copia, rollback, permisos y datos sensibles).
- 19 regresiones de transporte SSH y recuperación existentes aprobadas.
- 1 ensayo Docker local opt-in aprobado: reinicio, datos persistentes y dos instancias.

Estos resultados no acreditan el runtime Docker anidado, Core, gates de perfiles
ni concurrencia PostgreSQL. La imagen propia todavía no es una oferta del portal.

Ampliación por el fallo TLS: 26 pruebas dirigidas de bootstrap, diagnóstico y registry aprobadas.
Incluyen errores cerrados sin secretos, diagnóstico que no aplica cambios y handshake X.509
estricto. Es una selección parcialmente superpuesta con la anterior; no se suman los conteos.
