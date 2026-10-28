# Implementation Plan: aplicaciones desde Docker Hub e imágenes propias

**Branch**: `011-desplegar-servicios-universitarios` | **Updated**: 2026-10-27 | **Spec**: [spec.md](spec.md)

## Summary y reducción de alcance

Una única estrategia Docker/OCI con dos entradas al catálogo: buscar en **Docker Hub**
o ingresar una **imagen propia** en registry público/institucional autorizado. Ambas
convergen en la configuración `imagen_docker` ya construida; no duplicar resolución,
aprobación, reserva, instalación, consola ni lifecycle por procedencia de la imagen.

Community Scripts se retira por decisión de Mauro. No construir Core/harness, locks
APT, perfiles específicos MariaDB/Caddy ni otro runtime. Los spikes, recibos y esquemas
históricos se conservan; no convierten tareas retiradas en tareas completadas.
Ver [cambio de alcance y tareas retiradas](cambio-alcance-oci.md).

El alta sólo registra la oferta. La aprobación congela configuración/recursos; al
inicio autorizado se crea un LXC propio Ubuntu 24.04 no privilegiado y se ejecuta Docker
dentro. No instalar Docker en el nodo PVE. IaaS conserva Ubuntu 24.04 y Debian 13;
Draw.io y artefactos 009/010 conservan sus accesos e historial.

## Technical Context

- **Stack**: Python 3.12/FastAPI/SQLAlchemy async/PostgreSQL 16/Alembic; React/Vite;
  HTTPX, cryptography, OpenSSH y systemd existentes. Mantener locks y arquitectura.
- **Datos**: configuración inmutable, snapshots, secretos cifrados por pedido,
  operación/intento, slots e ingesta de consola ya implementados parcialmente.
- **Runtime**: Docker en Ubuntu 24.04/LXC, arquitectura inicial amd64, versiones y
  manifiestos fijados; comando original de la imagen. Sin Compose, builds desde
  código, flags libres, Docker socket, privilegios o montajes del nodo.
- **Recursos**: Small 1 CPU/512 MB/4 GB; Medium 2 CPU/1024 MB/8 GB. Candidato Docker
  Medium hasta medir Small. Rechazar mínimos superiores; no cambiar tamaños para aprobar.
- **Consola**: systemd independiente de SSH/UI, spool depurado, ingesta/polling 1 s;
  10 000 000 bytes por raíz/30 días, p95 <=5 s y apertura <=3 s. Sin shell o xterm.
- **Validación**: pruebas afectadas por bloque y PostgreSQL aislado para carreras.
  Gate PVE real del runtime definitivo antes de habilitar perfil; laboratorio no
  acredita la red universitaria. No añadir broker, orquestador o servicios nuevos.

## Diseño de biblioteca Docker Hub

Reutilizar pantalla/modal/componentes y ruta `/biblioteca/aplicaciones`. Cambiar el
proveedor de descubrimiento; no mantener dos bibliotecas de aplicaciones en paralelo.
Buscar por nombre y paginar de forma acotada; mostrar repositorio, descripción,
procedencia y distintivos confiables disponibles. No atribuir datos ausentes a la API.
Categorías sólo si la API elegida las ofrece; su ausencia no bloquea la entrega.

El API de distribución OCI resuelve manifiestos/blobs, no define el buscador Hub.
El adaptador de búsqueda consulta endpoints fijos revisados de Docker Hub con timeout,
límites y errores explícitos. La selección genera una referencia de imagen y reutiliza
`oci_registry_service` y `configuracion_despliegue_service` de US1: verifica DNS/IP/TLS,
realm, plataforma, digest, Config.Volumes y perfil. La ficha no habilita la oferta.
No ejecutar el contenido de Dockerfile, README o comandos del proveedor.

La UI abre el mismo formulario breve precargado, pide los datos faltantes y confirma
«Disponible para solicitar». Fallo/rate limit: reintento o ingreso manual de referencia,
sin confundirlo con cero resultados. No construir espejo, caché o gestión de cuentas.
Un perfil pendiente/bloqueado informa su impedimento, también para imágenes oficiales.

## Ejecución y acceso comunes

1. Alta valida referencia/perfil y registra configuración/oferta atómicas e idempotentes,
   sin CT/reserva. Edición crea revisión; no cambia decisiones aprobadas.
2. Aprobar revalida permisos, snapshot, mínimos y capacidad bajo lock. Genera/reutiliza
   secretos por pedido, reserva y admite/programa desde fecha inicial. Otro y aclaración
   conservan su flujo y avisos; no pedir hardware a cátedra.
3. Crear identidad/nonce e intento antes del efecto; reservar slot y crear CT detenido
   con marcador exacto. Imponer aislamiento externo y TLS por identidad antes de start.
4. Unidad root fija conduce las acciones Docker: paquetes fijados, pull por digest,
   credencial privada efímera, volúmenes propios, borde HTTPS y comprobación de acceso.
   No registrar valores privados ni permitir que el origen de búsqueda modifique permisos.
