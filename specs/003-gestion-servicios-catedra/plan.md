# Implementation Plan: Gestión de servicios para cátedra

**Branch**: `003-gestion-servicios-catedra` | **Date**: 2026-08-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-gestion-servicios-catedra/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Hoy la pestaña Servicios le muestra a la cátedra sus propios contenedores en modo solo lectura: los
botones de apagar/encender viven en `servicios.py` detrás de `require_admin`, y no existe reinicio
ni consola para nadie. Esta feature abre esas capacidades a la cátedra sobre sus propios servicios
(y, por extensión natural, se las suma también al administrador sobre cualquier servicio) sin tocar
el modelo de datos de `Servicio` ni la máquina de estados de `Pedido`. El enfoque técnico tiene dos
partes de complejidad muy distinta: (1) apagar/encender/reiniciar son extensiones directas del
patrón ya existente en `orquestacion_service.py` (cambiar el gate de permisos de `require_admin` a
verificación de propiedad, más un endpoint nuevo de reinicio que llama al reboot nativo de Proxmox
para LXC); (2) la consola interactiva requiere que el backend actúe de proxy de WebSocket entre el
navegador y el `termproxy` de Proxmox — el navegador nunca habla directo con Proxmox, cumpliendo el
Principio I de la constitución.

## Technical Context

**Language/Version**: Backend: Python 3.12 (FastAPI, async) — sin cambios. Frontend: JavaScript/JSX
(React 19, Vite 8) — sin cambios.

**Primary Dependencies**: Backend: FastAPI (su soporte nativo de rutas WebSocket), SQLAlchemy async,
proxmoxer (se extiende `ProxmoxClient` con `reboot_lxc` y `abrir_termproxy`); **nueva** dependencia
`websockets` como cliente asíncrono para el lado saliente del proxy (backend → Proxmox). Frontend:
react-router-dom, axios (sin cambios); **nueva** dependencia `@xterm/xterm` (+ `@xterm/addon-fit`)
para renderizar la terminal interactiva de US3.

**Storage**: PostgreSQL — sin cambios de esquema. No se agregan columnas a `Servicio` ni tablas
nuevas: la "sesión de consola" es efímera por diseño (ver `data-model.md`), no un registro de
negocio.

**Testing**: Backend: pytest + pytest-asyncio + httpx, extendiendo `backend/tests/fakes.py`
(`FakeProxmoxClient`) con `reboot_lxc` y knobs de fallo (`fallar_start`/`fallar_stop`/
`fallar_reboot`) que hoy no existen. Aplica la compuerta de calidad de la constitución para US1/US2
(apagar/encender/reiniciar): están en `orquestacion_service.py`, el mismo archivo de "orquestación"
ya cubierto por tests existentes, así que requieren pruebas automatizadas con al menos un camino de
fallo de infraestructura simulado. US3 (consola/WebSocket) se declara explícitamente **exenta** de
esa cobertura automatizada por esta iteración (ver Constitution Check y `research.md` R7); se valida
con los escenarios manuales de `quickstart.md`. Frontend: sin framework de test instalado (igual que
specs previas), validación manual en navegador.

**Target Platform**: Web SPA (Vite) + API FastAPI, mismo despliegue Docker Compose ya existente. El
WebSocket de consola viaja por el mismo puerto 8000 ya expuesto del backend, sin necesidad de un
puerto o proxy inverso adicional.

**Project Type**: Web application (backend + frontend), estructura ya establecida.

**Performance Goals**: SC-003 del spec — abrir la consola de un servicio propio y ver el resultado
de un comando en menos de 15 segundos desde que se elige abrirla.

**Constraints**: El tráfico de la consola MUST viajar exclusivamente a través del backend del
portal; el navegador MUST NOT recibir en ningún momento el host/puerto/ticket de Proxmox de forma
que pueda conectarse directo a él (Principio I). No se persiste ninguna credencial ni ticket de
Proxmox más allá de la vida de la conexión WebSocket activa.

**Scale/Scope**: Cambios acotados a `orquestacion_service.py`, `proxmox_client.py`, `servicios.py`
y sus schemas en el backend; a `Servicios.jsx` y un componente nuevo de consola en el frontend. No
se tocan `Pedido`, su máquina de estados, ni las pantallas de cátedra de la spec 002.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitución evaluada**: v1.1.0, última enmienda 2026-08-15.

