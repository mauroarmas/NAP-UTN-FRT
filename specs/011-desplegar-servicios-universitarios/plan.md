# Implementation Plan: Desplegar servicios universitarios

**Branch**: `011-desplegar-servicios-universitarios` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: `specs/011-desplegar-servicios-universitarios/spec.md`

## Summary

Agregar dos caminos declarativos al catálogo existente: imagen Docker propia e instalación
compatible de Community Scripts. El alta registra una oferta reutilizable sin crear invitados ni
reservar capacidad. La aprobación congela configuración y recursos; el despliegue usa un LXC propio
por servicio, conserva la máquina de estados/reservas y confirma disponibilidad antes de entregar.

NAP crea el LXC en ambos casos. Docker se ejecuta en un LXC Ubuntu 24.04 no privilegiado mediante
un perfil institucional cerrado; Community usa el instalador guest y Core fijados, nunca el wrapper
host que crea otro CT y sustituye su marcador. Los pilotos Community son MariaDB y Caddy sobre
Debian 13. Son candidatos de validación, no instalaciones ya probadas.

Un nuevo protocolo cerrado del runner administra trabajos duraderos del nodo. La consola negra
con texto blanco consulta registros depurados por cursor; no abre shell ni depende de la pestaña.
Se conservan los caminos históricos de Ubuntu/Debian y Draw.io. Diseño e interfaces detallados en
[research.md](research.md), [data-model.md](data-model.md) y [contracts/](contracts/).

## Technical Context

**Language/Version**: Python 3.12 en contenedores del portal; JavaScript/React 19.2 y Vite 8.3;
Python 3 estándar en el wrapper del nodo, con dependencias privadas sólo si las exige su paquete.

**Primary Dependencies**: FastAPI 0.157, Starlette 1.9, SQLAlchemy 2.0 async, asyncpg 0.30,
Alembic 1.16, proxmoxer 2.2, HTTPX 0.28, cryptography/keyring y OpenSSH existentes. systemd para
trabajos independientes; Docker Engine/API dentro de cada guest, no el daemon del nodo. Core
Community versionado y harness común. Mantener locks de dependencias; no añadir Celery, broker,
xterm ni un cluster de orquestación adicional.

**Storage**: PostgreSQL para configuración inmutable, snapshots, intentos, registros depurados y
reservas de red. Rootfs LXC para aplicación/volúmenes; spool privado y acotado en el nodo. No raw logs,
secretos ni estados de ejecución en almacenamiento del navegador. Artefactos privados verificados
para perfiles; secretos en keyring y canales efímeros, no en repositorio o imagen base.

**Testing**: pytest/pytest-asyncio, PostgreSQL 16 aislado para concurrencia/migración, fakes de PVE,
runner, registry y reloj; Vitest/Testing Library y Playwright. Ensayos reales separados en la VM
local para nested runtime, Core, red y persistencia. No ejecutados durante esta planificación.

**Target Platform**: portal Linux + Proxmox/LXC; laboratorio inicial amd64. Runtime Docker sobre
Ubuntu 24.04; perfiles Community iniciales Debian 13 según fuentes. TLS/red/permisos se preparan
una vez por infraestructura. La red universitaria sigue siendo una instalación distinta.

**Project Type**: aplicación web con API, worker existente y runner cerrado de infraestructura.

**Performance Goals**: alta <=3 min de interacción y pedido <=2 min; p95 captura→consola <=5 s con
dos instalaciones activas, apertura de registro <=3 s. Productor flush <=250 ms, ingesta <=1 s,
consulta visible <=1 s, páginas <=64 KiB; no prometer duración de descargas externas.

**Constraints**: Small 1 vCPU/512 MB/4 GB y Medium 2 vCPU/1024 MB/8 GB incluyendo plataforma y datos.
Conservadoramente habilitar Medium para perfiles iniciales hasta medir Small. Un perfil que exige
más recursos o permisos prohibidos queda bloqueado, sin reducir mínimos. Logs <=10 000 000 bytes
por raíz/30 días. Sin escritura de consola, Compose, builds desde código o SSO universal.

**Scale/Scope**: instalación universitaria pequeña, decenas de cátedras, un laboratorio inicial y
dos instalaciones activas por nodo. Resto queda en cola con capacidad reservada. Dos perfiles
Community y dos imágenes distintas prueban reutilización; ninguna app queda compatible sólo por
aparecer en la búsqueda. El diseño admite nuevos perfiles por datos dentro del mismo contrato.

## Constitution Check

