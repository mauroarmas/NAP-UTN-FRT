# Implementation Plan: Remediación de hallazgos y cierre de la práctica

**Branch**: 009-remediar-hallazgos-cierre (por pedido del usuario) | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Feature Directory**: specs/009-remediar-hallazgos-cierre. La rama Git `009-remediar-hallazgos-cierre` fue creada el 2026-10-20 por pedido del usuario, conservando los cambios de trabajo.

**Input**: 73 requisitos, ocho historias y diecisiete criterios de aceptación, con cuatro aclaraciones incorporadas. Este documento termina en diseño de fase 1; no genera tasks.md ni implementa cambios.

## Summary

Cerrar vulnerabilidades de autorización y autenticación, hacer indivisible el compromiso de capacidad y recuperar operaciones externas sin duplicar recursos. Conservar el conjunto tecnológico y servicios existentes, añadiendo sesiones por propósito, operaciones persistidas y compromisos por destino en PostgreSQL. Un worker del mismo backend ejecuta tareas y reconciliación; la API devuelve operación pendiente sin afirmar éxito anticipado.

Completar calendario lectivo configurable, snapshots de aprobación y períodos de renovación separados; corregir formularios, sesión, accesibilidad, filtros y observación. Preparar LXC completos y dos productos demostrables: PostgreSQL y BookStack, con definiciones versionadas, imágenes saneadas y personalización controlada. La entrega incluye respaldo/restauración, evidencia real, manuales y trazabilidad. QEMU y alumnos dentro de NAP quedan fuera; 2FA sigue voluntario para ambos roles.

## Technical Context

| Aspecto | Decisión y evidencia |
|---|---|
| Language/Version | Python 3.12 del dockerfile; JavaScript ESM/JSX. Frontend Node 22.12 o superior de rama 22 LTS para Vite 8; ajustar imagen node:20-alpine actual al preparar entrega, fijando digest comprobado. |
| Primary Dependencies | FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.16, proxmoxer 2.2, APScheduler 3.11, PyOTP 2.9; React 19, React Router 7, Axios y Recharts/Vite 8. Son versiones de partida, no una obligación de conservar vulnerabilidades. |
| Dependencias adicionales | cryptography directa para cifrado, jsonschema Draft 2020-12 para manifiestos; Vitest/Testing Library y Playwright como desarrollo. OpenSSH del sistema en worker; sin Paramiko, broker ni nueva base. Pines concretos/lock se generan al implementar y auditar. |
| Storage | PostgreSQL 16, Alembic. Snapshots, operaciones, sesiones y outbox; datos de aplicaciones fuera de la base interna. Claves en secretos de entorno/archivos montados y keyring externo. |
| Testing | pytest/pytest-asyncio/httpx y dobles PVE/runner; PostgreSQL 16 aislado para locks/migraciones; componentes y Playwright funcional/rendimiento. Suites infra/runner/tests e infra/services/tests con configuración propia y job CI explícito: backend/pytest.ini no las recolecta. |
| Target Platform | Linux, contenedores API/worker, SPA compilada y reverse proxy HTTPS con una origin. Versión real Proxmox inspeccionada antes de habilitar destinos; LXC no privilegiado Ubuntu 24.04 amd64. |
| Project Type | Aplicación web existente, API REST /api/v1 y worker del mismo repositorio. |
| Performance Goals | SC-008: p95 por recorrido <=3 s desde interacción hasta resultado visible/utilizable en navegador, con cien servicios, noventa días y diez sesiones durante un despliegue lento. Medición HTTP complementaria; consultas ordinarias no llaman PVE por fila. |
| Constraints | Stack constitucional fijo; permisos actuales por cátedra; sin cuotas, sin borrado histórico, sin éxito previo a confirmar tarea ni capacidad de infraestructura supuesta. |
| Scale/Scope | Ocho historias completas; cadencia de un minuto: hasta 12,96 millones de muestras en noventa días, más resúmenes diarios históricos. Sin particionado prematuro. |
| Productos de referencia | PostgreSQL 16; BookStack 26.09.1/PHP 8.3/MariaDB 10.11. Artefactos fijan patches, commit y digests reales al construirse; BookStack sigue siendo referencia provisional. |

Las incógnitas iniciales sobre sesiones, locks, almacenamiento, tareas, calendario, bootstrap y copias se resolvieron en [research.md](research.md). Inventario, permisos y conectividad del entorno tienen gates verificables; no quedan decisiones de arquitectura abiertas.

