# Research: Panel simple para cátedra

## R1: ¿El backend necesita endpoints nuevos para esta spec?

- **Decision**: No. Los endpoints que la pantalla de cátedra necesita ya existen y ya aplican el
  filtrado por cátedra del lado del servidor:
  - `GET /pedidos/` — filtra por `catedra_id` para roles no-admin (`backend/app/routers/pedidos.py`).
  - `GET /servicios/` — ídem (`backend/app/routers/servicios.py`).
  - `GET /catedras/{id}` — devuelve `CatedraConUso` (cuota + uso actual + servicios activos) y
    responde 403 si la cátedra pide un `id` que no es el suyo (`backend/app/routers/catedras.py`).
  - `POST /pedidos/` — crea un pedido solo con `template_id` y `parametros_extra` opcional; nunca
    pide VMID ni nodo (`backend/app/schemas/pedido.py`, `PedidoCreate`).
- **Rationale**: Los Principios I y IV de la constitución ya estaban aplicados en estos endpoints
  antes de esta spec. El problema que la motivó era exclusivamente de presentación en el frontend:
  `Dashboard.jsx` le mostraba a la cátedra la misma información agregada que ve el administrador.
- **Alternatives considered**: crear un endpoint de resumen agregado (p. ej. `GET
  /catedras/{id}/resumen`) que combine pedidos + servicios + cuota en una sola llamada. Se
  descarta para esta iteración: ahorraría dos llamadas HTTP en una pantalla que ya carga rápido,
  lo cual no se justifica en una spec explícitamente acotada a mejoras pequeñas.

## R2: ¿Cómo dar acceso a "crear pedido en un paso" sin duplicar lógica existente?

- **Decision**: Reutilizar el formulario "Nuevo Pedido" que ya existe en
  `frontend/src/pages/Pedidos.jsx` (selección de template, sin campos de infraestructura) en vez de
  reconstruirlo dentro del dashboard. El acceso directo de la pantalla principal de cátedra lleva a
  ese mismo flujo (navegación directa a Pedidos con el formulario ya abierto, o llamado directo al
  mismo helper `createPedido` de `services/api.js`).
- **Rationale**: Ese formulario ya cumple FR-004 (`Pedidos.jsx:154-176`): solo pide elegir un
  template del catálogo, nada de infraestructura. Duplicarlo en el dashboard arriesga que las dos
  copias diverjan con el tiempo — justo el tipo de deuda que la constitución busca evitar.
- **Alternatives considered**: embeber una copia independiente del formulario directamente en el
  dashboard. Se descarta por riesgo de duplicación/divergencia; se prioriza reutilizar el
  componente/lógica ya validada.

## R3: ¿Cómo traducir el estado técnico de un servicio a lenguaje simple para la cátedra?

- **Decision**: Mapeo de 3 categorías para la vista de cátedra, construido sobre el `EstadoServicio`
  ya existente (sin tocar el modelo ni el backend):

  | estado (backend) | categoría cátedra |
  |---|---|
  | `running` | Activo |
  | `stopped` | Apagado |
  | `paused` | Apagado |
  | `error` | Con problemas |

- **Rationale**: La cátedra no necesita distinguir "detenido" de "pausado" para saber si su
  servicio "anda bien"; ese detalle técnico completo (4 estados) se mantiene disponible tal cual en
  `Servicios.jsx` (`ESTADO_CONFIG`) y en la vista de administrador.
- **Alternatives considered**: reusar sin cambios el `ESTADO_CONFIG` de 4 estados que ya usa
  `Servicios.jsx`. Se descarta porque no resuelve el problema que motivó la spec (lenguaje técnico
  para una audiencia no técnica).

## R4: ¿Separar la vista de cátedra en su propio bloque o mantenerla condicional dentro de Dashboard.jsx?

- **Decision**: Separar los dos caminos de renderizado (cátedra / admin) en bloques claramente
  distintos — ya sea con un retorno temprano dentro de `Dashboard.jsx` o extrayendo un componente —
  en vez de intercalar más condicionales `isAdmin &&` sobre la estructura actual.
- **Rationale**: El código actual ya mezcla ambas vistas con condicionales dispersos (`Dashboard.jsx`
  líneas 71 y 93 en la versión pre-spec), que es precisamente el patrón que hizo que la cátedra
  terminara viendo una pantalla pensada para admin. Separar los caminos de renderizado hace
  estructuralmente más difícil que un elemento de admin se filtre a la vista de cátedra por
  descuido futuro.
- **Alternatives considered**: seguir agregando condicionales puntuales sobre la estructura
  existente. Se descarta: es la causa raíz del problema reportado, no una solución.

## Resumen de unknowns resueltos

Ningún ítem de Technical Context quedó marcado como NEEDS CLARIFICATION — todos los datos
necesarios (stack, endpoints disponibles, permisos, formularios existentes) se derivaron
directamente del código del repositorio.