*GATE: antes de Phase 0 y reevaluación tras Phase 1.*

La decisión de usuario sobre oferta/instancia se incorporó a la constitución **4.2.0** y a sus
plantillas. Se aplicó el hook de comprobación Git, que no modificó un repositorio ya existente.
No queda conflicto pendiente entre FR-003 y el Principio VII.

| Principio / gate | Comprobación de diseño | Pre / Post |
|---|---|---|
| I: gestión sólo en NAP | Routers→servicios→PVE/runner; ningún comando libre o wrapper host; consola de lectura no usa la excepción interactiva | PASS / PASS |
| II: estados centralizados | Transiciones por `pedido_service.transicionar`; autor sistema en agenda/reconciliación, historial y motivo | PASS / PASS |
| III: recuperación | Identidad y ejecución persistidas antes de efectos, fencing, inspección, deduplicación y ausencia antes de liberar | PASS / PASS |
| IV: aislamiento/capacidad | Reserva atómica existente, snapshot, red externa al guest, secretos/datos propios y sin cuotas anticipadas | PASS / PASS |
| V: historia | Revisiones inmutables, operaciones terminales conservadas, purga sólo de texto operativo | PASS / PASS |
| VI: roles | Cátedra aplicación/propósito/fechas y Otro; administración resuelve; consola/descarga sólo admin actual | PASS / PASS |
| VII: simplicidad | Dos orígenes, formulario breve; alta sin instancia, instalación por pedido; sin ensayos, publicación o evidencia manual | PASS / PASS |
| Stack y esquema | Stack constitucional conservado; nuevas tablas/FK por Alembic, compatibilidad aditiva | PASS / PASS |
| Fallo y concurrencia | Casos obligatorios de PVE/SSH/DB/registro y carreras reales en PostgreSQL incluidos en validación | PASS diseño / ejecución pendiente |
| Pruebas no simulables | Gates de runtime/Core/firewall/instalación/red identificados y perfiles no habilitados hasta comprobarlos | PASS declaración / ejecución pendiente |

Los PASS anteriores evalúan el diseño; no acreditan código ni infraestructura desplegados. Si el
spike sólo funciona con LXC privilegiado o protecciones desactivadas, el gate real falla y no se
habilita ese perfil. No se cambia a QEMU u otro alcance silenciosamente.

## Project Structure

### Documentation (this feature)

```text
specs/011-desplegar-servicios-universitarios/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── configuracion.md
│   ├── api.md
│   ├── runner.md
│   └── acceso-ui.md
└── checklists/requirements.md
```

`tasks.md` se generará con `/speckit-tasks`; este comando termina en diseño.

### Source Code (repository root)

Rutas existentes y propuestas para generar tareas, no archivos de implementación ya creados:

```text
backend/
├── alembic/versions/                         # migración aditiva desde 010_06
├── app/
│   ├── models/                              # configuración, secretos, intentos, consola, reserva de red
│   ├── schemas/                             # deployment discriminado y protocolo de trabajo
│   ├── routers/{templates,pedidos,operaciones,servicios}.py
│   ├── services/
│   │   ├── {perfiles,evaluacion,admision,orquestacion}_service.py
│   │   ├── {identidad_infra,reserva_red,service_access}_service.py
│   │   ├── configuracion_despliegue_service.py
│   │   ├── oci_registry_service.py
│   │   ├── application_job_client.py
│   │   ├── consola_operacion_service.py
│   │   └── despliegue_programado_service.py
│   ├── application_gateway.py                # adaptador web nuevo + Draw.io intacto
│   └── worker.py                            # agenda e ingesta corta, además de tick existente
└── tests/                                   # contratos/fakes; postgres/ para carreras y migración
infra/
├── runner/                                  # dispatcher nuevo protocolo, sin romper /1 histórico
├── applications/
│   ├── profiles/{docker,community}/          # perfiles institucionales y candidatos
│   ├── job/                                 # supervisor, spool y redactor comunes
│   ├── community/                           # harness/política común, fuentes fijadas
│   ├── docker/                              # runtime/probes/borde de acceso
│   └── fixtures/                            # demo universitaria para pruebas, no build del producto
└── laboratorio/                             # preparación una vez y verificaciones sin secretos
frontend/
├── src/
│   ├── components/{AgregarServicioModal,BibliotecaAplicaciones,ProgresoDespliegue}.jsx
│   ├── components/{AplicacionPropiaForm,ConsolaOperacion}.jsx
│   ├── hooks/useConsolaOperacion.js
│   ├── pages/{Definiciones,Pedidos,Servicios}.jsx
│   └── services/api.js
└── tests/                                   # Vitest y e2e de ambos caminos/consola
```

