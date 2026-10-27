# Traspaso de NAP — 27/10/2026

## Estado que recibe el compañero

Continuar la rama **`011-desplegar-servicios-universitarios`**, no crear otra spec
ni volver a implementar 009/010. El checkpoint de código previo a este traspaso
es `597713e`; el traspaso agrega configuración, documentación y limpieza básica.
`tasks.md` tiene **38 de 105 tareas verificadas**. Varias tareas pendientes tienen
código parcial: leer sus pruebas y evidencias antes de decidir qué falta.

Objetivo: un pequeño AWS sencillo para la universidad. Dos entradas al catálogo:
imagen Docker propia y aplicación compatible de Community Scripts. Agregar una
oferta no crea LXC ni reserva capacidad; aprobar un pedido reserva y su despliegue
instala/verifica una instancia independiente por cátedra.

## Decisiones que deben conservarse

- UI breve, lenguaje cotidiano y feedback de progreso/error/éxito. Cátedra:
  aplicación o **Otro**, propósito/justificación y fechas; sin hardware.
- Admin aprueba, rechaza o **pide aclaración**, con aviso por correo. Sin cuotas
  previas por cátedra; capacidad al aprobar y despliegue desde fecha inicial.
- Sin preparar/confirmar/publicar manualmente, sin Guardadas y sin ensayo de
  oferta de 24 h. Las vigencias académicas sí se conservan.
- Small: 1 vCPU/512 MB/4 GB; Medium: 2 vCPU/1024 MB/8 GB. Respetar mínimos reales:
  el runtime Docker candidato sólo admite Medium, no forzar Small para mostrarlo.
- LXC únicamente. Docker usa Ubuntu 24.04; Community pilotos Debian 13. IaaS
  conserva Ubuntu 24.04 y Debian 13. No fallback privilegiado, unconfined o QEMU.
- Consola de instalación **de lectura**, negra con texto blanco, sólo admin;
  cátedra ve resumen. No es una shell ni reemplaza la consola IaaS.
- No copiar contraseñas NAP a aplicaciones. Acceso web mediante gateway aislado;
  no prometer SSO para cualquier producto. MFA del portal es opcional.
- Pruebas afectadas una vez por bloque; repetir si cambia/falla. Regresión completa
  sólo en hitos. Pruebas simuladas y build no acreditan Proxmox real.

## Mapa del código y lo ya construido

| Área | Dónde mirar | Situación |
|---|---|---|
| Esquema 011 | `backend/alembic/versions/`, `backend/app/models/` | Revisión actual `011_01_despliegue_aplicaciones`; configuración inmutable, secretos, intentos, consola y slots. |
| Contratos/perfiles | `infra/applications/job/`, `infra/applications/profiles/`, `backend/app/schemas/application_profiles.py` | Protocolo cerrado, identidad, perfil ligado a plataforma/código, replay, estado durable. |
| Ejecución root | `job/supervisor.py`, `worker.py`, `runtime.py`, `infra/runner/node_executor.py` | Unidades systemd, canal privado, captura/redacción y salida durable. No shell libre por SSH. |
| Red/TLS | `job/network.py`, `isolation.py`, `tls.py` | Política por instancia antes del arranque, recibos y TLS por identidad; integración real final pendiente. |
| Imágenes OCI | `backend/app/services/oci_registry_service.py`, `configuracion_despliegue_service.py` | Resolución de digest/plataforma, destinos permitidos, alta/revisión idempotentes sin CT/reserva. |
| UI de imagen propia | `AplicacionPropiaForm.jsx`, `AgregarServicioModal.jsx`, `TemplatesAdmin.jsx` | Nombre/imagen/puerto y opcionales, errores conservan formulario; entrada integrada al catálogo. |
| Runtime Docker | `infra/applications/docker/`, `profiles/docker/ubuntu24.json` | Estrategia parcial definitiva: paquetes/digests fijados, comando original, volúmenes propios, Caddy/TLS/probes; pendiente gate real completo. |
| Gateway/entrega | `application_target_service.py`, `application_proxy_service.py`, `application_websocket_service.py`, `application_verification_service.py`, `application_gateway.py` | Rama genérica web construida, controles de destino/cookies/autorización, entrega después de comprobación; TCP pendiente. |
| Históricos 009/010 | `infra/services/`, `infra/runner/`, servicios `biblioteca*`, `ensayo*` | Draw.io/IaaS siguen usando partes del legado. No borrarlo por no pertenecer al motor nuevo. |

Los nombres sin directorio del backend en la tabla corresponden a
`backend/app/services/` salvo `application_gateway.py` en `backend/app/`;
los componentes pertenecen a `frontend/src/components/` y las páginas a `frontend/src/pages/`.

## Bloqueo exacto al detener el trabajo

El spike Docker anterior pasó, pero **no era el runtime definitivo**. Su último
ensayo con el worker nuevo se bloqueó antes de arrancar el LXC: Proxmox agrega
`type=veth` en `net0`, y el validador no lo admitía. Resultado correcto del trabajo:
`incierto`/`UNCONFIRMED`; no se anunció aplicación disponible ni hubo reintento.

