# Traspaso verificado — 27/10/2026

No cambia el avance funcional de la spec: **38/105**; Docker definitivo continúa
pendiente de gate real. Guía vigente: [traspaso](../../traspaso-011.md).

## Exportación e importación reales

- Origen: portal local PostgreSQL 16; `pg_dump` con esquema y datos, sin escritura
  ni detención del portal. Revisión `011_01_despliegue_aplicaciones`.
- Restauración de la copia en PostgreSQL 16 temporal, `--network none`, sin
  puertos publicados y con datos en tmpfs. Constraints/índices/secuencias cargados
  por `pg_restore --single-transaction --exit-on-error`.
- Inventario: **50 tablas**, incluidos **7 usuarios, 24 cátedras, 3 pedidos y
  3 servicios**. Los recuentos completos y hashes están en el manifiesto privado.
- Segunda importación real mediante el helper `restore`, hacia un contenedor
  aislado con etiquetas del proyecto de traspaso: revisión y todos los recuentos
  coincidentes. Intentar importar otra vez sobre esa base no vacía fue rechazado.
- Ambos contenedores de verificación se retiraron. No se restauró ni se limpió
  la base del portal de origen. No se tocó Proxmox.

La primera verificación encontró una carrera con el servidor transitorio de
inicialización de la imagen PostgreSQL. El helper ahora espera el fin de initdb
y disponibilidad del servidor final; el corte definitivo y la importación posterior
pasaron. La carpeta incompleta de ese intento se retiró.

## Archivos entregables

Paquete privado fuera de Git:
`~/.local/share/nap011/nap-traspaso-db-2026-10-27.tar.gz`.
Contiene sólo `portal.dump`, `keyring.json` y `manifest.json`.

SHA-256 del paquete:
`51eb0fb0a129b04d12a1eb88f9e89e2f8fb6a7e0f2167f028c58bd09e7e3018f`.

La carpeta original del corte es
`~/.local/share/nap011/traspaso-final-2026-10-27/`.
Paquete/archivos tienen permisos 0600 y carpeta 0700. No contienen las
credenciales de PVE/SSH ni el .env original. Sí contienen datos privados de
autenticación del portal y su keyring: compartir únicamente por canal privado.

## Validación acotada del cambio

- 7 pruebas del helper: generación/importación de claves, no sobrescritura,
  permisos/enlaces, inyección por identificador, rechazo de export dentro del repo,
  destino ajeno y dump modificado.
- 11 pruebas frontend afectadas aprobadas: aplicación propia, IaaS y biblioteca.
- Build frontend aprobado y Compose de traspaso validado sin mostrar secretos.
- Importación PostgreSQL real y rechazo de reimportación sobre base no vacía,
  descritos arriba; no equivalen a restore operativo de LXC/archivos de aplicaciones.

Limpieza: script de restablecimiento con contraseñas fijas eliminado, seis
wrappers/alias frontend sin consumidores eliminados, texto sobrante de Vite
retirado y referencias antiguas de scheduler/correo/constitución corregidas.
Planes históricos identificados como tales e índice único de documentación.
No se eliminaron tests, migraciones, evidencia ni caminos históricos en uso.
