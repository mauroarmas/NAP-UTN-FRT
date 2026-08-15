---

description: "Task list for feature implementation"
---

# Tasks: Gestión de servicios para cátedra

**Input**: Design documents from `/specs/003-gestion-servicios-catedra/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: SÍ se incluyen para US1 y US2 — tocan `orquestacion_service.py`, dentro del alcance de la
compuerta de calidad de la constitución (ver Constitution Check en [plan.md](./plan.md)). US3
(consola) se testea de forma automatizada solo en sus rechazos (403/409), no en el relay de
WebSocket en sí — declarado así explícitamente en [research.md](./research.md) R7; el resto de US3
se valida con [quickstart.md](./quickstart.md).

**Organization**: US1 = apagar/encender (P1, MVP), US2 = reiniciar (P2), US3 = consola interactiva
(P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivo distinto, sin dependencias pendientes)
- **[Story]**: US1, US2 o US3, según [spec.md](./spec.md)
- Todas las rutas son relativas a la raíz del repositorio

## Path Conventions

Aplicación web: `backend/app/`, `backend/tests/`, `frontend/src/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencias nuevas que esta feature necesita (ninguna existía antes)

- [X] T001 [P] Agregar `websockets==16.*` a `backend/requirements.txt` como dependencia directa
      (hoy solo llega transitivamente vía `uvicorn[standard]`) e instalar con
      `pip install -r requirements.txt` dentro del entorno del backend
- [X] T002 [P] Agregar `@xterm/xterm` y `@xterm/addon-fit` a `frontend/package.json` y correr
      `npm install` en `frontend/`

**Checkpoint**: dependencias instaladas, sin cambios de comportamiento todavía

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Helper de autorización compartido y doble de prueba extendido, de los que dependen
las tres historias

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase

- [X] T003 [P] En `backend/app/services/orquestacion_service.py`, agregar
      `requiere_propio_o_admin(servicio: Servicio, usuario: Usuario) -> None`: no hace nada si
      `usuario.rol == RolUsuario.ADMIN`; si no, levanta `HTTPException(403, "Sin permisos")` cuando
      `servicio.catedra_id != usuario.catedra_id`. Centraliza el chequeo que hoy está duplicado en
      `obtener_servicio` y `estado_en_proxmox` (`servicios.py`, ahora importan el helper), y que
      esta feature multiplicaría a 6 copias si se siguiera duplicando (FR-005). Se ubica en
      `orquestacion_service.py` en vez de `servicios.py`: es donde `iniciar_servicio`/
      `detener_servicio` ya fetchean el `Servicio` (el router no lo pre-fetchea para esos
      endpoints), así que es el lugar natural para las cuatro acciones nuevas/modificadas
- [X] T004 [P] Extender `backend/tests/fakes.py` (`FakeProxmoxClient`): agregar parámetros
      `fallar_start`, `fallar_stop`, `fallar_reboot` (excepciones opcionales, mismo patrón que
      `fallar_create`/`fallar_delete`); hacer que `start_lxc`/`stop_lxc` levanten su excepción
      correspondiente si está seteada, antes de registrar el cambio de estado; agregar
      `reboot_lxc(node, vmid)` (respeta `fallar_reboot`, registra en `self.reiniciados`, no cambia
      `self.estados`) y `abrir_termproxy(node, vmid)` (devuelve
      `{"user": "test@pve", "ticket": "PVE:fake", "port": "5900"}`)

**Checkpoint**: helper de autorización y doble de prueba listos; comportamiento observable de la
API sigue idéntico

---

## Phase 3: User Story 1 - Apagar y encender mi propio servicio (Priority: P1) 🎯 MVP

**Goal**: La cátedra apaga y enciende sus propios servicios sin depender de un administrador.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, apagarlo desde
Servicios y verificar que queda detenido; desde uno propio detenido, encenderlo y verificar que
queda en ejecución. Ninguna de las dos requiere intervención de un administrador.

### Tests for User Story 1 ⚠️

> **Escribir estas pruebas PRIMERO y confirmar que fallan antes de implementar**

- [X] T005 [US1] Crear `backend/tests/test_servicios_lifecycle_catedra.py` cubriendo, para
      `POST /servicios/{id}/start` y `POST /servicios/{id}/stop`: cátedra actúa sobre su propio
      servicio (200, `estado` refleja el cambio); cátedra recibe 403 sobre un servicio de otra
      cátedra (usar una segunda cátedra + `factories.crear_servicio` para el servicio ajeno);
      acción sobre estado inválido devuelve 409 (parar uno ya `stopped`, iniciar uno ya `running`);
      fallo de infraestructura simulado (`proxmox.fallar_stop` / `proxmox.fallar_start`) devuelve
      502 sin que `Servicio.estado` haya cambiado en la base (depende de T003, T004)