El repositorio ya admite `type=veth` o ausencia del campo y rechaza otro tipo,
con pruebas. **Esa última corrección no está distribuida al nodo**. Se retiraron
el CT temporal 900011, sus discos y el pool `nap011-final-gate`; los recibos
privados del trabajo incierto se conservaron. No reutilizar su identidad ni
repetir su ejecución. El instalador puede bloquear una actualización si ve un
trabajo incierto: reconciliar su estado con ausencia real y unidad detenida,
preservando historial, antes de otro intento; no debilitar esa guarda.

En Proxmox de Mauro sólo quedó CT **100**, Draw.io, **detenido** al último control.
No se lo detuvo como parte del ensayo. No modificarlo para limpiar la 011.
El registro del motor definitivo conserva **cero perfiles habilitados**.

Último cierre: 46 pruebas afectadas aprobadas/2 integraciones omitidas y otra
prueba del paquete de sólo lectura aprobada. Hubo pruebas HTTPS OCI reales,
una carrera PostgreSQL y pruebas UI con API simulada; detalles y límites en
`docs/evidencia/011/us1-imagenes.md`. No repetir la suite general por rutina.

## Orden recomendado para continuar

1. Leer `AGENTS.md`, constitución y spec/plan/tasks/contracts/quickstart de 011.
   Confirmar qué cambios locales recibió el clon y revisar T008/T023/T032/T034/T037
   y T039/T044–T047: contienen trabajo parcial, no empezar de cero.
2. Revisar el cierre seguro del ensayo incierto. Si se usa otro nodo, crear
   identidades/red/perfiles propios; los UUID, certificados y recibos de Mauro
   no acreditan otra instalación.
3. Distribuir la corrección de `net0.type` y completar T050 con runtime definitivo:
   whoami, campus-demo con persistencia y registry privado, aislamiento y secretos.
   Habilitar el perfil únicamente tras ese gate. Hoy el candidato es Medium.
4. Completar Community T051–T064 usando los locks y la factibilidad existentes:
   MariaDB y Caddy. No ejecutar el wrapper de Community Scripts en el nodo ni
   admitir cualquier resultado de búsqueda como instalable. Categorías y motivos
   claros para aplicaciones aún incompatibles.
5. Completar pedidos/agenda/secretos/avisos T065–T076, consola T077–T087,
   recuperación/operaciones T088–T098 y cierre T099–T105 siguiendo dependencias.
   Hay piezas comunes ya hechas; verificar antes de duplicarlas.

## Replicar el portal con los datos actuales

Requisitos: Git, Python 3.11+ para el helper y Docker con Compose v2. Backend
usa Python 3.12 y PostgreSQL 16; frontend Node 22 >=22.12. Docker trae esas
dependencias, sin exigir instalar Python/Node del proyecto en el host.

Clonar la rama indicada. Los archivos privados de Mauro **no vienen con Git**.
Recibir por canal privado el directorio de exportación con estos tres archivos:

- `portal.dump`: esquema, datos, secuencias, índices, constraints y versión Alembic.
- `keyring.json`: claves Fernet necesarias para descifrar registros existentes.
- `manifest.json`: hashes y recuentos obtenidos tras restauración real aislada.

Guardar fuera del repositorio, directorio 0700 y archivos 0600. El dump contiene
cuentas, hashes, sesiones e identidades: tratarlo como privado aunque sean datos
de prueba. No pegarlo en Claude, Git, issues o logs. El export no contiene el
token PVE, SSH, contraseñas root, configuración privada completa ni discos LXC.

Si Mauro entrega `nap-traspaso-db-2026-10-27.tar.gz`, extraerlo como usuario normal,
sin sudo, dentro de una carpeta privada nueva. El paquete contiene exactamente
los tres archivos anteriores. Su SHA-256 y las verificaciones del traspaso están
en [la evidencia](evidencia/011/traspaso.md). No viene en el clon de Git.

En los ejemplos, sustituir `/ruta/privada/traspaso` por la carpeta recibida:

```bash
python3 scripts/traspaso.py verify --directory /ruta/privada/traspaso
python3 scripts/traspaso.py init --keyring /ruta/privada/traspaso/keyring.json
docker compose -p nap-handoff -f docker-compose.handoff.yml build
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d --wait db
python3 scripts/traspaso.py restore --directory /ruta/privada/traspaso
docker compose -p nap-handoff -f docker-compose.handoff.yml run --rm --no-deps api alembic upgrade head
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d
```

**No ejecutar `alembic upgrade head` antes de importar el dump completo**: necesita
una base vacía. El helper rechaza otro proyecto Compose, API encendida o tablas
existentes; restaura en una transacción, sin `--clean`, y compara recuentos/revisión.
Si falla, no borrar volúmenes para reintentar: revisar la causa. El nombre por
defecto del contenedor es `nap-handoff-db-1`; admite `--container` si Compose usa otro.

