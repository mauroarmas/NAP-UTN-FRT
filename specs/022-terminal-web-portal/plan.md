# Implementation Plan: Terminal web de la consola dentro del portal

**Branch**: `022-terminal-web-portal` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/022-terminal-web-portal/spec.md`

## Summary

La persona abre una terminal **dentro del portal** y nunca ve Proxmox. Tres piezas nuevas:

1. **Relay de terminal en el backend**: un WebSocket del portal (`/servicios/{id}/terminal`) que, por detrás, inicia sesión en la infraestructura con la **identidad individual** de la persona (ticket de sesión, no token de API), pide la consola del contenedor y reenvía bytes entre el navegador y el nodo. Verifica la pertenencia en el portal, impone inactividad, límite de sesiones por persona y cierre inmediato, y audita aperturas y cierres sin guardar contenido.
2. **Aprovisionamiento automático de identidades**: un reconciliador durable en el worker compara lo que cada persona *debe* tener (según las cátedras que posee) con lo aplicado, y lo converge con **acciones cerradas del runner del nodo** (`nap-console-identity/1`): crear/actualizar identidad y ACL por pool, retirar, terminar sesiones. La contraseña es aleatoria, se guarda cifrada y nunca se muestra.
3. **Terminal web en el frontend** (xterm.js) en «Ver acceso», que reemplaza el enlace a Proxmox para las personas.

El retiro conserva la prueba de revocación de la 020 y la compuerta de instalación sigue exigiendo evidencia real. **No se enmienda la constitución en esta feature**: la derivación a Proxmox queda como respaldo y el plan registra el escenario (research R9). Detalle y fuentes en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (FastAPI + SQLAlchemy async; runner de nodo sólo biblioteca estándar), JavaScript/React (Vite).

**Primary Dependencies**: backend: las existentes (`websockets`, `httpx`, `uvicorn[standard]`); frontend: **nueva** `@xterm/xterm` y `@xterm/addon-fit`, versiones exactas `6.0.0` y `0.11.0` fijadas en el lockfile (≥ 2 semanas de antigüedad; research R7).

**Storage**: PostgreSQL del portal, **migración Alembic** (cabeza actual `017_01_clave_acceso_servicio`): tablas `identidades_consola` y `sesiones_terminal`; el estado de sesión vivo es en proceso, el cupo y la auditoría están en la base.

**Testing**: pytest (backend y `infra/runner/tests`, con dobles del nodo y del WebSocket de infraestructura), vitest (frontend, con un doble de WebSocket), y ensayo real en frt y pve91 (apertura por ambos nodos, retiro con sesión abierta, límites).

**Target Platform**: portal en contenedores del equipo, con Caddy delante (deja pasar WebSocket); nodos Proxmox VE 9.x.

**Project Type**: aplicación web (backend + frontend) con paquete de infraestructura de nodo.

**Performance Goals**: prompt de login en < 5 s (SC-001); corte por retiro en < 5 s (SC-004); decenas de sesiones simultáneas en el lab, cientos en una instalación, con consumo por sesión acotado.

**Constraints**: la contraseña de la identidad sólo está en memoria durante el inicio de sesión del relay; nunca en registros, errores, auditoría ni respuestas (SC-007); sin token de infraestructura con permisos amplios para crear identidades; sin tocar archivos del `policy_digest` del motor Docker; compuerta e identidades de la 020 y usuario `nap` de la 021 sin regresión.

**Scale/Scope**: un único proceso de API hoy (sin `--workers`); el plan evita depender de memoria compartida para cupo y cortes (research R5). Sólo Linux IaaS.

## Constitution Check

*GATE: pasa antes de la investigación y se re-evalúa después del diseño.*

| Principio | Evaluación |
|---|---|
| I. Proxmox es el back-end, nunca la interfaz | **Cumple y mejora.** La persona deja de tocar la interfaz de Proxmox: todo pasa por el portal. La excepción de consola sigue vigente como **respaldo** (no se retira aquí; ver R9 y la tabla de escenarios). El relay vive en `app/services/` y los routers no invocan `proxmoxer`. La pertenencia se verifica en el portal (FR-003). |
| II. Máquina de estados única | **Cumple.** La identidad tiene su propio estado de aprovisionamiento (derivado y reconciliado); no agrega estados al pedido/servicio. Los retiros reutilizan el trámite `CambioAccesoConsola` de la 009. |
| III. Recuperable | **Cumple con atención (riesgo principal R4).** El reconciliador compara *deseado* vs *aplicado* y es idempotente; un resultado incierto se reintenta sin duplicar; el retiro sigue el orden bloqueo → revocación acreditada → transferencia. |
| IV. Aislamiento por cátedra | **Cumple.** Identidad individual + ACL sólo sobre `/pool/catedra-N`, **y** verificación en el portal antes de abrir (doble barrera). Cada sesión se ata a un único servicio. |
| V–VI | No aplican. La terminal exige servicio encendido y con vigencia, como hoy. |
| VII. Simplicidad | **Cumple.** La persona no aporta datos nuevos ni ve infraestructura: un botón y una terminal. Los límites de sesión son configuración de instalación, no de la persona. |
| Seguridad | Identidad por persona (nunca compartida); contraseña aleatoria cifrada; acciones cerradas del nodo (sin token amplio); límites de sesión, inactividad, tamaño de mensaje y cola; auditoría sin contenido. La cláusula «Identidad en Proxmox para la consola» se **conserva**. |

**Re-evaluación posterior al diseño**: sin violaciones sin justificar. La complejidad nueva se justifica abajo.

## Project Structure

### Documentation (this feature)

```text
specs/022-terminal-web-portal/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── terminal-ws.md
    ├── runner-console-identity.md
    └── api-identidades-consola.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/022_01_terminal_identidades.py        # NUEVO: identidades_consola, sesiones_terminal