**Structure Decision**: extender monolito/worker/runner existentes con dos estrategias de ejecución
discriminadas por configuración. No dividir el producto en servicios de catálogo/pedidos nuevos;
el gateway sigue en origen distinto por seguridad, como en el laboratorio actual.

## Phase 0 — Research y decisiones cerradas

[research.md](research.md) documenta R01–R14 con fuentes y alternativas. Se investigaron Docker,
Community/Core y consola en paralelo mediante agentes de lectura. Hallazgos decisivos:

1. El wrapper host Community no preserva el marcador de NAP; usar instalador guest/harness.
2. Docker anidado requiere features/perfil probados y puede necesitar acción root cerrada del
   runner para `keyctl`, no otro token con privilegios globales.
3. Registro duradero necesita trabajo independiente de SSH; el runner actual es síncrono y acotado.
4. El contador actual de intentos no representa instalaciones; crear intento estable y raíz lógica.
5. La depuración ocurre antes de spool/journal/DB; Core tiene caminos de logs crudos que se adaptan.
6. No existe programación futura automática en el checkbox actual; implementarla explícitamente.
7. El pool histórico consume UUIDs de slots; asignaciones nuevas separan slot reutilizable e identidad.

No quedan decisiones de diseño sin resolver. Las pruebas de factibilidad física no se sustituyen
por documentación: son el primer gate de implementación.

## Phase 1 — Diseño de integración

### Alta y aprobación

- Nuevo POST de aplicaciones crea configuración inmutable + template tras validar datos, fuente,
  perfil, plataforma y acceso. No usa ensayo/preparación 010 ni afirma funcionamiento ya probado.
- `perfiles_service` distingue base IaaS, artefacto legacy y configuración declarativa; conserva las
  verificaciones históricas en sus ramas. Nuevo esquema no exige una evidencia legacy inexistente.
- Evaluación incluye hash de configuración/perfil y mínimos. Aprobación revalida bajo lock de
  capacidad, congela snapshot, crea secretos por pedido y reserva. No guardar secretos en la
  idempotencia de request/response; usar cifrado y fingerprint contextual.
- Solicitud de despliegue inmediata o programada es una decisión única en la UI. La agenda se
  vincula a la revisión aprobada y respeta inicio, gracia de reserva, revocación y actor sistema.

### Creación y ejecución

- Admitir operación e intento antes del efecto; reservar red y reclamar identidad bajo las
  garantías existentes. Crear CT detenido con marcador exacto; verificar recursos/base/red.
- Wrapper del nodo verifica y habilita sólo las features del perfil; firewall antes del arranque.
  Empezar trabajo duradero con execution_id, sin mantener transacción SQL durante SSH/descargas.
- Docker inspecciona/pull digest, configura volúmenes/secretos/borde y arranca sin privilegios libres.
  Community usa script guest/Core/harness/dependencias revisados y respuestas predefinidas.
- Tras terminar, comprobar pertenencia/configuración, salud y acceso. Sólo entonces marcar
  utilizable/transicionar a ACTIVO y avisar. No instalar otra vez por volver a consultar.
- Stop/start/restart mantienen el contenedor y persistencia; delete confirma ausencia y libera
  capacidad/red. Si falla la identidad o limpieza, estado explícito y contabilidad retenida.

### Consola y continuidad

- SQL almacena texto depurado ordenado por raíz; intentos y trabajos se correlacionan sin cambiar
  operaciones terminales. Supervisor de nodo sobrevive a SSH/worker; reboot exige reconciliar.
- Ingesta corta cada 1 s, commit y después ACK; navegador cada 1 s con cursor, sin sockets de shell.
  Textos desconocidos no se retienen; registro técnico permite diagnóstico sin exponer credenciales.
- UI con fases claras, consola negra/blanca, texto literal, scroll pausable, exportación deliberada,
  errores de consulta distintos del proceso y metadatos de recorte/vencimiento visibles.
- Sesión/rol se revalidan en cada lectura/exportación. Se aborta y borra el buffer de consulta al
  perder acceso; no se promete borrar copias ya descargadas.

### Compatibilidad y migración

- Cambios aditivos y discriminados; no reset de base, usuarios, cátedras ni IDs existentes.
- FKs nuevas nullable y tipos nuevos separados; conservar `nap-guest-runner/1`, manifiestos 1.1,
  artefactos/credenciales/red Draw.io y datos de IaaS.