5. Ingerir cursor final/ACK, reobservar propiedad/configuración y probar acceso antes de
   transicionar a ACTIVO y avisar. La consola no convierte `exit 0` en entrega.
6. Stop/start/restart conservan datos/secretos. Reintento incierto exige reconciliación;
   eliminación sólo de recursos propios, capacidad/red libres después de ausencia confirmada.

Gateway genérico separado del portal y Draw.io intacto: IP/Host/SNI/CA fijos, cookies
nativas aisladas, streaming acotado, WS sólo declarado y revocación. TCP conserva su
contrato nativo y requiere perfil/autenticación comprobados; no se agrega un piloto ni
adaptador MariaDB por esta entrega ni se promete compatibilidad universal de puertos.

## Compatibilidad del esquema y retirada del proveedor anterior

No editar revisiones Alembic aplicadas ni resetear DB para quitar Community. El valor
`community_scripts` existe en modelos/fixtures; la implementación T062 deberá rechazar
altas y despacho nuevos por ese origen, manteniendo lectura histórica donde sea necesaria.
Retirar navegación/consultas/configuración por defecto del proveedor anterior, sin borrar
las rutas legacy necesarias para Draw.io, IaaS o auditoría. No migrar registros a OCI
inventando imágenes equivalentes. Las pruebas antiguas útiles se adaptan o conservan
como regresión, nunca se eliminan sólo para que el recorte parezca implementado.

## Mapa de implementación

- Backend: `services/oci_registry_service.py`, `configuracion_despliegue_service.py`,
  `biblioteca_service.py`, routers `templates`/`biblioteca`; servicios de admisión,
  orquestación, ingesta, acceso/gateway y agenda existentes.
- Infra: `infra/applications/docker/`, `profiles/docker/`, `job/` y
  `infra/runner/node_executor.py`; instalación y validación en `infra/laboratorio/011/`.
- Frontend: `AgregarServicioModal`, `BibliotecaAplicaciones`, `AplicacionPropiaForm`,
  aprobación/pedidos/servicios y consola de lectura, sin pantalla nueva de perfiles.
- Contratos: [configuración](contracts/configuracion.md), [API](contracts/api.md),
  [runner](contracts/runner.md), [acceso/UI](contracts/acceso-ui.md) y [modelo](data-model.md).

## Secuencia y aceptación proporcional

1. Revisar integración parcial T008/T023/T032/T034/T037/T039/T044–T047. Reconciliar el
   gate incierto y distribuir la corrección `net0.type=veth` antes de otro ensayo propio.
2. Completar T050: runtime Docker definitivo con whoami y campus-demo; persistencia,
   registry privado, red, secretos y acceso comprobados. No repetir los spikes Community.
3. US2 reducida: T051/T054 tests; T062 adaptador Hub + retirada del proveedor;
   T063 UI con formulario común; T064 recorrido de búsqueda. Reusar T050 para las
   verificaciones del motor, no ejecutar toda la batería dos veces por las dos entradas.
4. Completar agenda/pedidos, consola y recuperación con el mismo motor según tareas.
5. Aceptación integrada de **dos imágenes**: whoami descubierto en Hub y campus-demo
   propia con dato persistente y pull privado; dos cátedras aisladas. Ensayos secuenciales
   si falta capacidad y dos operaciones simultáneas sólo para medir la consola.

Siguen vigentes los controles críticos de seguridad, datos y recuperación, así como
regresión de IaaS/Draw.io. No se requieren cuatro aplicaciones, perfiles Core o pilotos
MariaDB/Caddy. La búsqueda no exige API de categorías, caché local o una nueva spec.

## Constitution Check y trazabilidad

La constitución 4.2.0 conserva oferta/instancia, simplicidad, autorización, aislamiento,
capacidad atómica e historia. No prescribe Community Scripts; no necesita una enmienda
para retirar ese proveedor. Diseño conforme; PASS de diseño no acredita instalación.

| Requisitos | Diseño y aceptación |
|---|---|
| FR-001–005 | Un modal, dos entradas, un alta OCI sin recursos; US1 y T050 |
| FR-006–009 | Hub por nombre, categorías opcionales, digest/configuración común; US2 reducida |
| FR-010–017 | Pedido/Otro, aprobación/agenda, identidad, acceso y entrega comprobados |
| FR-018–024 | Consola durable, depuración/cursor/ACK, autorización y límites |
| FR-025–030 | Reconciliación, persistencia, limpieza, vigencias y legado intacto |
| SC-001–003/008 | Dos entradas <=3 min, pedido <=2 min; dos imágenes y dos cátedras |
| SC-004–007/009 | Medidas de consola, fallos, secretos y regresión del motor común |

El historial de investigación y factibilidad Community se conserva como descartado;
las instrucciones vigentes están aquí y en [quickstart.md](quickstart.md).