├── app/
│   ├── models/identidad_consola.py, sesion_terminal.py    # NUEVO
│   ├── schemas/console_identity.py                        # NUEVO: protocolo nap-console-identity/1 (se copia al nodo)
│   ├── services/
│   │   ├── identidad_consola_service.py                   # NUEVO: deseado vs aplicado, reconciliación, adopción
│   │   ├── terminal_relay_service.py                      # NUEVO: ticket, termproxy, relay, límites, cierre
│   │   ├── terminal_sesiones_service.py                   # NUEVO: cupo, heartbeat, cierre solicitado, auditoría
│   │   ├── consola_gate_service.py                        # autorizar: identidad desde la base (ya no del perfil)
│   │   ├── consola_access_service.py                      # retiro automático + evidencia del sistema
│   │   └── guest_runner_client.py                         # execute_console_identity
│   ├── routers/terminal.py, admin_identidades_consola.py  # NUEVO: WS + estado/reintento
│   └── worker.py                                          # bucle de reconciliación
infra/runner/console_identity.py                           # NUEVO: acciones cerradas del nodo
infra/applications/install.py                              # mapa de archivos del paquete de nodo
frontend/src/
├── components/TerminalConsola.jsx                         # NUEVO (xterm)
├── components/AccesoServicio.jsx                          # botón «Abrir terminal»; sin enlace a Proxmox
└── pages/IdentidadesConsola.jsx                           # NUEVO: estado para administración
docs/runbook-terminal-portal.md, scripts del laboratorio   # runbook y operación
```

**Structure Decision**: se mantiene backend + frontend + paquete de nodo. Lo nuevo se aísla en servicios propios y en un protocolo de runner cerrado (patrón de la 017). La compuerta de instalación de la 020 no cambia; sólo deja de leer las identidades del archivo privado.

## Complexity Tracking

| Complejidad nueva | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| Protocolo de runner `nap-console-identity/1` | Crear/retirar identidades sin dar al portal un token con permisos amplios (vía de escalada) | Token de Proxmox con `User.Modify`/`Permissions.Modify` en `/access` |
| Relay WebSocket con ticket individual | Única forma de mostrar la terminal sin interfaz de Proxmox ni red de la persona hacia los nodos | SSO por cookie compartida (exige DNS/certificados reales; no funciona con IPs; la persona igual ve Proxmox) |
| Tablas `identidades_consola` y `sesiones_terminal` | Estado de aprovisionamiento recuperable y cupo/auditoría que sobrevivan al proceso | Estado sólo en memoria o en el archivo privado de la 020 (se pierde, no escala) |