- Validación de perfiles es técnica y una vez por revisión/plataforma, no un trámite por alta.
  Medium inicial en pilotos; Small sólo cuando se demuestre que cabe la plataforma completa.
- El perfil de acceso web debe ser genérico: no basta permitir otro producto en el gateway Draw.io.
  TCP mantiene su autenticación propia; un logout NAP no revoca retroactivamente una conexión nativa.

## Secuencia para la generación posterior de tareas

1. **Gate de factibilidad**: harness Core, Docker anidado, permisos cerrados y red en un recurso
   controlado; validar fuentes/secretos sin activar perfiles ni crear ofertas engañosas.
2. **Base común**: migración/configuración, resolver/profile registry, snapshots/reserva, trabajos
   duraderos, intento/fencing, productor seguro e ingesta de consola con fakes y carreras SQL.
3. **Recorrido Docker**: alta, aprobación, instancia, persistencia, acceso y primer flujo de consola.
4. **Recorrido Community**: mismo contrato y control, perfiles MariaDB/Caddy y probes específicos
   de acceso; ninguna duplicación de máquina de estados o implementación completa de instaladores.
5. **Integración**: agenda/reintentos/bajas, permisos, GUI simple, regresión, ensayos reales y guía
   de conexión institucional. Declarar cada gate real aprobado o bloqueado con su motivo.

Estos son incrementos de diseño, no tareas ejecutadas ni autorización para saltar sus compuertas.

## Validation Strategy

[quickstart.md](quickstart.md) contiene los comandos y ensayos posteriores a implementación.

| Superficie | Evidencia requerida |
|---|---|
| Configuración/registry | Fuente inválida, cambio de tag, plataforma incorrecta, auth/CA y SSRF; sin secretos |
| Capacidad/agenda | Aprobaciones concurrentes, reserva futura, inicio/revocación y autor sistema |
| Runner | Respuesta perdida, takeover, misma ejecución, boot cambiado, entrada maliciosa y log seguro |
| Consola | Secretos entre chunks, raw logs deshabilitados, orden/cursor/ACK, límites, revocación/exportación |
| Persistencia/acceso | Reinicio sin reinstalar, datos por cátedra, TLS/autenticación y restricción de red |
| Limpieza | Propiedad ajena, ausencia incierta, disco ocupado y red retenidos hasta confirmación |
| Regresión | Ubuntu/Debian/Draw.io, renovaciones, avisos y permisos existentes |
| Física | MariaDB + Caddy + dos imágenes, dos instancias aisladas y fallos reales controlados |

No hay nuevos tests de implementación creados o ejecutados en esta fase. Se valida coherencia de
artefactos y fuentes; pasar a tareas no equivale a certificar un perfil real.

## Complexity Tracking

No se mantienen violaciones constitucionales aceptadas. La enmienda 4.2.0 ya resuelve la única
ambigüedad del momento de instalación. Nuevas tablas y protocolo tienen motivos concretos:
configuración sin reinterpretar legado, ejecución durable, consola limitada y red reutilizable.
Polling, un worker y acciones cerradas son la alternativa mínima; no broker/terminal interactiva.

## Trazabilidad de requisitos

| Requisitos | Diseño y comprobación |
|---|---|
| FR-001–003 | Alta administrativa unificada y oferta sin recursos; contratos UI/API; US1/US2 |
| FR-004–005 | Configuración OCI/registry, plataforma/digest, dos imágenes y datos; R02–R04 |
| FR-006–009 | Perfil/harness Community, fuentes fijas, mínimos y cambios inmutables; R05/R06 |
| FR-010–012 | Pedido/Otro, evaluación/reserva/agenda, dos aprobaciones; R01/R13 |
| FR-013–017 | Identidad, red, secretos, trabajos duraderos y comprobación de acceso; R07/R11/R14 |
| FR-018–024 | UI/consola, depuración previa, cursores/ACK, cuotas y permisos; R08–R10 |
| FR-025–028 | Reintento enlazado, persistencia, limpieza confirmada y políticas académicas; R07/R11/R13 |
| FR-029–030 | Configuración inicial, perfiles bloqueados hasta prueba real y regresión sin recreación; R12 |

SC-001/008: recorridos cronometrados; SC-002/003: cuatro aplicaciones y dos cátedras; SC-004:
medición del registro; SC-005/006: fallos/reconciliación/limpieza; SC-007: permisos y secretos;
SC-009: regresión y separación de evidencia simulada/local/institucional.