| Principio | Resultado | Fundamento |
|-----------|-----------|------------|
| I. Proxmox es el back-end, nunca la interfaz | **PASS — con restricción de diseño explícita** | Es el principio más en juego de esta spec. La consola MUST proxearse por el backend (ver Constraints); el navegador nunca recibe host/puerto/ticket de Proxmox directamente. `research.md` R2 documenta la alternativa rechazada (conexión directa navegador→Proxmox) precisamente por violar este principio. |
| II. La máquina de estados es la única fuente de verdad | **PASS — no aplica a Servicio** | El texto del principio está scoped a `Pedido` ("todo cambio de `estado` de un **pedido**..."). Esta spec no toca `Pedido` ni su tabla de transiciones; `Servicio.estado` sigue el patrón ya existente en `iniciar_servicio`/`detener_servicio` (asignación directa tras una llamada exitosa a Proxmox), que esta spec extiende sin apartarse de ese patrón ya aceptado en el código. |
| III. Toda operación contra la infraestructura debe ser recuperable | **PASS** | Apagar/encender/reiniciar siguen el mismo try/except ya establecido: el estado en base solo se muta después de que Proxmox confirma, y un fallo devuelve 502 sin dejar el registro a mitad de camino. La consola no persiste estado alguno en la base, así que no hay riesgo de fila huérfana; el ticket de Proxmox expira solo del lado de Proxmox si nadie lo usa (`research.md` R3). |
| IV. Aislamiento y cuota por cátedra | **PASS** | Ninguna de las tres capacidades nuevas crea, destruye ni redimensiona un servicio, así que no tocan cuota. El aislamiento se resuelve reusando el mismo chequeo de propiedad (`servicio.catedra_id == current_user.catedra_id`) que ya usan `obtener_servicio` y `estado_en_proxmox`. |
| V. El historial académico no se destruye | **PASS** | No interactúa con soft delete ni con el historial de pedidos. |
| VI. La cátedra pide y observa; el administrador gestiona | **PASS — el texto del principio no cubre este caso; ver nota** | Los bullets ratificados de este principio están explícitamente scoped al *ciclo de vida del pedido* ("aprobar, rechazar y gestionar el ciclo de vida del **pedido** es responsabilidad exclusiva del administrador"). Esta spec no le da a la cátedra ningún poder sobre pedidos — sigue sin poder aprobar ni desplegar nada. Lo que gana es control operativo sobre un servicio que **ya es suyo** (ya aprobado, ya desplegado), acotado a acciones simples con confirmación y sin conceptos de infraestructura (FR-004, FR-007), lo cual es consistente con la frase rectora del principio ("el rol cátedra no es un operador de infraestructura") interpretada como "no debe operar la infraestructura compartida", no como "no puede operar lo propio". Se deja constancia acá en vez de tratarlo como una violación silenciosa. |
| Compuerta de calidad (pruebas) | **PASS — con alcance parcial declarado** | Aplica de lleno a US1/US2 (tocan `orquestacion_service.py`): requieren tests con fallo de infraestructura simulado. US3 (consola) se declara exenta de test automatizado de extremo a extremo por el costo de infraestructura de prueba que implicaría (sí se testea la parte no-WebSocket: ownership y precondición de estado del servicio antes de emitir el ticket) — declaración explícita en vez de darla por cumplida, como exige la constitución. |

**Resultado global**: **PASS**. No hay violaciones que requieran registrarse en Complexity
Tracking; la nota sobre el Principio VI es una interpretación documentada, no una excepción.

**Re-evaluación post-Fase 1**: sin cambios — `data-model.md` y `contracts/` no introducen entidades
persistentes nuevas ni tocan `Pedido`; la arquitectura de proxy de WebSocket definida en
`research.md` R2/R3 es la que sostiene el PASS del Principio I.

## Project Structure

### Documentation (this feature)

```text
specs/003-gestion-servicios-catedra/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/
│   │   ├── proxmox_client.py       # MODIFICADO — + reboot_lxc, abrir_termproxy
│   │   └── orquestacion_service.py # MODIFICADO — + reiniciar_servicio;
│   │                                #   iniciar_servicio/detener_servicio generalizan
│   │                                #   el parámetro admin→usuario (mismo comportamiento)
│   ├── routers/
│   │   └── servicios.py            # MODIFICADO — start/stop pasan de require_admin a
│   │                                #   ownership check; + POST /restart,
│   │                                #   + POST /console-ticket, + WS /console
│   ├── schemas/
│   │   └── servicio.py             # MODIFICADO — + ConsolaTicketResponse
│   └── requirements.txt            # MODIFICADO — + websockets
└── tests/
    ├── fakes.py                    # MODIFICADO — + reboot_lxc, fallar_start/stop/reboot
    └── test_servicios_lifecycle_catedra.py  # NUEVO

frontend/
├── package.json                    # MODIFICADO — + @xterm/xterm, @xterm/addon-fit
├── src/
│   ├── services/api.js             # MODIFICADO — + reiniciarServicio, obtenerTicketConsola
│   ├── pages/Servicios.jsx         # MODIFICADO — acciones visibles para cátedra sobre
│   │                                #   sus propios servicios; confirm() en apagar/reiniciar
│   └── components/
│       └── ConsolaServicio.jsx     # NUEVO — terminal embebida (@xterm/xterm) sobre el
│                                    #   WebSocket de consola
```

**Structure Decision**: Se mantiene la estructura Web application existente. No se crean
directorios nuevos de primer nivel; el único componente nuevo de UI (`ConsolaServicio.jsx`) va
junto a los demás componentes ya existentes en `frontend/src/components/`. El backend no requiere
un router ni un servicio nuevos — se extienden los tres archivos que ya son dueños de este dominio
(`proxmox_client.py`, `orquestacion_service.py`, `servicios.py`), evitando introducir una capa
adicional para tres capacidades que son extensiones directas de lo que ya existe ahí.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No aplica — la Constitution Check no arrojó violaciones. La nota sobre el Principio VI es una
interpretación documentada del alcance del principio, no una excepción que requiera justificar una
alternativa más simple.
