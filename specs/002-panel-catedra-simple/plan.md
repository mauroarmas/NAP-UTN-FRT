# Implementation Plan: Panel simple para cátedra

**Branch**: `002-panel-catedra-simple` | **Date**: 2026-08-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-panel-catedra-simple/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

La pantalla principal del rol cátedra hoy reutiliza la vista pensada para administrador (tabla de
todas las cátedras, conteos globales, estado de infraestructura), sin darle a la cátedra un lugar
simple para pedir un servicio y ver cómo vienen los suyos. El enfoque técnico es casi enteramente
de frontend: separar la vista de cátedra de la de admin en `Dashboard.jsx`, darle un acceso directo
al formulario de "Nuevo Pedido" que ya existe en `Pedidos.jsx` (ya cumple con no pedir datos de
infraestructura), y presentar el estado de sus servicios y su cuota en lenguaje simple reusando
endpoints ya existentes. La investigación (Fase 0) confirma que el backend ya filtra por cátedra y
ya expone cuota+uso sin datos de otras cátedras, así que esta spec no requiere endpoints nuevos.

## Technical Context

**Language/Version**: Backend: Python 3.12 (FastAPI, async). Frontend: JavaScript/JSX (React 19,
Vite 8) — sin cambios de versión, se usa el stack ya instalado.

**Primary Dependencies**: Backend: FastAPI, SQLAlchemy async, Alembic (sin nuevas dependencias).
Frontend: react-router-dom, axios (sin nuevas dependencias; no se agrega ninguna librería de UI
nueva para mantener la spec chica).

**Storage**: PostgreSQL — sin cambios de esquema (no se agregan tablas ni columnas).

**Testing**: Backend: pytest + pytest-asyncio + httpx (ya configurado en `backend/pytest.ini`);
aplica solo si se toca orquestación/máquina de estados/cuotas (Compuerta de calidad de la
constitución), lo que esta spec no hace. Frontend: sin framework de test automatizado instalado en
el repo; validación manual en navegador vía `quickstart.md`, como ya es la práctica del proyecto.

**Target Platform**: Web SPA servida por Vite (dev) / build estático, consumiendo la API FastAPI;
despliegue vía Docker Compose (`docker-compose.yml`) ya existente.

**Project Type**: Web application (backend + frontend), estructura ya establecida en el repo.

**Performance Goals**: Ninguno nuevo. Se apoya en los mismos endpoints ya usados por el dashboard
actual (`GET /pedidos/`, `GET /servicios/`, `GET /catedras/{id}`); sin llamadas adicionales de alto
costo.

**Constraints**: Debe cumplir el Principio VI de la constitución (pantalla de cátedra sin datos de
admin/infraestructura); no debe pedir identificadores de Proxmox a la cátedra (Principio I); debe
seguir usando los endpoints que ya filtran por `catedra_id` en el servidor (Principio IV), no
reimplementar ese filtrado en el cliente.

**Scale/Scope**: Cambio acotado a la pantalla principal (`frontend/src/pages/Dashboard.jsx`) y, si
aporta claridad, un componente nuevo de presentación derivado de ella. Cero archivos nuevos de
backend previstos (ver Fase 0). No afecta la vista de administrador.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitución evaluada**: v1.1.0, última enmienda 2026-08-15.

| Principio | Resultado | Fundamento |
|-----------|-----------|------------|
| I. Proxmox es el back-end, nunca la interfaz | **PASS** | No se agregan llamadas a infraestructura; se reutiliza el formulario de pedido existente, que ya solo pide `template_id` (catálogo interno), nunca VMID/nodo. |
| II. La máquina de estados es la única fuente de verdad | **PASS** | No se toca `cambiar_estado` ni se agregan transiciones; el frontend solo lee y traduce el `estado` ya existente a lenguaje simple para la vista de cátedra. |
| III. Toda operación contra la infraestructura debe ser recuperable | **N/A** | Esta spec no agrega operaciones nuevas contra infraestructura. |
| IV. Aislamiento y cuota por cátedra | **PASS** | Se reutilizan endpoints (`/pedidos/`, `/servicios/`, `/catedras/{id}`) que ya filtran por `catedra_id` y ya devuelven 403 si la cátedra pide datos ajenos; el frontend no reimplementa ese filtro. |
| V. El historial académico no se destruye | **PASS** | No se toca soft delete ni historial. |
| VI. La cátedra pide y observa; el administrador gestiona | **PASS — remedia** | Es el objeto central de esta spec: `Dashboard.jsx` deja de mostrarle a la cátedra la tabla global de cátedras y el estado del nodo, y pasa a mostrarle solo su acceso a "nuevo pedido" y el estado de lo suyo. La vista de administrador no cambia. |
| Compuerta de calidad (pruebas) | **N/A** | El feature no toca orquestación, máquina de estados ni cálculo de cuotas (esos ya existen y no se modifican); solo cambia presentación en el frontend. La compuerta de pruebas automatizadas de la constitución no aplica por alcance. |

**Resultado global**: **PASS**, sin violaciones. No se registran entradas en Complexity Tracking.

**Re-evaluación post-Fase 1**: sin cambios — el diseño (ver `data-model.md` y `contracts/`) confirma
que no se agregan entidades, columnas, ni endpoints; solo mapeos de presentación en el frontend.

## Project Structure

### Documentation (this feature)

```text
specs/002-panel-catedra-simple/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/app/
├── models/            # Sin cambios — Pedido, Servicio, Catedra ya existentes
├── routers/           # Sin cambios — pedidos.py, servicios.py, catedras.py ya filtran por rol
├── schemas/           # Sin cambios — CatedraConUso, ServicioResponse, PedidoResponse ya alcanzan
└── services/          # Sin cambios — no se toca orquestación ni máquina de estados

frontend/src/
├── pages/
│   ├── Dashboard.jsx     # MODIFICADO — separa vista cátedra de vista admin
│   ├── Pedidos.jsx       # Sin cambios de lógica — su formulario "Nuevo Pedido" se reutiliza/enlaza
│   └── Servicios.jsx     # Sin cambios — referencia para el mapeo de estados simplificado
├── components/            # Posible NUEVO — bloque de presentación de la vista cátedra, si separar
│                          # el JSX de Dashboard.jsx aporta claridad (se decide en /speckit-tasks)
└── services/api.js       # Sin cambios — ya expone getPedidos, listarServicios, getCatedra, createPedido
```

**Structure Decision**: Se mantiene la estructura Web application ya existente (`backend/` +
`frontend/`), sin agregar directorios nuevos. El cambio se concentra en `frontend/src/pages/
Dashboard.jsx`, con la opción de extraer un componente de presentación bajo `frontend/src/
components/` si el archivo resultante mezcla demasiado JSX de las dos vistas (admin/cátedra); esa
decisión de extracción se resuelve en la fase de tasks, no acá, para no sobre-diseñar una spec
explícitamente chica. El backend no requiere archivos nuevos ni modificados (ver `research.md` R1).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No aplica — la Constitution Check no arrojó violaciones. No se registran entradas.