### Implementation for User Story 1

- [X] T006 [US1] En `backend/app/routers/servicios.py`, cambiar `start`/`stop` de
      `Depends(require_admin)` a `Depends(get_current_user)`, y llamar a
      `_requiere_propio_o_admin(servicio, current_user)` antes de ejecutar la acción (depende de
      T003, T005)
- [X] T007 [US1] En `backend/app/services/orquestacion_service.py`, renombrar el parámetro `admin:
      Usuario` a `usuario: Usuario` en `iniciar_servicio` y `detener_servicio` (mismo
      comportamiento; refleja que ya no son exclusivas de administrador) (depende de T006)
- [X] T008 [US1] En `frontend/src/pages/Servicios.jsx`, mostrar la columna "Acciones" (estado,
      stop, start) también para la cátedra sobre sus propios servicios, no solo para `isAdmin` —
      la lista que le llega ya viene filtrada a lo suyo por el backend, así que alcanza con quitar
      la condición `isAdmin &&` alrededor de esa columna; el `confirm('¿Detener el servicio?')` que
      ya tiene `handleStop` se hereda sin cambios porque es el mismo handler para ambos roles
      (depende de T006)
- [X] T009 [US1] Validación manual: correr Escenarios 1, 2 y 3 de
      [quickstart.md](./quickstart.md) — confirmar el pedido de confirmación al apagar, la
      ausencia de confirmación al encender, y el mensaje en lenguaje simple ante estado inválido.
      Verificado en navegador real contra el clúster Proxmox de producción (no un doble de
      prueba): apagar y encender el servicio `cat1-svc2` (VMID 100) funcionaron correctamente,
      con y sin confirmación según corresponde.

**Checkpoint**: US1 completa y verificable de forma independiente — MVP entregable.

---

## Phase 4: User Story 2 - Reiniciar mi propio servicio (Priority: P2)

**Goal**: La cátedra reinicia sus propios servicios en ejecución en una sola acción.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, reiniciarlo con una
única acción y verificar que vuelve a quedar en ejecución (no que queda detenido esperando un
segundo paso).

### Tests for User Story 2 ⚠️

> **Escribir estas pruebas PRIMERO y confirmar que fallan antes de implementar**

- [X] T010 [P] [US2] En `backend/app/services/proxmox_client.py`, agregar
      `reboot_lxc(node: str, vmid: int) -> str` que llama a
      `self.api.nodes(node).lxc(vmid).status.reboot.post()`, mismo estilo que `start_lxc`/
      `stop_lxc` (depende de Foundational; independiente de T005-T009)
- [X] T011 [US2] Agregar a `backend/tests/test_servicios_lifecycle_catedra.py` casos para
      `POST /servicios/{id}/restart`: cátedra reinicia su propio servicio en ejecución (200, sigue
      `running`); 403 sobre servicio ajeno; 409 si no está en ejecución; 502 con
      `proxmox.fallar_reboot` sin que `Servicio.estado` cambie (depende de T004; mismo archivo que
      T005, ejecutar después)

### Implementation for User Story 2

- [X] T012 [US2] En `backend/app/services/orquestacion_service.py`, agregar
      `reiniciar_servicio(db, servicio_id, usuario)`: valida existencia/propiedad implícita vía el
      router, exige `estado == RUNNING` (409 si no, con el estado actual en el mensaje), llama a
      `reboot_lxc`, y **no** reasigna `Servicio.estado` (sigue `RUNNING` antes y después) — mismo
      patrón try/except → 502 que `iniciar_servicio`/`detener_servicio` (depende de T010, T011)
- [X] T013 [US2] En `backend/app/routers/servicios.py`, agregar
      `POST /servicios/{servicio_id}/restart` (`Depends(get_current_user)` +
      `_requiere_propio_o_admin`), delegando en `reiniciar_servicio` (depende de T003, T012)
- [X] T014 [US2] En `frontend/src/services/api.js`, agregar
      `export const reiniciarServicio = (id) => api.post(\`/servicios/${id}/restart\`);`
- [X] T015 [US2] En `frontend/src/pages/Servicios.jsx`, agregar el botón "🔁 Reiniciar" junto a
      Start/Stop en la misma columna de Acciones (visible en las mismas condiciones que T008: admin
      sobre cualquiera, cátedra sobre lo propio), solo habilitado cuando `estado === 'running'`, con
      `confirm('¿Reiniciar el servicio?')` antes de llamar a `reiniciarServicio` (depende de T008,
      T014)
