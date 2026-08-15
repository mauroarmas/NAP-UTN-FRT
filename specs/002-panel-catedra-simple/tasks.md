---

description: "Task list for feature implementation"
---

# Tasks: Panel simple para cátedra

**Input**: Design documents from `/specs/002-panel-catedra-simple/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/endpoints-reutilizados.md](./contracts/endpoints-reutilizados.md), [quickstart.md](./quickstart.md)

**Tests**: NO se incluyen tareas de test automatizado. El feature no toca orquestación, máquina de
estados ni cálculo de cuotas (ver Constitution Check en [plan.md](./plan.md)), así que la compuerta
de pruebas de la constitución no aplica; y el repo no tiene framework de test de frontend instalado
(ver Technical Context en [plan.md](./plan.md)). La validación es manual, contra los 6 escenarios de
[quickstart.md](./quickstart.md).

**Organization**: Tareas agrupadas por historia de usuario. US1 = pantalla principal simple de
cátedra (P1, MVP). US2 = pedir un servicio en un paso desde esa pantalla (P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede correr en paralelo (archivo distinto, sin dependencias pendientes)
- **[Story]**: US1 o US2, según [spec.md](./spec.md)
- Todas las rutas son relativas a la raíz del repositorio

## Path Conventions

Aplicación web: cambios exclusivamente en `frontend/src/`. El backend no se toca en este feature
(ver [research.md](./research.md) R1: los endpoints que hacen falta ya existen y ya filtran por
cátedra del lado del servidor).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización de proyecto/dependencias

No aplica — proyecto existente, stack ya instalado (React 19 + Vite, `axios`,
`react-router-dom`); esta feature no agrega dependencias nuevas (ver Technical Context en
[plan.md](./plan.md)). Se pasa directo a Foundational.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Preparar el vocabulario de estados compartido y el punto de entrada por rol en el
dashboard, del que dependen ambas historias de usuario

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase

- [X] T001 [P] Crear `frontend/src/constants/estados.js` que exporte `ESTADO_PEDIDO_CONFIG` (el
      mismo objeto de 8 estados — ícono, label, badge — hoy definido en
      `frontend/src/pages/Pedidos.jsx`, movido tal cual sin cambiar valores) y
      `ESTADO_SERVICIO_SIMPLE` (mapeo de 3 categorías para cátedra: `running` → "Activo",
      `stopped`/`paused` → "Apagado", `error` → "Con problemas", según
      [data-model.md](./data-model.md))
- [X] T002 Actualizar `frontend/src/pages/Pedidos.jsx` para importar `ESTADO_PEDIDO_CONFIG` desde
      `../constants/estados.js` (como `ESTADO_CONFIG`) en lugar de definirlo localmente; eliminar
      la definición local duplicada (depende de T001)
- [X] T003 Crear `frontend/src/components/PanelCatedra.jsx` con el esqueleto del componente (recibe
      `user` como prop) y la carga de datos: `getPedidos()`, `listarServicios()` y
      `getCatedra(user.catedra_id)` desde `frontend/src/services/api.js` (ya existentes, sin
      cambios); todavía sin JSX de presentación (depende de T001)
- [X] T004 En `frontend/src/pages/Dashboard.jsx`, agregar una rama de retorno temprano: si
      `!isAdmin`, renderizar `<PanelCatedra user={user} />` y salir; dejar la rama de
      administrador exactamente como está hoy, sin modificarla (FR-002, FR-009; depende de T003)

**Checkpoint**: la cátedra ve el esqueleto de `PanelCatedra` (sin contenido rico todavía) en lugar
del dashboard de admin; el administrador no ve ningún cambio.

---

## Phase 3: User Story 1 - Pantalla principal simple para la cátedra (Priority: P1) 🎯 MVP

**Goal**: La cátedra ve, en su pantalla principal, el estado de sus propios pedidos y servicios y
el consumo de su cuota, sin ningún dato reservado al administrador.

**Independent Test**: Iniciar sesión como cátedra y verificar que la pantalla principal solo
muestra información propia (Escenarios 1, 2 y 6 de [quickstart.md](./quickstart.md)); verificar en
paralelo que el administrador no sufrió ninguna regresión.

### Implementation for User Story 1

- [X] T005 [US1] En `frontend/src/components/PanelCatedra.jsx`, renderizar la sección "Mis pedidos
      recientes": los últimos pedidos (orden por `created_at` descendente, tope de 5) con
      ícono/label/badge de `ESTADO_PEDIDO_CONFIG` (FR-001)
- [X] T006 [US1] En `frontend/src/components/PanelCatedra.jsx`, renderizar la sección "Mis
      servicios": por cada servicio, hostname y categoría simple (`ESTADO_SERVICIO_SIMPLE`) en vez
      del código técnico de estado (FR-001, FR-005)
- [X] T007 [US1] En `frontend/src/components/PanelCatedra.jsx`, renderizar el resumen de cuota
      (vCPU, RAM, disco: uso vs. asignado) a partir de la respuesta `CatedraConUso` de
      `getCatedra(user.catedra_id)`, sin mostrar el nodo físico ni datos de otras cátedras (FR-006)
- [X] T008 [US1] En `frontend/src/components/PanelCatedra.jsx`, agregar el estado vacío: si la
      cátedra no tiene pedidos ni servicios, mostrar un mensaje que invite a crear el primer
      pedido en lugar de secciones vacías sin contexto (edge case de [spec.md](./spec.md))
- [X] T009 [US1] Validación manual: correr los Escenarios 1, 2 y 6 de
      [quickstart.md](./quickstart.md) — confirmar que no aparece tabla de otras cátedras, conteos
      globales ni estado de infraestructura, y que la vista de administrador sigue igual

**Checkpoint**: User Story 1 completa y verificable de forma independiente — cátedra ve su propio
resumen simple; administrador sin regresión.

---

## Phase 4: User Story 2 - Pedir un servicio de forma rápida (Priority: P2)

**Goal**: Desde la pantalla principal, la cátedra llega al formulario de pedido ya abierto, elige
solo el tipo de servicio (sin datos de infraestructura), y el pedido queda visible de inmediato
para el administrador.

**Independent Test**: Desde `PanelCatedra`, usar el acceso directo de "nuevo pedido", completar el
formulario ya abierto en `/pedidos` y confirmar que el pedido aparece tanto en "Mis pedidos
recientes" como en la bandeja del administrador (Escenarios 3, 4 y 5 de
[quickstart.md](./quickstart.md)).

### Implementation for User Story 2

- [X] T010 [P] [US2] En `frontend/src/components/PanelCatedra.jsx`, agregar el botón/CTA "Nuevo
      pedido" que navega a `/pedidos` pasando `{ state: { abrirNuevo: true } }` vía `useNavigate`
      de `react-router-dom` (FR-003)
- [X] T011 [P] [US2] En `frontend/src/pages/Pedidos.jsx`, leer `location.state?.abrirNuevo` con
      `useLocation` e inicializar `showNuevo` en `true` cuando venga en `true`, de modo que el
      formulario "Nuevo Pedido" (ya existente, solo pide `template_id`) esté abierto al llegar sin
      navegación adicional (FR-003, FR-004)
- [X] T012 [US2] Validación manual: correr el Escenario 3 de [quickstart.md](./quickstart.md) —
      cronometrar que el flujo completo (desde la pantalla principal hasta el pedido creado) toma
      menos de 1 minuto y que ningún paso pide datos de infraestructura (SC-001, FR-004)
- [X] T013 [US2] Validación manual: correr el Escenario 4 de [quickstart.md](./quickstart.md) —
      con una cátedra sin cuota suficiente, confirmar que el mensaje `Cuota excedida: ...` que ya
      devuelve el backend (`backend/app/services/pedido_service.py`) se muestra en el frontend sin
      exponer detalles de infraestructura (edge case de US2)
- [X] T014 [US2] Validación manual: correr el Escenario 5 de [quickstart.md](./quickstart.md) —
      confirmar que el pedido recién creado por la cátedra aparece de inmediato en la bandeja de
      gestión del administrador, sin ninguna acción manual adicional (FR-007, FR-008, SC-003)

**Checkpoint**: User Story 2 completa. Con US1 + US2, el MVP cubre todos los requisitos funcionales
y criterios de éxito de [spec.md](./spec.md).

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Verificación final de alcance y limpieza

- [X] T015 [P] Revisar `frontend/src/components/PanelCatedra.jsx` y confirmar que no importa ni
      referencia datos reservados a administrador (otras cátedras, estado de nodo/clúster) —
      chequeo contra el Principio VI de la constitución
- [X] T016 Correr los 6 escenarios completos de [quickstart.md](./quickstart.md) de punta a punta
      (incluye re-verificar US1 y US2 juntos) y marcarlos como pasados
- [X] T017 [P] Revisar `frontend/src/pages/Dashboard.jsx` y eliminar cualquier import o variable
      que haya quedado sin uso tras extraer `PanelCatedra.jsx`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no aplica, sin tareas
- **Foundational (Phase 2)**: sin dependencias externas — BLOQUEA a US1 y US2
- **User Story 1 (Phase 3)**: depende de Foundational; sin dependencia de US2
- **User Story 2 (Phase 4)**: depende de Foundational; el CTA que agrega (T010) vive en el mismo
  componente que construye US1, así que en la práctica conviene completar US1 antes, aunque no hay
  un bloqueo técnico estricto entre ambas
- **Polish (Phase 5)**: depende de que US1 y US2 estén completas

### Within Each User Story

- T005–T008 (US1) tocan el mismo archivo (`PanelCatedra.jsx`) → secuenciales, no paralelas entre sí
- T010 y T011 (US2) tocan archivos distintos → paralelizables entre sí

### Parallel Opportunities

- T001 no tiene dependencias previas dentro de Foundational; T002, T003 dependen de T001
- Dentro de US2: T010 (`PanelCatedra.jsx`) y T011 (`Pedidos.jsx`) en paralelo
- T015 y T017 (Polish) son revisiones de archivos distintos, paralelizables entre sí

---

## Parallel Example: User Story 2

```bash
# T010 y T011 tocan archivos distintos y pueden avanzar en paralelo:
Task: "Agregar CTA 'Nuevo pedido' en frontend/src/components/PanelCatedra.jsx (navega con state.abrirNuevo)"
Task: "Leer location.state.abrirNuevo en frontend/src/pages/Pedidos.jsx para abrir el formulario automáticamente"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 2: Foundational
2. Completar Phase 3: User Story 1
3. **Parar y validar**: correr Escenarios 1, 2 y 6 de quickstart.md
4. Este MVP ya resuelve el problema reportado (pantalla de cátedra sin datos de admin), aunque la
   creación de pedido todavía requiera un paso extra de navegación manual a "Pedidos"

### Incremental Delivery

1. Foundational → listo para ambas historias
2. Agregar US1 → validar de forma independiente → esto ya es demostrable
3. Agregar US2 → validar de forma independiente → feature completo según spec.md
4. Agregar Polish → validación final de punta a punta

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes entre sí
- [Story] mapea cada tarea a US1 o US2 para trazabilidad con spec.md
- Sin tareas de test automatizado: ver la nota "Tests" al inicio de este documento
- Cero tareas de backend: confirmado en research.md R1 — los endpoints necesarios ya existen y ya
  filtran por cátedra en el servidor
- Commitear después de cada tarea o grupo lógico
- Parar en cada checkpoint para validar la historia de forma independiente
