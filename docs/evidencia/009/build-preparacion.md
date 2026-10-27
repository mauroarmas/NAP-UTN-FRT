# Insumos reales para construir las referencias

Todavía no hay imágenes saneadas, manifiestos publicados ni ensayos PVE de productos. Esta evidencia registra solamente insumos y construcción aislada del inventario; no sustituye T101/T102.

## Base Ubuntu

Se descargó `ubuntu-base-24.04.5-base-amd64.tar.gz` (30.028.293 bytes) del [directorio oficial Ubuntu Base 24.04](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/). SHA-256 comprobado contra SHA256SUMS:

```text
e77b6f10c2590cef872b33ee9f635a0e3fd1f57fb074c0e52b5c7f56147a0c86
```

La firma SHA256SUMS.gpg aprobó `gpgv` con el keyring Ubuntu ya instalado. Firmante: Ubuntu CD Image Automatic Signing Key (2012), huella `843938DF228D22F7B3742BC0D94AA3F0EFE21092`. No se importó una clave de un servidor externo para aceptar esta descarga.

Archivo, sumas firmadas y `procedencia.json` están en `/home/mauro/.local/share/nap009/build/base/`. Se importó esa base verificada a Docker como `nap009-ubuntu-base:24.04.5-e77b6f10c259`, ID `sha256:949a44ec43c99a4acb953bbd7db1f6d74bb14de9e5b5ed193760de118e7ec878`. No es una referencia preparada para cátedras.

## Revisión de las recetas

Se creó un repositorio de fuentes de construcción independiente en `/home/mauro/.local/share/nap009/build/source/`. Contiene exclusivamente recetas, constructor/saneador y contratos necesarios, con procedencia del árbol de trabajo y SHA por archivo. La rama del proyecto continúa en `009-remediar-hallazgos-cierre`; no se creó un commit sobre sus cambios ni se incorporaron modificaciones ajenas.

Revisión actual del snapshot con el ayudante de resolución y reutilización de los índices APT ya verificados:

```text
99e86b9b7a18f644a1d5c24d70aeb86c55fca346
```

Las tres recetas aprobaron la función real `verify_recipe_revision` contra la revisión anterior `f65ca871705831c6abaf07a0828747580f537cdb`, sin sustituir el verificador; las recetas de producto no cambiaron después. Se conservan ambos bundles, incluido `/home/mauro/.local/share/nap009/build/fuentes-recetas-99e86b9b7a18.bundle`, para recuperar las fuentes Git junto con los artefactos futuros. Esos commits describen fuentes del constructor, no la entrega completa de la feature.

## Resolución exacta de paquetes

Se agregó el ayudante `infra/services/resolve.Dockerfile` y `resolve_packages.py`. Instala paquetes de uno de los tres productos cerrados en una copia Docker de la base, con policy-rc.d que impide iniciar servicios, y obtiene el inventario completo con dpkg-query. PostgreSQL/PHP/MariaDB se identifican por su binario real. El resultado se etiqueta `resolucion_sin_saneamiento_ni_validacion`; no inventa checks ni evidencia de acceso.

Comando de resolución Linux completado:

```bash
docker build -f /home/mauro/.local/share/nap009/build/source/infra/services/resolve.Dockerfile \
  --build-arg BASE_IMAGE=nap009-ubuntu-base:24.04.5-e77b6f10c259 \
  --build-arg PRODUCT=linux -t nap009-resolved-linux:24.04.5 \
  /home/mauro/.local/share/nap009/build/source/infra/services
```

Las tres resoluciones terminaron y se extrajeron los inventarios exactos, con lock completo y versiones de binarios:

| Producto | Imagen Docker local | Paquetes | Versión observada |
|---|---|---:|---|
| Linux | `nap009-resolved-linux:24.04.5` | 149 | Ubuntu Base 24.04.5 |
| PostgreSQL | `nap009-resolved-postgresql:24.04.5` | 169 | PostgreSQL 16.15 |
| BookStack, dependencias | `nap009-resolved-bookstack:24.04.5` | 250 | PHP 8.3.6 / MariaDB 10.11.14 |

Inventarios/locks: `/home/mauro/.local/share/nap009/build/{linux,postgresql,bookstack}-paquetes.json`. Logs en el mismo directorio con sufijo `-resolucion.log`. PostgreSQL y BookStack reutilizaron la base Linux y sus índices APT verificados para evitar repetir la descarga; no se omitió la comprobación de paquetes. La descarga inicial de APT tardó aproximadamente seis minutos. No se instalaron paquetes de productos en Proxmox.

## Construcciones terminadas

Se construyó `infra/services/build-host.Dockerfile` con herramientas instaladas desde `host-requirements.lock --require-hashes`. La fuente/base/plan se montan sólo lectura; los contenedores de build tienen límites de CPU/RAM/pids y no acceden al socket Docker. Los paquetes `.deb` de las imágenes resueltas se reutilizan con `--apt-cache`: APT verifica sus hashes contra los índices firmados y el inventario completo debe coincidir con el lock.

Las tres imágenes finales están construidas y saneadas, incluida la aplicación BookStack con vendor y lock verificados. Las salidas actuales son `/home/mauro/.local/share/nap009/build/salidas/{linux,postgresql,bookstack}-1.0.0-salud`. Cada directorio contiene imagen, bundle y `manifest-draft.json`. La revisión Git del snapshot separado es **20ba2a308ae6d79b781c35d9800f1bb51f109638**; se conserva su bundle de fuentes. Esta revisión reemplaza las construcciones anteriores: corrige COMPOSER_HOME, limpia la caché APT y distingue fallos funcionales de sondeo de fallos de transporte. El repositorio principal sigue sin commits nuevos.

Hashes, tamaños e inventarios actuales: [imagenes-construidas.json](imagenes-construidas.json). Se verificaron los archivos reales y sus tar: cuentas bloqueadas, sudo SUID, ausencia de claves SSH, contraseñas/base de aplicación, archivos privados de root y caché APT; BookStack conserva vendor pero no .env. Suite infra:73 pruebas aprobadas/4 optativas omitidas. Estas comprobaciones locales **no** acreditan acceso, persistencia o aislamiento en PVE.

Los tres manifiestos se guardaron por API autenticada como **borradores** en la DB de laboratorio55433. No se validaron/publicaron ni se subieron invitados. Pendientes: registro root de bundles, red/DNS/TLS por instancia, ACL y gate de consola T101, dos ensayos por producto y acceso desde otra computadora T102. Estos ayudantes no asignan IP/DNS/certificados ni completan el gate de consola.
