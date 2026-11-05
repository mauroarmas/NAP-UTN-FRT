# 023 — Paginar el listado de pedidos

**Status**: Implementada (pendiente de revisión del PR)

## Problema
`GET /pedidos/` devolvía todos los pedidos de una vez y la pantalla buscaba en el navegador sobre esa lista completa. Con el uso del
laboratorio (y más aún en la universidad) la respuesta crece sin límite.

## Contrato
`GET /api/v1/pedidos/` → `{ "items": [PedidoResponse], "next_cursor": string | null }`, del más reciente al más antiguo.

| Parámetro | Detalle |
|---|---|
| `limit` | 1–100, por defecto 20 |
| `cursor` | el `next_cursor` de la respuesta anterior; opaco (base64 de fecha de creación + id). Inválido → 422 `cursor_invalido` |
| `estado` | igual que antes; se aplica antes de paginar |
| `q` | búsqueda en el servidor, sin distinguir mayúsculas: Nº (con o sin `#`), nombre del servicio, nombre de la cátedra, descripción, modelo de servicio y etiqueta visible del estado (p. ej. «aclaración»). `%` y `_` se toman literales |

Orden estable `(created_at desc, id desc)`: el cursor no repite ni salta pedidos aunque entren pedidos nuevos entre páginas.
El alcance no cambia: administración ve todos, una cátedra sólo los suyos.

**Cambio incompatible**: antes la respuesta era una lista. Los consumidores internos se actualizaron (pantalla de Pedidos, Servicios,
pruebas). Servicios necesita todos los aprobados y usa `getPedidosTodos`, que sigue los cursores.

## Pantalla de Pedidos
- Botón «Cargar más pedidos»; el contador muestra `20+` mientras haya más.
- El refresco automático (5 s) vuelve a pedir desde la primera página hasta la que la persona tiene abierta, para no dejar huecos si llegan pedidos nuevos.
- La búsqueda espera 350 ms, se hace en el servidor y vuelve a la primera página.

## Límite conocido
La búsqueda por texto ya no cubre la etiqueta de vigencia («Vigencia…»), que sólo existía en el navegador.

## Pruebas
`backend/tests/test_pedidos_paginacion.py` (orden, cursor, empates, límites, estado, búsqueda, comodines, alcance por cátedra) y
`frontend/tests/e2e/pedidos-paginacion.spec.js`.