## Constitution Check

GATE antes de fase 0 y reevaluación después de fase 1, contra la [constitución 4.0.0](../../.specify/memory/constitution.md).

| Principio / compuerta | Antes de investigar | Después del diseño y evidencia prevista |
|---|---|---|
| I. Portal media infraestructura | PASS: conservar services y consola propia como única excepción. | PASS diseño: routers sin proxmoxer/SSH; pertenencia previa y trámite de revocación nativa con terminación de sesiones antes de reasignar/retirar permisos. Sin prueba institucional de revocación no se habilita consola. |
| II. Máquina de estados única | PASS: retirar vía genérica sin ejecutor. | PASS diseño: transición central también en sistema/renovación; actor, motivo y operación en historia. |
| III. Operaciones recuperables | PASS: persistencia y reconciliación. | PASS diseño: identidad estable, UPID, incertidumbre explícita e idempotencia; timeout no libera por sí solo. |
| IV. Aislamiento y capacidad al aprobar | PASS: backend sin cuotas nuevas. | PASS diseño: pertenencia vigente, lock 4001, inventario por destino y ledger único; futura alta reserva ahora; sobreasignación deliberada. |
| V. Historia no destructiva | PASS: conservar entidades/autorías. | PASS diseño: snapshots, períodos y resúmenes; baja lógica y migración sin inventar historia. |
| VI. Cátedra pide y observa | PASS: no ampliar panel con administración de clúster. | PASS diseño: docente crea/consulta pedidos, solicita renovación y opera servicios propios; corregir/reenviar/cancelar pedidos exige admin incluso sobre lo propio. Lectores solo en BookStack. |
| Seguridad y stack | PASS: MFA voluntario y cambio inicial obligatorio. | PASS diseño: sesiones restringidas, códigos, CSRF y secretos externos; sin reemplazar stack. |
| Pruebas de orquestación/fallo | Requeridas en implementación. | Quickstart exige fallo simulado por ejecutor modificado, reinicio y tarea tardía, sin PVE real. |
| Concurrencia de capacidad | Requerida; SQLite no la acredita. | PostgreSQL aislado con sesiones/workers independientes y barreras; diez repeticiones por caso de SC-003. |
| Compuertas manuales | Declararlas, no asumir cumplimiento. | Red alumno, runner/consola, DNS/TLS, recuperación de identidad, restore y validación con el responsable de una cátedra/teclado requieren evidencia. |

Resultado: sin violaciones de diseño ni excepciones constitucionales nuevas. PASS se refiere al diseño; implementación e infraestructura siguen condicionadas a sus pruebas de aceptación.

## Project Structure

### Documentation (this feature)

~~~text
specs/009-remediar-hallazgos-cierre/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── guia-servicios-referencia.md
├── checklists/requirements.md
└── contracts/
    ├── auth.md
    ├── operations.md
    ├── catalog-ui.md
    ├── guest-runner.md
    ├── console-access.md
    ├── evidence.md
    ├── evidence.schema.json
    └── service-definition.schema.json
~~~

tasks.md corresponde a /speckit-tasks; no se crea aquí.

### Source Code (repository root)

~~~text
backend/
├── app/
│   ├── models/                   # existentes + sesiones, ledger, operaciones, vigencias, avisos
│   ├── schemas/                  # contratos y errores coherentes
│   ├── routers/                  # actuales + calendario, definiciones, operaciones, alertas
│   ├── services/                 # conservar límites actuales; añadir servicios de nuevos dominios
│   │   ├── acceso_service.py
│   │   ├── pedido_service.py     # única transición de pedidos
│   │   ├── capacidad_service.py
│   │   ├── orquestacion_service.py
│   │   ├── proxmox_client.py
│   │   └── scheduler.py
│   ├── worker.py                # nuevo entrypoint del mismo backend
│   ├── config.py
│   └── main.py
├── alembic/versions/
├── scripts/                     # bootstrap/recovery/preflight/validación, sin seeds operativos
└── tests/
    ├── fakes.py
    ├── test_*.py
    └── postgres/               # nuevo: migraciones y concurrencia real
frontend/
├── src/
│   ├── pages/                  # conservar; seguridad, calendario y definiciones admin
│   ├── components/             # formularios y Dialog compartido
│   ├── hooks/                  # sesión/carga sin persistir credenciales
│   └── services/api.js
└── tests/                      # nuevo: componentes y e2e críticos
infra/                          # nuevo material operativo versionado, sin secretos
├── services/{linux,postgresql,bookstack}/
├── runner/
├── profiles/
└── proxy/
docs/                           # actualizar informe, manuales, datos y evidencia al implementar
~~~

