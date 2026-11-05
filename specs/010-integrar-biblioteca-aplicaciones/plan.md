# Implementation Plan: Biblioteca de aplicaciones reutilizables

> Ajuste vigente del 25/10/2026: el alta normal es **elegir → preparar → comprobar funcionamiento → publicar o eliminar**, sin TTL de 24 horas ni parámetros técnicos en el formulario. La configuración institucional se resuelve una sola vez. El [contrato de alta simple](contracts/alta-simple-api.md) sustituye los pasos avanzados/TTL de este documento; los ensayos reales y mediciones pendientes no se consideran ejecutados. Ver [guía actual](../../docs/administracion-servicios.md).

**Branch**: `010-integrar-biblioteca-aplicaciones` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: `specs/010-integrar-biblioteca-aplicaciones/spec.md`, incluidas las cuatro aclaraciones de 2026-10-25.

## Summary

Incorporar búsqueda administrativa de aplicaciones de Community Scripts, importación de borradores y preparación desde NAP de Draw.io como piloto Software. Community Scripts aporta el comando de origen; NAP usa una receta propia cerrada para construir una imagen LXC limpia, comprobar dos instancias de ensayo y publicar una oferta reutilizable. Los pedidos consumen el catálogo/perfiles existentes y cada cátedra recibe su propia instancia.

La publicación actualiza un perfil estable; los pedidos de alta pendientes usan la versión vigente al aprobar, con evaluación/reserva de esa versión y aviso del cambio. Después de aprobar se conserva el snapshot. Limpieza automática de ensayo al publicar, descartar o vencer; retener definición, evidencia y artefactos para nuevos despliegues sin Community Scripts.

Este documento completa fases 0 y 1. No implementa funcionalidad, no genera `tasks.md` ni declara aceptación de infraestructura. El alcance solicitado ahora incluye planificación, aunque la spec original anticipaba realizarla en otro chat.

## Technical Context

**Language/Version**: Python 3.12 (imagen backend existente); JavaScript ES modules/React 19/Vite 8 del proyecto. JRE 21/Tomcat 11 para el nuevo runtime, versiones exactas fijadas por preparación.

**Primary Dependencies**: FastAPI, SQLAlchemy async 2, Alembic, PostgreSQL asyncpg, proxmoxer, APScheduler, keyring criptográfico, runner SSH/forced-command y builder institucional ya presentes. No añadir cola/distribuidor ni catálogo de ejecución arbitraria. Reusar React Router, Axios, Vitest y Playwright.

**Storage**: PostgreSQL 16 para incorporaciones/ensayos/publicaciones y snapshots. Imágenes/bundles en almacenamiento institucional de sólo lectura por digest, con réplicas PVE y registro de disponibilidad. Credenciales sólo cifradas y configuración privada; ningún secreto en manifiestos o procedencia.

**Testing**: pytest/pytest-asyncio con dobles de PVE, fuente, builder y runner; PostgreSQL real aislado para locks, carreras y migraciones; Vitest/Testing Library para formularios; Playwright para recorridos. Suites separadas de `infra/`. Gate de staging real para imagen, editor, saneamiento, acceso y aislamiento.

**Target Platform**: Portal Linux + Proxmox VE institucional y host builder Ubuntu 24.04 amd64 separado. LXC sin privilegios, sin nesting; no VMs nuevas. No se fija una versión PVE inventada: registrar versión real del staging y verificar capacidades por cliente existente antes de publicar.

**Project Type**: Web app existente backend/frontend + infraestructura auxiliar.

**Performance Goals**: SC-001 <2 min y SC-004 <3 min para tareas humanas. Objetivos de diseño: consultas locales/estado p95 ≤1 s con 10 sesiones/100 muestras en staging; búsqueda externa deadline 10 s; retorno 202 de operaciones largas una vez persistidas, sin esperar construcción. Medir y registrar, no dar por cumplido.

**Constraints**: autenticación/2FA voluntario vigente, aislamiento por cátedra, capacidad atómica, trazabilidad, artefactos inmutables y disponibilidad sin Community Scripts tras publicación. Metadata externa incompleta se conserva como desconocida. Sin shell libre; no ejecutar `ct/drawio.sh` del proveedor en nodos operativos. No gestión de alumnos, cuentas internas Draw.io, guardado centralizado, colaboración ni actualizaciones automáticas.

