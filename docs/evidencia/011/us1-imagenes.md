# Imágenes propias — avance; aceptación Proxmox pendiente

## Componentes implementados (27/10/2026)

- Resolver OCI sin daemon ni ejecución: normaliza referencia, verifica índice,
  plataforma/manifiesto/config y hashes/tamaños. No descarga capas ni infiere
  espacio descomprimido desde el tamaño comprimido. Rechaza capas con URLs
  externas y exige persistencia declarada para Config.Volumes.
- Perfiles institucionales de registro: Host/SNI/CA sobre IP autorizada en cada
  conexión, sin proxies ambientales, redes de administración/loopback ni scopes
  libres. Credenciales de lectura en archivo privado, no en formulario/documento.
- Token realm/service/scope fijos. Sólo blobs pueden seguir un salto a un CDN
  registrado; sin credenciales del registry, con DNS/TLS y hash final comprobados.
  Transporte HTTP de bajo nivel evita el log de URLs firmadas de AsyncClient.
  La lista Docker Hub incluye CloudFront conforme a la
  [lista oficial de Docker](https://docs.docker.com/desktop/enterprise/allow-list/).
- POST `/templates/aplicaciones` y `/templates/{id}/configuracion`: rol/CSRF,
  idempotencia, revisión esperada y configuración inmutable. Validación externa
  sin transacción SQL, revalidación de rol/perfil/registry al commit. Configuración
  y oferta atómicas, sin invitado/reserva/borrador visible. Revisar la oferta no
  cambia asignaciones ya aprobadas ni configuraciones anteriores.
- Ventana única con Biblioteca / Imagen Docker. Alta propia: nombre/imagen/puerto,
  opciones plegadas, valores privados declarados sin ingresarlos al agregar.
  Progreso explícito, errores que conservan datos y clave de reintento estable.
  Edición de nombre/descripción/tamaño de estas ofertas no exige una definición
  histórica ni cambia su origen. Acciones administrativas fuera de la vista docente.

Contratos usados: [OCI Distribution](https://github.com/opencontainers/distribution-spec/blob/main/spec.md),
[Image Manifest](https://github.com/opencontainers/image-spec/blob/main/manifest.md) y
[Image Config](https://github.com/opencontainers/image-spec/blob/main/config.md).

## Comprobaciones acotadas

- Resolver: 17 casos base aprobados; 9 adicionales de CDN/CA/cuerpo/archivos
  privados; un caso de tag cambiado. Repetición sólo tras corregir streaming de
  fixtures y validación de nombres de host. No se corrió suite general.
- Consulta HTTPS real a Docker Hub de `traefik/whoami:latest`, linux/amd64:
  índice `sha256:c4717a8d1f0134a7444e24f881160e033991f23027c6c5a9a3f8fd22e70d1d44`,
  manifiesto `sha256:80f8bb74f634d45d55967820a702c5fddf01cf92968bb29ed7a3573dd16b0e55`,
  config `sha256:cd370f99dbfb63a9541c3787c576352d0d22e78fa33ef9d831f97cbeee9667e9`.
  Se verificó el salto autorizado a CloudFront sin ejecutar la imagen ni crear oferta.
- API/servicio: 9 casos aprobados en 6,40 s (doble OCI y perfil certificado sólo de
  prueba): rol/CSRF, datos inválidos, replay, cero invitados/reservas, revisión
  inmutable y bloqueo cambiado durante validación externa.
- PostgreSQL aislado: una carrera real aprobada en 1,80 s; dos altas con la misma
  clave crean una sola oferta. El contenedor de tests estaba detenido: se arrancó
  sólo `nap009-tests-postgres_test-1`, sin tocar la DB del portal.
- Vitest: formulario + IaaS, 6 aprobadas; edición/catálogo histórico, 9 aprobadas.
  Playwright/Chromium: dos escenarios aprobados en 5,2 s, con API simulada; incluyó
  build, alta con error/reintento y catálogo docente sin administración. Inspección
  visual de escritorio oscuro y móvil 390 px sin desborde horizontal.

## Pendiente para aceptar US1

T039/T044–T047/T050: runtime/estrategia/borde/probes definitivos instalados en la VM,
perfil habilitado sólo tras gate real y aceptación de campus-demo, whoami, credencial
privada y persistencia. Este archivo **no acredita despliegue Docker real completo**.
No se habilitaron perfiles ni ofertas de producción con fixtures. La consulta real
OCI no prueba funcionamiento de la aplicación, recursos máximos ni Proxmox.

## Checkpoint del runtime Docker — 27/10/2026

Implementación en revisión: estrategia de cinco acciones cerradas dentro del LXC,
paquetes y manifiestos fijados, comando original de la imagen, volúmenes por
instancia y borde HTTPS Caddy. Las credenciales de descarga, valores privados de
la aplicación y claves TLS viajan sólo por el canal privado de su acción. Se
incorpora recibo durable del aislamiento y entrada privada concurrente con la
captura de salida para evitar bloqueos por buffers llenos.

Se instaló el paquete en Proxmox sin habilitar perfiles. Se generó una CA propia
del motor en el nodo; su clave privada permaneció allí. El ensayo final usó una
identidad nueva y el LXC temporal 900011, separado de Draw.io. **Se detuvo antes
del arranque del invitado**: Proxmox incluye `type=veth` en `net0` y la validación
lo rechazaba. El trabajo quedó `incierto`/`UNCONFIRMED`, sin disponibilidad ni
reintento automático. Se conservó ese resultado para diagnóstico.

La corrección en el repositorio admite exclusivamente `veth` o el campo ausente;
rechaza otros tipos y conserva las demás comprobaciones. Todavía no se distribuyó
esa corrección ni se repitió el ensayo real. No se acredita instalación Docker,
acceso, persistencia o credenciales privadas reales con este intento.

Validación acotada al cierre: **46 aprobadas y 2 integraciones omitidas** en
aislamiento, estrategia Docker, collector y guardas del ensayo; comprobación
adicional del paquete instalado de sólo lectura **1 aprobada**. Estas pruebas
locales no sustituyen el gate Proxmox.

Limpieza real confirmada: LXC 900011 ausente, sus discos ausentes y pool
`nap011-final-gate` eliminado. Sólo permanece el LXC 100 de Draw.io, detenido y
sin modificaciones de este ensayo. El registro de producción conserva cero
perfiles habilitados. Los recibos privados de trabajo/TLS/aislamiento se conservan
como historial; no reutilizar esa identidad ni repetir la ejecución incierta.

Se detiene el trabajo aquí a pedido de Mauro. T039/T044–T047/T050 y la aceptación
completa de US1 siguen pendientes; próximo paso: revisar el cierre del ensayo
incierto, distribuir la corrección y validar con una identidad nueva.

## Convergencia Phase 9 (28/10/2026)

- **Diagnóstico de pedidos #34, #35 y #36**: fallaron en etapa 1 (`preparacion`) con `perfil_aplicacion_no_disponible` porque un script manual previo (`activar-perfil-nodo.py`, ya eliminado) escribió en `/etc/nap/applications-011/runner.json` y en `settings.json` una validación `proxmox_real` no ejecutada con kernel `6.8.12-2-pve`, mientras el nodo real corre `7.0.2-6-pve`, provocando `estado: bloqueado` / `motivo_codigo: PLATFORM_CHANGED` al consultar `action: profiles`.
- **Reversión y limpieza local completadas (`T107`, `T110`–`T114`)**:
  - Se revirtió `docker-ubuntu24:1` en `settings.json` del portal a `pendiente_validacion` (`VALIDATION_REQUIRED`).
  - Se regularizaron los pedidos #34, #35 y #36 (cerrados como rechazados sin recursos, liberando sus compromisos de capacidad) y se retiraron las ofertas `nginx`, `mariadb` y `phpmyadmin` atadas a los hashes inválidos `0b62d4df…` y `66d5e2ee…` (`T113`).
  - Se incorporó el preflight del nodo (`verify_node_profile` vía `action: profiles`) en `evaluacion_service.py` y `admision_service.py` antes de reservar o despachar (`T110`), la explicación en lenguaje cotidiano en `ProgresoDespliegue.jsx` (`T111`), y la actualización en un clic (`Requiere actualizar` → `POST /templates/{id}/configuracion`) en `Definiciones.jsx` cuando cambie el hash del perfil (`T112`).
  - Se completaron `docs/evidencia/011/perfil-docker.md` (`T044`), `backend/tests/test_orquestacion_aplicaciones_011.py` (`T037`/`T047`), `infra/applications/tests/test_docker_runtime.py` (`T039`) y la reparación de las 7 pruebas Vitest (`T114`).
- **Compuerta física Proxmox real ejecutada y aprobada (`T106`, `T108`, `T109`/`T050`)**:
  1. Se retiró de `/etc/nap/applications-011/runner.json` la entrada no validada `docker-ubuntu24:1` (`T106`).
  2. Se distribuyó el paquete definitivo al nodo Proxmox `172.16.36.100` (`policy_digest = 73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2`, `code_sha256 = 86e2bf133422a7c435f68c3e0a8e0485284cf3e7784da0477f22783011e1433c`), incorporando `net0.type=veth`, `umask=0o022` en los subprocesos de `pct`, espera de ruta por defecto en `bootstrap_docker`, compatibilidad con `manifest_digest` en `docker image/container inspect` de Docker 29 (`overlayfs`) y `--cap-add=NET_BIND_SERVICE` en el contenedor de borde `caddy` (`T108`).
  3. **Caso 1 (`docker.io/traefik/whoami@sha256:80f8bb74f634d45d55967820a702c5fddf01cf92968bb29ed7a3573dd16b0e55`)**:
     - `execution_id`: `4bba6281-3a9a-40ef-891d-49e122729537` sobre `LXC 900011` (`172.16.36.81`).
     - Resultado: `estado = confirmado`, `fase = finalizada`, `comprobaciones = ['aislamiento', 'runtime', 'salud', 'acceso_web']`, `recurso_configurado = True`, `last_source_seq = 11`.
     - Verificación externa HTTPS: `GET https://app1.nap011.test:8443/` con SNI y CA del nodo → `HTTP 200` sobre `TLSv1.3`.
     - Limpieza confirmada: `{"state": "cleaned", "guest_absent": true, "disks_absent": true, "vmid": 900011}`.
  4. **Caso 2 (`172.16.36.1:5443/nap/campus-demo@sha256:5cf44a35a166574041c678916d119f3b7ab96d6d427394a36160b299662b618d`, registry privado autenticado `campus-registry` y volumen `/data`)**:
     - `execution_id`: `d07d3250-aba2-463f-8ce6-b8c20e7e806c` sobre `LXC 900011` (`172.16.36.81`).
     - Resultado: `estado = confirmado`, `fase = finalizada`, `comprobaciones = ['aislamiento', 'runtime', 'salud', 'acceso_web']`, `recurso_configurado = True`, `last_source_seq = 12`.
     - Credenciales efímeras de pull retiradas (`/run/nap-pull-*` ausente; `/run/nap-docker-cli/config.json` con `{"auths":{}}`).
     - Persistencia verificada sobre HTTPS (`https://app1.nap011.test:8443`): `GET /health` → `200`, `POST /api/note` (`{"note": "Persistencia gate final 011"}`) → `200`, reinicio de contenedor `nap-e80c4dd90720498c96c8d6167ab9b2d4` y posterior `GET /api/note` → `200 {"note": "Persistencia gate final 011"}`.
     - Limpieza confirmada: `{"state": "cleaned", "guest_absent": true, "disks_absent": true, "vmid": 900011}`; `CT 100` (Draw.io) preservado sin cambios.
  5. **Habilitación sincronizada (`docker-ubuntu24:1`)**:
     - Plataforma observada del nodo: `{"pve": "9.2.2", "kernel": "7.0.2-6-pve", "arquitectura": "amd64"}`.
     - `perfil_sha256`: `2ed42514102e2f2ed7702bf4f1162f4ba2b6c175f2012f929c0895e743f67a24`.
     - Aplicado idéntico en `/etc/nap/applications-011/runner.json` (nodo) y `/home/mauro/.local/share/nap010/privado/settings.json` (portal), verificado con `require_profile` y `verify_node_profile` contra el nodo real.