**Structure Decision:** ampliar models/schemas/routers/services y la SPA actuales. Las rutas nuevas del árbol son propuestas, no archivos de aplicación generados por este comando. Runner y recetas se limitan a servicios propios; no forman un sistema general de gestión del clúster.

## Phase 0 — investigación completada

[research.md](research.md) documenta decisiones R01–R12, fundamento y alternativas. Investigación paralela contrastó seguridad, capacidad/calendario y servicios con código y documentación primaria. Se descartan broker nuevo, shell libre, Docker anidado, accesos ficticios, cuotas y reinterpretación de fechas aprobadas.

Se conserva el advisory lock global existente: permite cerrar carreras a esta escala sin introducir órdenes múltiples de bloqueo. OpenSSH restringido resuelve bootstrap porque el adaptador actual no dispone de ejecución guest mediante REST. El contrato no acepta comandos libres.

## Phase 1 — diseño resultante

### Límites transaccionales y ejecución

1. Sesión comprueba versión/propósito/usuario; servicio de negocio comprueba permiso vigente, pertenencia, bloqueo preventivo y transición. Corregir/reenviar/cancelar pedidos solo admin. Reasignar/retirar acceso nativo usa un trámite duradero: bloquear, acreditar revocación de ACL y sesiones, comprobar revisión y completar; nunca entregar al nuevo titular antes de esa confirmación. El operador institucional ejecuta y acredita la revocación según console-access.md; guest-runner conserva solo sus tres comandos.
2. Aprobar/iniciar/reactivar toma lock de capacidad y después fila; relee condiciones e inventario con plazo acotado. Confirma ledger, historia, idempotencia y operación en una transacción. No mantiene la transacción durante tareas externas.
3. Worker reclama con lease/generación, persiste fase previa al envío, llama adaptador y guarda UPID; recupera por reconciliación. Concurrencia externa inicial cuatro y sesiones DB independientes.
4. Confirma tarea/recurso y bootstrap/salud para toda oferta, incluso cuenta guest Linux. La operación infra termina sin esperar al operador; servicio permanece no_verificada y pedido EN_DESPLIEGUE hasta registrar prueba individual desde red prevista. Solo entonces publica acceso utilizable y transiciona ACTIVO. Pedido ERROR no elimina recursos ni los deja fuera de contabilidad.
5. Outbox se agrega junto al evento; SMTP se ejecuta fuera de la transacción, con error visible y reintento. Fallo de correo no revierte decisiones.

### Calendario, compatibilidad y esquema

[data-model.md](data-model.md) define entidades, restricciones, estados, índices y backfill. Períodos aprobados dan cobertura, no el máximo vence_at futuro. Reserva de alta futura: min(fin_exclusivo, max(aprobación,inicio)+24h). Detenciones conservan capacidad hasta confirmación; receso conserva disco sin garantizar CPU/RAM. Renovación registrada no significa contenedor encendido.

Nuevas ofertas requieren LXC y definición compatible. Se conserva lectura histórica de QEMU y plantillas retiradas. API/SPA se actualizan juntas por cambios de autenticación, evaluación POST y respuestas 202; los contratos anteriores siguen históricos, sin mantener una vía insegura por compatibilidad.

### Catálogo y preparación reproducible

Construir/sanear las tres imágenes; validar receta, paquetes, integridad, parámetros, secretos y repetición. El builder de preparación técnica prueba dos instancias fuera de la oferta pública antes de publicar la versión. Luego el flujo cotidiano exige solo solicitar, aprobar y desplegar desde catálogo.

Runner del nodo solo admite bootstrap/inspect/verify sobre identidad/pool/nonce propios, hostkey fijada y recetas permitidas. Perfiles institucionales resuelven nodo/storage/red/DNS/TLS. Si faltan, ese destino no se habilita; no se afirma que ya existan.

### Métricas, experiencia y evidencia

Worker captura estado/salud por minuto, evalúa alertas/vigencias/reservas por minuto, operaciones cada cinco segundos, inactividad cada hora y agregación/purga diaria. Jobs manuales usan el mismo ejecutor y locks. Muestras deduplicadas, deltas, máximos y calidad; consultas desde PostgreSQL.