**Scale/Scope**: piloto desplegable Draw.io; descubrimiento de otras aplicaciones con compatibilidad no comprobada. Dos LXC por ensayo; una instancia por pedido aprobado. Un ensayo abierto por definición y trabajos limitados por capacidad, pool de red y presupuesto builder. Índice externo hasta 10.000 entradas/8 MiB, resultados paginados de máximo 50. Sin prometer incorporar masivamente todo el catálogo.

## Constitution Check

Constitución 4.0.0. Evaluación inicial realizada sobre spec y arquitectura existente antes de consolidar fase 0; reevaluación al finalizar diseño.

| Principio/compuerta | Evaluación inicial | Resultado tras diseño |
|---|---|---|
| I. Portal único de gestión | Compatible: acciones administrativas propias | Pasa: servicios NAP crean/controlan recursos; comando externo sólo procedencia; sin nueva derivación a Proxmox |
| II. Estados centrales e historial | Compatible: conservar estados de pedido | Pasa: `pedido_service.transicionar` sigue siendo único escritor; ensayo tiene máquina propia central y bitácora con autor sistema/usuario |
| III. Recuperación | Requiere diseño durable de ensayo | Pasa en diseño: intención antes de I/O, leases y generación/cierre durable remoto por ensayo, consulta de trabajos/UPID, ownership y conciliación antes de reintentar; fallos 502/409/403 diferenciados |
| IV. Aislamiento/capacidad | Requiere incluir recursos de ensayo | Pasa en diseño: ledger común y lock 4001, fila PresupuestoBuilder por scope con upsert/lock desde primera admisión, pool de ensayo separado, dos reservas atómicas; limpieza incierta retiene capacidad; sin cupo docente |
| V. Historia preservada | Compatible: artefacto/referencia por versión | Pasa: snapshots originales, bitácoras append-only, retiro lógico, retención de artefactos referenciados |
| VI. Cátedra pide/observa | Compatible: oferta Software sin hardware | Pasa: selección en Catálogo y Nuevo pedido, avisos, ninguna pantalla de build para docentes |
| Stack, secretos y migraciones | Compatible con stack fijo | Pasa: Alembic aditivo, keyring y rutas de revelado auditadas; credenciales infra fuera del repo |
| Tests de orquestación/fallo | Obligatorios para implementación | Exigidos: timeout tras creación, pérdida de confirmación builder/UPID, reintento y limpieza fallida |
| Tests de capacidad/concurrencia | Obligatorios con PostgreSQL | Exigidos: ensayo vs aprobación, dos ensayos, publicar vs aprobar, workers con lease perdido |
| Compuertas externas | No acreditadas por esta planificación | Pendientes explícitas en quickstart: dos LXC reales, red institucional, exportar/reabrir, saneamiento, denegación cruzada y caída externa |

No se identifican violaciones que requieran excepción constitucional. «Pasa en diseño» no significa prueba ejecutada o aceptación operativa.

## Project Structure

### Documentation (this feature)

```text
specs/010-integrar-biblioteca-aplicaciones/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── biblioteca-api.md
│   ├── preparacion-runner.md
│   └── catalogo-pedidos-ui.md
└── checklists/requirements.md
```

`tasks.md` es salida posterior de `/speckit-tasks`; no se crea en este comando.

### Source Code (repository root)

Rutas existentes y propuestas para implementación; los nombres nuevos son decisiones del plan, no archivos implementados.