- [X] T016 [US2] Validación manual: correr Escenario 4 de [quickstart.md](./quickstart.md).
      Verificado en navegador real contra el clúster Proxmox de producción: reiniciar
      `cat1-svc2` (VMID 100) pidió confirmación y el servicio quedó "Corriendo" después,
      confirmado también contra `proxmox.reiniciados` en la suite automatizada.

**Checkpoint**: US1 + US2 completas — apagar, encender y reiniciar disponibles para la cátedra
sobre lo propio y para el administrador sobre cualquier servicio.

---

## Phase 5: User Story 3 - Consola interactiva de mi propio servicio (Priority: P3)

**Goal**: La cátedra abre una terminal real de su propio servicio, embebida en el portal, sin
recibir nunca credenciales ni acceso directo a Proxmox.

**Estado real (2026-08-15)**: implementación completa según el diseño del plan, validada contra
Proxmox real (192.168.1.92) — start/stop/restart de US1/US2 confirmados funcionando de punta a
punta contra el clúster real. La emisión de ticket (`console-ticket`) y la apertura del WebSocket
de consola también funcionan (se autentica, conecta y negocia el subprotocolo correctamente contra
Proxmox — se corrigieron en el camino tres bugs reales: formato del header `Authorization`
`PVEAPIToken=...`, negociación del subprotocolo `binary`, y el framing de los mensajes como frames
binarios en vez de texto). Lo que **no** quedó resuelto: Proxmox cierra la conexión saliente al
cabo de un rato corto sin transmitir ningún byte de vuelta, así que la terminal nunca llega a
mostrar contenido real. Investigar esto más a fondo requiere acceso a los logs del lado de Proxmox
(`journalctl` en el host, o el log de la tarea `vncproxy` por su UPID) que no está disponible en
este entorno. Por pedido explícito del usuario, se abandona esta línea de investigación por ahora
al no ser un requerimiento indispensable — T025 queda sin marcar en consecuencia.

**US3 EN PAUSA (2026-08-15, decisión posterior)**: la consola se retira del alcance de la cátedra
hasta la entrevista con el profesor (duda 1.1 de [DUDAS-ENTREVISTA.md](../../DUDAS-ENTREVISTA.md)),
porque antes de resolver *cómo* dar consola hay que definir *si* la cátedra debe tener acceso al
contenedor. Se sospecha además una causa concreta del fallo, no confirmada: Proxmox no aceptaría
API tokens para el websocket de consola, y haría falta un ticket de sesión (`POST /access/ticket`
con usuario y contraseña; en el `.env` solo hay token). Concretamente:

- Se quitó el botón de consola de la cátedra en `frontend/src/pages/Servicios.jsx`.
- `POST /servicios/{id}/console-ticket` pasó a exigir administrador; los tests fijan esa
  restricción para que no se reabra por accidente.
- Se agregó `GET /servicios/consola/proxmox-base` (solo admin) y un botón "🖥️ Consola" que abre la
  consola nativa de Proxmox en otra pestaña. Es solo para admin, que ya tiene sesión propia en
  Proxmox: no viola el Principio I porque la cátedra sigue sin llegar nunca a esa interfaz.
- `ConsolaServicio.jsx` y la ruta WebSocket quedan en el repo, marcados como en pausa y sin uso.

**Independent Test**: Con sesión de cátedra y un servicio propio en ejecución, abrir su consola
desde Servicios, escribir un comando y ver su resultado, todo sin abandonar el portal ni recibir
una URL o credencial de Proxmox.

### Tests for User Story 3 (parciales — ver nota de alcance) ⚠️

> **Escribir estas pruebas PRIMERO y confirmar que fallan antes de implementar**

- [X] T017 [US3] Agregar a `backend/tests/test_servicios_lifecycle_catedra.py` casos para
      `POST /servicios/{id}/console-ticket`: 403 sobre servicio ajeno; 409 si el servicio no está
      en ejecución. **No** se testea automáticamente la emisión exitosa del ticket contra Proxmox
      ni el WebSocket de consola (research.md R7) — ambos casos negativos se resuelven antes de
      tocar Proxmox, así que no requieren el `abrir_termproxy` del fake (depende de T004; mismo
      archivo que T005/T011, ejecutar después)

### Implementation for User Story 3

