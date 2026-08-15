# Quickstart: Panel simple para cátedra

Guía de validación manual end-to-end. No hay framework de test automatizado de frontend en el
repo (ver `plan.md`, Technical Context); esta feature no toca orquestación/máquina de
estados/cuotas, así que tampoco dispara la compuerta de pruebas automatizadas de la constitución
(ver Constitution Check en `plan.md`). La validación es en navegador.

## Prerrequisitos

- Proyecto levantado localmente: `./docker-dev.sh up` (o `docker compose up`), disponible en
  `http://localhost:5173` (frontend) y `http://localhost:8000` (API).
- Datos de prueba cargados: `backend/scripts/seed_dev.py` (crea una cátedra y un usuario
  `catedra` / `catedra`, y un usuario `admin` con acceso completo).
- Al menos un template de recurso creado (requisito previo para poder pedir un servicio — si no
  existe, crearlo como admin desde la sección Templates).

## Escenario 1 — Pantalla principal de cátedra sin datos de admin (US1)

1. Iniciar sesión con el usuario `catedra` / `catedra`.
2. Verificar que la pantalla principal muestra: un acceso directo para crear un pedido, y el
   estado de los propios pedidos/servicios de esa cátedra.
3. Verificar que **no** aparece: tabla de otras cátedras, conteos globales del sistema, ni estado
   del nodo/clúster de Proxmox.
4. Cerrar sesión e iniciar como `admin`. Verificar que la pantalla principal de administrador sigue
   mostrando lo que mostraba antes de esta feature (sin regresión).

**Resultado esperado**: cumple FR-001, FR-002, FR-009 y SC-002.

## Escenario 2 — Cátedra sin servicios todavía (edge case de US1)

1. Iniciar sesión con una cátedra recién creada, sin pedidos ni servicios.
2. Verificar que la pantalla principal muestra un estado vacío que invita a crear el primer
   pedido, no una tabla vacía sin contexto.

**Resultado esperado**: cumple el edge case correspondiente de `spec.md`.

## Escenario 3 — Crear un pedido en un paso desde la pantalla principal (US2)

1. Con sesión de cátedra activa y cuota disponible, usar el acceso directo de "nuevo pedido" desde
   la pantalla principal.
2. Verificar que el único dato pedido es el tipo de servicio (template); ningún campo de
   infraestructura (nodo, VMID) aparece en el flujo.
3. Confirmar el pedido y cronometrar el tiempo desde que se llegó a la pantalla principal hasta que
   el pedido queda creado.
4. Verificar que el pedido recién creado aparece en la lista de "pedidos recientes" de la pantalla
   principal de la cátedra, con su estado inicial.

**Resultado esperado**: cumple FR-003, FR-004, SC-001 (< 1 minuto).

## Escenario 4 — Cuota insuficiente (edge case de US2)

1. Con una cátedra sin cuota disponible para el template elegido, intentar crear el pedido.
2. Verificar que el sistema informa la falta de cuota en lenguaje claro, sin exponer detalles
   técnicos de infraestructura.

**Resultado esperado**: cumple el segundo acceptance scenario de US2.

## Escenario 5 — El pedido nuevo llega de inmediato al administrador (US2)

1. Con el pedido creado en el Escenario 3 todavía reciente, iniciar sesión como `admin` (o
   cambiar de usuario en otra pestaña).
2. Ir a la bandeja de gestión de pedidos y verificar que el pedido de la cátedra ya aparece,
   listo para revisar/aprobar/rechazar, sin haber requerido ninguna acción extra de la cátedra.

**Resultado esperado**: cumple FR-007, FR-008, SC-003.

## Escenario 6 — Estado de servicios en lenguaje simple (US1)

1. Con sesión de cátedra activa y al menos un servicio desplegado (activo, apagado y, si es
   posible reproducir, en error), revisar la pantalla principal.
2. Verificar que cada servicio se identifica como "Activo", "Apagado" o "Con problemas" — no como
   el código técnico (`running`/`stopped`/`paused`/`error`).
3. Verificar que se muestra el consumo de cuota (vCPU/RAM/disco) en relación a lo asignado a esa
   cátedra, sin métricas del nodo físico compartido.

**Resultado esperado**: cumple FR-005, FR-006, SC-004.