```text
backend/
├── alembic/versions/                   # migración aditiva 010 desde head real
├── app/
│   ├── models/                        # incorporación, ensayo/recurso/operación, artefacto, publicación
│   │                                  # ampliar pedido, identidad y compromiso_capacidad
│   ├── schemas/                        # biblioteca/ensayo; manifiesto Draw.io 1.1 y evidencia
│   ├── routers/
│   │   ├── biblioteca.py               # nuevo descubrimiento/incorporación
│   │   ├── ensayos.py                  # nuevas acciones/consulta
│   │   └── definiciones.py             # integración de publicar-oferta
│   ├── services/
│   │   ├── biblioteca_service.py       # nuevo adaptador externo e importación
│   │   ├── ensayo_service.py           # nueva máquina/decisiones
│   │   ├── ensayo_worker.py            # nueva ejecución durable/reconciliación
│   │   ├── build_runner_client.py      # nuevo transporte de construcción cerrado
│   │   ├── artefacto_service.py        # nuevo registro/distribución verificable
│   │   └── catalogo_service.py         # extender publicación atómica y gates
│   │                                  # ampliar evaluación/admisión/capacidad/preparación/probes/red
│   ├── config.py                      # fuente, builder, límites y perfiles de ensayo
│   └── worker.py                      # registrar ejecución/expiración/limpieza de ensayos
└── tests/                             # dobles/contratos/fallos; postgres para carreras/migración
frontend/
├── src/pages/Definiciones.jsx          # búsqueda, ficha, preparación/publicación
├── src/components/                    # componentes de ficha/estado/confirmación de entradas
├── src/pages/Catalogo.jsx              # conservar oferta seleccionada
├── src/components/NuevoPedidoModal.jsx # selección docente existente
├── src/components/AprobarPedidoModal.jsx # versión solicitada/efectiva
├── src/services/api.js                 # contratos nuevos
└── tests/                             # Vitest y Playwright
infra/
├── builder/                           # nuevo ejecutor/registro/forced-command de build
├── services/
│   ├── drawio/                        # nueva receta/bootstrap
│   ├── build_image.py                 # extender builder, inventario y evidencia
│   ├── sanitize.py                    # limpieza de artefacto Draw.io
│   └── tests/                         # saneamiento/runtime/paquete
├── runner/                            # ampliar producto/probes/secretos cerrados
├── laboratorio/                       # ampliar instalación de paquete/registro
└── production/                        # configuración y permisos de tablas nuevas
```

**Structure Decision**: ampliar los tres árboles existentes sin un segundo catálogo ni un motor académico paralelo. Nuevo dominio de ensayo porque no es un pedido de cátedra; compartir primitivas de leases, identidad, ledger, transporte y evidencia. Conservar el builder y la creación LXC existentes.

## Phase 0 — Investigación resuelta

[research.md](research.md) documenta decisiones, alternativas y fuentes primarias. Hallazgos determinantes: la metadata JSON histórica no es una interfaz disponible; el comando externo crea contenedores y no sirve como bootstrap; la preparación actual es de instancias académicas, mientras el builder institucional existente sí crea artefactos saneados. No quedan decisiones funcionales pendientes.

## Phase 1 — Diseño

### Flujo y responsabilidades

1. US1: buscar en fuente de lectura, indexar alias/categorías y mostrar procedencia/faltantes; importar incorporación idempotente editable, sin infraestructura.
2. US2: completar Draw.io, crear borrador técnico, admitir ensayo/reservas y presupuesto builder; resolver/confirmar versiones exactas; construir imagen limpia y distribuir; desplegar dos LXC de ensayo desde artefacto; ejecutar probes y comprobación administrativa externa.
3. Validar definición y publicar oferta/perfil en transacción atómica; no permite bypass por la ruta de publicación previa. Encolar limpieza efímera, sin borrar artefactos ni evidencia. Expirar/descartar usa el mismo ejecutor de limpieza con fencing.
4. US3: solicitar oferta estable, guardar selección original; evaluar/aprobar vigente con token y capacidad de esa versión; notificar diferencia y congelar snapshot. Desplegar desde la fecha inicial mediante la orquestación existente; bootstrap Draw.io y gate de acceso por instancia.

El bootstrap de ensayo no puede llamar sin cambios a `_definition()` actual, que exige definición publicada/retirada: crear validación específica de artefacto de ensayo con dueño institucional y permitir sólo imagen/receta verificadas de ese ensayo. Mantener intacto el gate de publicación de los servicios académicos. Las pruebas impiden usar un borrador por el camino de producción.

### Precisiones de ejecución