`init` nunca sobrescribe `.env`. Genera claves JWT/CSRF **nuevas** para este portal,
invalidando los JWT de la instalación anterior; importa únicamente el keyring de
datos. No regenera el keyring de la copia. Las cuentas y contraseñas actuales
permanecen: coordinar su acceso con Mauro de forma privada. Bootstrap no reemplaza
cuentas existentes y no hay contraseña predeterminada soportada.

El helper `verify` restaura en PostgreSQL 16 temporal, sin red ni puertos, compara
recuentos y elimina ese contenedor al terminar. Puede descargar su imagen si falta.
No realiza pruebas Proxmox ni de contenido de aplicaciones.

Para generar un corte actualizado desde la instalación original (API encendida
y acceso Docker local): `python3 scripts/traspaso.py export --directory /ruta/privada/nuevo-corte`.
La carpeta debe ser nueva y estar fuera de Git. Usa `ps_postgres`/`ps_backend` por
defecto; ambos nombres admiten opciones CLI. `pg_dump` mantiene una instantánea
consistente sin detener la API. El corte se entrega por canal privado junto con
su keyring; exportar no modifica los datos de origen.

Sin copia recibida, usar `python3 scripts/traspaso.py init`, levantar DB/build como
arriba y migrar la base vacía. Luego crear **una vez** el administrador:

```bash
docker compose -p nap-handoff -f docker-compose.handoff.yml run --rm api python -m scripts.bootstrap_admin --actor operador_local
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d
```

Portal `http://localhost:5174`, API `http://localhost:8001/api/docs`, correo de prueba
`http://localhost:8025`, DB local 5434. Los puertos deben estar libres. El Compose
de traspaso publica sólo loopback, usa un volumen propio, no tiene scheduler ni
worker de notificaciones/despliegue y fuerza PVE sin credencial/perfiles vacíos.
Se puede revisar UI/datos y desarrollar; capacidad, inventario y acceso a servicios
reales no funcionarán hasta configurar infraestructura. No interpretar ese estado
como pérdida de las plantillas o defecto del dump.

## Lo que requiere configuración aparte

La DB no mueve el Proxmox ni las instancias. Deben acordar si seguirán en la VM de
Mauro o en otra. No conectar dos portales/workers activos al mismo inventario con
copias de la misma DB. El clúster y la red universitarios aún no están configurados.

Inventario del equipo original, para diagnóstico, no para copiar rutas al clon:

- Proxmox `172.16.36.100`, VM VMware; red de invitados anidados requiere tráfico
  permitido en vmnet8. No aplicar esa excepción en otro equipo sin diagnóstico.
- Privados `~/.local/share/nap009`, `nap010`, `nap011`: configuración, known_hosts,
  claves dedicadas, bundles, TLS y recibos. Los lanzadores `.sh` de esa carpeta
  **no están versionados**; no asumir que existen en la computadora del compañero.
- Registry de ensayo `172.16.36.1:5443`, builder `nap010-builder`, gateway
  `nap010-app-gateway`, nombres `*.nap-apps.test:8443`. NFS limitado a artefactos;
  no comparte claves TLS de aplicaciones. API/worker usan UID 10001 para archivos
  privados; builder/root tienen permisos diferentes.
- Runtime del nodo `/etc/nap/applications-011/runner.json`, estado
  `/var/lib/nap-application-jobs`, aislamiento `/var/lib/nap-application-isolation`
  y PKI `/etc/nap/applications-011/pki`. No exportar la CA privada del nodo al clon.

Procedimientos versionados: `infra/applications/install.py`,
`infra/laboratorio/011/preparar_entorno.py`, `preflight.py`,
`validar_motor_docker.py` y su README; configuración operativa por archivos privados
con `NAP_SETTINGS_FILE`, según `DOCKER.md` y `docs/conexion-infraestructura.md`.
El gate final de laboratorio tiene VMID/pool acotados y estado root privado:
leer sus guardas antes de usarlo; no es un instalador genérico para otra universidad.

Si necesitan reproducir el laboratorio completo, pedir a Mauro los **datos de
configuración necesarios** y preparar credenciales nuevas/rutas locales; Git +
dump sólo reproducen el portal y los registros. El código conserva las guardas
para no dar por configurada una infraestructura inexistente.

## Pruebas al continuar y limpieza realizada

Instalación local de dependencias y comandos: READMEs backend/frontend. Ejecutar
sólo los tests de los módulos modificados. PostgreSQL concurrente usa
`docker-compose.test.yml` y `TEST_DATABASE_URL` aislada; nunca el dump de trabajo.
Las suites infra se corren con `-c infra/pytest.ini`; una integración real exige
`NAP_INFRA_INTEGRATION=1` y revisar primero su destino.

La limpieza retira `setup_usuarios_solicitados.py` (contraseñas fijas y modificación
de cuentas), seis wrappers/alias sin consumidores en frontend y texto de Vite.
No borra migraciones, pruebas, bitácoras ni servicios históricos por apariencia de
desuso. El backend aún tiene compatibilidad 009/010 intencional. Priorizar la 011
antes de una refactorización general que pueda romper el flujo funcional.