- [X] T018 [P] [US3] En `backend/app/services/proxmox_client.py`, agregar
      `abrir_termproxy(node: str, vmid: int) -> dict` que llama a
      `self.api.nodes(node).lxc(vmid).termproxy.post()` y devuelve la respuesta tal cual
      (`{user, ticket, port}`) (independiente de T017; depende de Foundational)
- [X] T019 [US3] En `backend/app/schemas/servicio.py`, agregar
      `class ConsolaTicketResponse(BaseModel): ticket: str; expira_en_segundos: int`
- [X] T020 [US3] En `backend/app/services/orquestacion_service.py`, agregar un emisor de tickets
      propios del portal (un solo uso, corta vida — p. ej. 30s — atados a `servicio_id` +
      `usuario_id`, guardados en un diccionario en memoria del proceso con su expiración; no se
      persiste en base, ver `data-model.md`): `emitir_ticket_consola(db, servicio_id, usuario) ->
      ConsolaTicketResponse` (exige `estado == RUNNING`, 409 si no; llama a `abrir_termproxy` y
      guarda internamente node/vmid/ticket/puerto de Proxmox asociados al ticket propio) y
      `consumir_ticket_consola(servicio_id, ticket) -> dict | None` (devuelve los datos de Proxmox
      asociados si el ticket es válido, no vencido y no usado antes; lo invalida al consumirlo)
      (depende de T018)
- [X] T021 [US3] En `backend/app/routers/servicios.py`, agregar
      `POST /servicios/{servicio_id}/console-ticket` (`Depends(get_current_user)` +
      `_requiere_propio_o_admin`), delegando en `emitir_ticket_consola` (depende de T003, T017,
      T020)
- [X] T022 [US3] En `backend/app/routers/servicios.py`, agregar la ruta
      `@router.websocket("/{servicio_id}/console")`: lee `ticket` de los query params, lo valida
      con `consumir_ticket_consola`; si es inválido, cierra la conexión inmediatamente; si es
      válido, abre con `websockets` una conexión saliente al `vncwebsocket` de Proxmox usando el
      puerto/ticket obtenidos de `abrir_termproxy`, y hace relay bidireccional de bytes entre esa
      conexión y la del navegador hasta que cualquiera de las dos se cierre (FR-009) (depende de
      T001, T020)
- [X] T023 [US3] Crear `frontend/src/components/ConsolaServicio.jsx`: al montarse, pide un ticket
      vía `POST /servicios/{id}/console-ticket`, instancia una terminal `@xterm/xterm` +
      `@xterm/addon-fit` ajustada al contenedor, abre un WebSocket nativo del navegador contra
      `/api/v1/servicios/{id}/console?ticket=...`, conecta la entrada de la terminal al socket
      (`onData` → `socket.send`) y los mensajes entrantes del socket a la terminal (`socket.onmessage`
      → `terminal.write`), y cierra el socket al desmontarse el componente (depende de T002, T019,
      T022)
- [X] T024 [US3] En `frontend/src/pages/Servicios.jsx`, agregar el botón "🖥️ Consola" en la misma
      columna de Acciones (mismas condiciones de visibilidad que T008/T015), habilitado solo cuando
      `estado === 'running'`, que abre `ConsolaServicio` para ese servicio (depende de T008, T023)
- [ ] T025 [US3] Validación manual: correr Escenarios 5, 6 y 7 de
      [quickstart.md](./quickstart.md) — incluye cronometrar que el resultado de un comando
      aparece en menos de 15 segundos desde el clic en "Consola"

**Checkpoint**: US1 + US2 + US3 completas — las tres capacidades del spec disponibles para cátedra
sobre lo propio y para administrador sobre cualquier servicio.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verificación final de aislamiento, paridad de admin, y regresión

- [X] T026 [P] Validación manual: correr Escenario 8 de [quickstart.md](./quickstart.md) —
      apagar/encender/reiniciar/consola sobre un servicio ajeno rechazados con 403 en las cuatro
      acciones (FR-005, SC-004). Cubierto por la suite automatizada (403 verificado para las
      cuatro acciones contra un servicio de otra cátedra) más el navegador real para
      apagar/encender/reiniciar contra Proxmox; la consola no se pudo ejercitar en vivo de punta a
      punta (ver nota de estado real en la Fase 5), pero su chequeo de propiedad en
      `console-ticket` sí quedó verificado por test.
- [X] T027 [P] Validación manual: correr Escenario 9 de [quickstart.md](./quickstart.md) — el
      administrador puede ejecutar las cuatro acciones sobre un servicio de cualquier cátedra, no
      solo la propia (FR-006). Confirmado por test automatizado (admin sobre servicio ajeno) para
      las cuatro acciones.