- El contrato builder incluye `generation`, `cancel` y registro durable de cierre fuera de temporales. Cancelar cierra primero y termina procesos antes de limpiar; mensajes build/stage atrasados nunca reabren el ensayo. La generación remota complementa, no sustituye, CAS/lease en DB y conciliación de tareas PVE inciertas antes de confirmar ausencia.
- El presupuesto builder tiene fila propia por scope físico, compartida por hosts con el mismo disco; upsert y lock transaccionales serializan también la primera admisión. Capacidad PVE se bloquea antes de scopes ordenados.
- La incorporación origina múltiples versiones NAP mediante FK desde definición y antecedente explícito. Nueva versión no exige cambio del comando externo ni modifica una publicación previa.
- Buscar sólo por categoría es válido; exigir texto o categoría y combinar ambos con AND cuando se proporcionen.

### Entidades e interfaces

[Modelo de datos](data-model.md); [API de biblioteca/ensayos](contracts/biblioteca-api.md); [builder/artefactos/runner](contracts/preparacion-runner.md); [ofertas/pedidos/UI](contracts/catalogo-pedidos-ui.md). Manifiestos previos siguen válidos; Draw.io usa esquema 1.1 y registros cerrados. La configuración de builder/artefactos es recargable y versionada para API y worker, sin escritura de configuración libre desde el navegador.

### Entrega incremental y trazabilidad

| Bloque | Requisitos | Validación principal |
|---|---|---|
| Descubrimiento/incorporación | FR-001–005, FR-016 | Alias, categorías, cache/fallo explícito, identidad/reimportación, teclado y ausencia de I/O de instalación |
| Ensayo/artefacto/Draw.io | FR-006–008, FR-013, FR-017–018 | Entradas fijadas, dos recursos, saneamiento, pérdida de confirmación, acceso/editor, limpieza/TTL |
| Oferta y pedidos | FR-009–012, FR-014–015 | Perfil estable, selección conservada, vigente al aprobar, reserva/token, retiro, «Otro», independencia proveedor |

### Validación y observabilidad

Ejecutar las suites descritas en [quickstart.md](quickstart.md) durante implementación; no ejecutarlas ahora como supuesto test de una función inexistente. Casos obligatorios de PostgreSQL: ensayo vs aprobación compitiendo por última capacidad; publicación entre evaluación y aprobación; dos importaciones/ensayos concurrentes; worker vencido vs cleanup. Pruebas con dobles de todos los efectos de infraestructura y sin red externa por defecto.

Logs/metricas: IDs de incorporación/ensayo/operación/definición/recurso, fase, duración, clase de fallo, reintentos y limpieza pendiente; excluir comando crudo, credenciales y headers Authorization. Auditar acciones administrativas, revelados y acciones automáticas. Backups del portal incluyen nuevas tablas; conservar paquete institucional fuera de LXC de ensayo y referenciar su revisión en la evidencia.

Gates previos a validar/publicar: dos instancias reales de ensayo desde artefacto retenido con Community Scripts bloqueado, saneamiento, red/HTTPS/acceso cruzado, ciclo editable y reinicio. Registrar `deployment_without_provider` en su evidencia antes de publicar. Gate posterior de SC-006: enviar/aprobar/desplegar un pedido nuevo durante bloqueo del proveedor; verifica el recorrido completo, pero no es prerrequisito circular para la primera publicación. Sin los gates previos no publicar Draw.io como comprobado. La planificación no declara que existan imagen, certificados, builder o aceptación real.

## Complexity Tracking

Sin excepciones constitucionales. La complejidad adicional necesaria es el dominio de ensayo y su ejecutor cerrado; duplicar el catálogo, crear pedidos académicos ficticios o aceptar comandos libres se descartan por romper identidad, capacidad o alcance.

## Post-design review y salida

Las decisiones de fase 1 preservan los seis principios y las compuertas de prueba. Entradas operativas concretas (host, versiones exactas de cada build, certificados, destinos) son parámetros validados del entorno y del ensayo, no decisiones funcionales pendientes. Sin `NEEDS CLARIFICATION` abiertos. No existe `.specify/extensions.yml`; no hay pre/post hooks que despachar.

Siguiente paso: `/speckit-tasks` para descomponer el diseño antes de implementar.
