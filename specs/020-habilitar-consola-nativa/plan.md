# Implementation Plan: Habilitar la consola nativa de Linux IaaS

**Branch**: `020-habilitar-consola-nativa` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/020-habilitar-consola-nativa/spec.md`

## Summary

El portal ya tiene la compuerta (`consola_gate_service`), el inventario, los trámites y la evidencia tipada de la spec 009; lo que falta es **montar y demostrar el circuito en el clúster real** y corregir dos huecos del endpoint de consola. El trabajo se divide en tres partes:

1. **Operación institucional (lab):** rol propio de solo consola, identidades individuales en un dominio propio, ACL por pool de cátedra, inventario, ensayo real de revocación (sesión abierta, ticket guardado, otro pool) con scripts versionados y reutilizables, evidencia `revocacion_consola`, trámite completado y `console_access_profile` cargado.
2. **Código del portal (acotado):** el destino de consola deja de depender de un único `proxmox_host`: se resuelve por nodo con failover (FR-016); la rama de administrador pasa también por la compuerta de instalación (FR-001); mensajes claros para la persona docente (FR-014).
3. **Documentación:** runbook para la universidad (FR-013), sin valores del laboratorio (FR-012).

Si el ensayo no demuestra la revocación, la entrega es el diagnóstico y la consola queda cerrada (FR-008). Decisiones y fuentes en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (backend FastAPI + SQLAlchemy async), JavaScript/React (frontend Vite), shell y Python estándar para los scripts de operación del lab.

**Primary Dependencies**: las existentes. El ensayo real necesita un cliente WebSocket (paquete `websockets`) sólo en el entorno de ensayo del operador, no en el backend.

**Storage**: PostgreSQL del portal sin tablas nuevas (se reutilizan `usuarios.identidad_consola*`, `cambios_acceso_consola`, `evidencias`). Configuración privada: `console_access_profile` gana una clave `nodos`. Sin migración.

**Testing**: pytest (backend: gate, endpoint de consola, resolución de nodo con doble de red), vitest (mensajes de estado), ensayo real en frt y pve91 con evidencia separada de dobles.

**Target Platform**: portal en contenedores del equipo; nodos Proxmox VE 9.2.2 (`nap-lab`, 2 nodos); la persona usa un navegador con alcance de red a los nodos.

**Project Type**: aplicación web (backend + frontend) más procedimientos de infraestructura.

**Performance Goals**: consola abierta en < 1 min desde el clic (SC-001); resolución de nodo con sondeo de red ≤ 2 s por nodo.

**Constraints**: la excepción de la constitución no se amplía (rol sólo con `VM.Console`); ninguna identidad ni secreto del lab en archivos versionados; el portal no crea ni modifica identidades ni ACL de infraestructura; sin cambios al `policy_digest` del motor Docker ni a los perfiles validados.

**Scale/Scope**: lab con 2 nodos y 2 cátedras con pool; una identidad por persona; sólo Linux IaaS.

## Constitution Check

*GATE: pasa antes de la investigación y se re-evalúa después del diseño.*

| Principio | Evaluación |
|---|---|
| I. Proxmox es el back-end | **Cumple, sin enmienda.** Se usa la excepción única ya vigente. El rol nativo sólo concede `VM.Console` sobre el pool de la cátedra: la persona no puede ver nodos, almacenamiento ni operar energía (FR-005, FR-006). El portal verifica la pertenencia antes de ofrecer el destino (FR-003). Los routers siguen sin invocar `proxmoxer`. |
| II. Máquina de estados única | **Cumple.** No hay estados nuevos; se reutilizan los trámites de la 009 (`pendiente`, `revocacion_fallida`, `completado`). |
| III. Recuperable | **Cumple.** El trámite es durable con idempotencia; un fallo del operador conserva el bloqueo. La resolución de nodo no cambia estado. |
| IV. Aislamiento por cátedra | **Cumple y es el centro de la feature.** ACL por `/pool/catedra-N`; la compuerta verifica `identity.pool_catedra` y el alcance con revisión de cada cátedra. |
| V–VI | No aplican (sin cambios de vigencia ni catálogo); la consola ya exige vigencia activa. |
| VII. Simplicidad | **Cumple.** La persona docente no aporta ningún dato nuevo: un botón, un destino. Sin configuración por nodo para ella. |
| Seguridad | Sin tickets ni cookies en el portal ni en auditoría; identidades individuales; `root@pam` rechazada por el importador; secretos fuera del repo. |

**Re-evaluación posterior al diseño**: sin violaciones. No se añade complejidad que requiera justificación.

## Project Structure

### Documentation (this feature)

```text
specs/020-habilitar-consola-nativa/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── console-endpoint.md
    └── console-profile.md
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                         # (sin cambio de campos; `console_access_profile` admite `nodos`)
│   ├── routers/servicios.py              # consola_del_servicio: gate para todos, destino por nodo
│   └── services/
│       ├── consola_gate_service.py       # `exigir_gate` también para administración; valida `nodos`
│       └── consola_destino_service.py    # NUEVO: resolver nodo + sondeo + failover
└── tests/
    ├── test_consola_destino_020.py       # NUEVO
    └── test_consola_gate_020.py          # NUEVO (admin con gate, perfil con nodos)

frontend/src/
├── components/AccesoServicio.jsx         # mensajes por motivo de bloqueo
└── services/api.js                       # sin cambios de ruta

docs/infraestructura-laboratorio/scripts/consola/   # NUEVO: operación y ensayo
├── crear-rol-consola.sh
├── crear-identidad.sh
├── retirar-acceso.sh
├── ensayo-revocacion.py
└── README.md
docs/runbook-consola-nativa.md                        # NUEVO: runbook de la universidad
```

**Structure Decision**: se mantiene la estructura backend + frontend existente. La lógica nueva se aísla en un servicio (`consola_destino_service`) para no engordar el router; los procedimientos de infraestructura viven junto a los demás scripts del lab y el runbook general en `docs/`.

## Complexity Tracking

Sin violaciones que justificar.