- [X] T028 Revisar `backend/app/routers/servicios.py` y confirmar que `start`, `stop`, `restart` y
      `console-ticket` pasan los cuatro por `requiere_propio_o_admin` — ningún endpoint nuevo
      quedó afuera del chequeo de propiedad (FR-005). Confirmado: los tres primeros delegan en
      funciones de `orquestacion_service.py` que llaman al helper; `console-ticket` también, vía
      `emitir_ticket_consola`. La ruta WebSocket de consola no repite el chequeo porque el ticket
      que exige ya fue emitido bajo ese chequeo (de un solo uso, atado a servicio_id + usuario_id).
- [X] T029 [P] Correr `pytest` en `backend/` y confirmar que toda la suite pasa en verde,
      incluyendo `test_servicios_lifecycle_catedra.py`. 52/52 en verde.
- [X] T030 [P] Correr `npm run build` y `npm run lint` en `frontend/` y confirmar que no hay
      errores ni warnings nuevos respecto de los ya preexistentes. Build limpio; único warning
      nuevo es el `exhaustive-deps` intencional de `ConsolaServicio.jsx` (omitir `onClose` de las
      deps evita reabrir la conexión en cada render).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — puede arrancar de inmediato
- **Foundational (Phase 2)**: depende de Setup solo para T001 (websockets, usado recién en T022);
  T003/T004 no dependen de Setup — BLOQUEA a las tres historias
- **User Story 1 (Phase 3)**: depende de Foundational; es el MVP, no depende de US2 ni US3
- **User Story 2 (Phase 4)**: depende de Foundational; T010 es independiente de toda la Fase 3,
  pero T015 (frontend) reutiliza la columna de Acciones que agrega T008, así que en la práctica
  conviene completar US1 antes
- **User Story 3 (Phase 5)**: depende de Foundational y de T001 (Setup); T024 (frontend) reutiliza
  la misma columna de Acciones de T008/T015
- **Polish (Phase 6)**: depende de que US1, US2 y US3 estén completas

### Within Each User Story

- Los tests de cada historia se escriben antes que su implementación correspondiente y deben
  fallar primero
- Las tres historias agregan test cases al **mismo archivo**
  (`test_servicios_lifecycle_catedra.py`) — T005, T011 y T017 son secuenciales entre sí, no
  paralelas
- Las tres historias agregan botones a la **misma columna** de `Servicios.jsx` — T008, T015 y T024
  son secuenciales entre sí

### Parallel Opportunities

- T001 y T002 (Setup) en paralelo — archivos distintos
- T003 y T004 (Foundational) en paralelo — archivos distintos
- T010 (US2, `proxmox_client.py`) puede avanzar en paralelo con toda la Fase 3 (US1) — no comparte
  archivo ni depende de ella
- T018 (US3, `proxmox_client.py`) puede avanzar en paralelo con T017 (mismo motivo que T010)
- T026, T027, T029, T030 (Polish) en paralelo entre sí — validaciones independientes

---

## Parallel Example: Foundational + inicio de US2

```bash
# Foundational, en paralelo:
Task: "Agregar _requiere_propio_o_admin en backend/app/routers/servicios.py"
Task: "Extender FakeProxmoxClient en backend/tests/fakes.py con reboot_lxc y knobs de fallo"

# Una vez terminada Foundational, esto puede arrancar sin esperar a que US1 termine:
Task: "Agregar reboot_lxc en backend/app/services/proxmox_client.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational
3. Completar Phase 3: User Story 1
4. **Parar y validar**: Escenarios 1-3 de quickstart.md
5. Esto ya resuelve la fricción más común (apagar/encender sin pedírselo al admin)

### Incremental Delivery

1. Setup + Foundational → listo para las tres historias
2. Agregar US1 → validar de forma independiente → MVP demostrable
3. Agregar US2 → validar de forma independiente → reinicio en un paso
4. Agregar US3 → validar de forma independiente → consola interactiva completa
5. Agregar Polish → aislamiento, paridad de admin, regresión

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes entre sí
- [Story] mapea cada tarea a US1, US2 o US3 para trazabilidad con spec.md
- US1 y US2 llevan test automatizado con fallo de infraestructura simulado (compuerta de calidad
  de la constitución); US3 lo lleva solo para sus rechazos, declarado así explícitamente
- Commitear después de cada tarea o grupo lógico
- Parar en cada checkpoint para validar la historia de forma independiente