Evidencia compartida antes de las historias: POST /evidencias registra documentos tipados de hasta 64 KiB, canónicos e inmutables en PostgreSQL; devuelve UUID/checksum. Catálogo, acceso por instancia y revocación consumen ese registro con comprobación de identidad/revisión. No se descargan referencias libres ni se confunde integridad del hash con prueba de una observación real. Ver evidence.md y evidence.schema.json.

Frontend restaura /auth/me, consulta operaciones pendientes, invalida evaluación al editar y presenta error/antigüedad/datos anteriores. Diálogos con foco/teclado y acciones sin doble confirmación. Carga diferida de rutas/gráficas; medir antes/después y comprobar SC-007 con el responsable de una cátedra de prueba.

## Cobertura para descomposición posterior

| Incremento | Requisitos | Salida comprobable |
|---|---|---|
| Acceso/seguridad US1–US2 | FR-001–FR-009, FR-046, FR-069–FR-071 | Autorización directa, MFA opcional, sesión restringida, recuperación y último admin concurrente. |
| Capacidad/operación US3–US4 | FR-010–FR-022, FR-033–FR-034, FR-048, FR-066, FR-068, FR-072 | Ledger/destino, 202, recuperación/reintento y concurrencia/fallo. |
| Pedidos/fechas/UI US5/US7 | FR-023–FR-032, FR-041, FR-044–FR-047, FR-064–FR-065 | Formularios, snapshot, calendario y receso con datos preservados. |
| Aplicaciones US6 | FR-035–FR-038, FR-052, FR-061–FR-063, FR-067, FR-073 | Dos instancias por producto, accesos reales y lectores individuales. |
| Observación US7 | FR-039–FR-040, FR-042–FR-043, FR-049–FR-050 | Tráfico/cobertura, alertas/outbox y resúmenes históricos. |
| Migración/cierre US8 | FR-051–FR-060 | Instalación/upgrade, secretos reales, dependencias, restore y documentos. |

Orden: contratos/esquema/acceso; admisión/operaciones; calendario/renovación; catálogo/productos; observación/UI; integración/cierre. Cada historia conserva prueba independiente; P2 integra la entrega. Las tareas ejecutables se generan después.

## Validation and delivery gates

[quickstart.md](quickstart.md) define comandos y evidencia SC-001–SC-017. Al implementar, el cierre requiere regresiones backend/frontend, fallo externo simulado por ejecutor modificado, PostgreSQL real para locks/unique parcial/fechas/migraciones y dos instancias de cada aplicación desde red alumno. También ejecutar explícitamente las suites infra/runner e infra/services y el ensayo Playwright de SC-008 sobre SPA compilada: cien servicios/noventa días/diez sesiones, al menos cien muestras por recorrido, p95 de resultado visible <=3 s y fallos contados; el benchmark HTTP es diagnóstico. Además, restore separado de portal+claves/aplicaciones y documentación completa.

La prueba antigua de límite de disco debe actualizarse a la política vigente; no se cambia producción para satisfacerla. La evidencia distingue simulación, integración real y limitaciones de terceros.

Gates de entorno pendientes de ejecución: versión/inventario PVE, destinos rootdir, ACL/token, runner, red, DNS/TLS, SMTP, destino de copias y acceso desde otra computadora. No son decisiones funcionales ni permisos pendientes del usuario. No marcar entrega aceptada sin evidencia.

## Complexity Tracking

No hay violaciones constitucionales que justificar.

| Complejidad añadida | Motivo | Alternativa más simple evaluada |
|---|---|---|
| Operaciones/ledger y worker persistentes | Recuperación y concurrencia sin perder reservas. | Solo estados/BackgroundTasks pierde trabajo tras caída y dispatch incierto. |
| Sesiones revocables y cookie/CSRF | Exigir MFA elegido/cambio inicial y revocar acceso. | JWT autónomo operativo conserva bypass y no revoca logout. |
| Runner limitado de infraestructura | Personalización LXC repetible y verificable. | Instalación manual no repite catálogo; shell root general expande privilegios. |

Verificación de artefactos de planificación: cobertura de FR-001–FR-073 y SC-001–SC-017, enlaces locales, ejemplos JSON, referencias internas del schema y formato Markdown. La metavalidación Draft 2020-12 requiere jsonschema, no instalado en este entorno; queda como check de implementación, sin afirmar que se ejecutó. No se corrieron suites de aplicación porque este comando solo produce diseño/documentación.

Hooks: .specify/extensions.yml ausente al iniciar y al finalizar; sin hooks que ejecutar.
