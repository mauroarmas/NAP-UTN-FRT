# Quickstart: Gestión de servicios para cátedra

Guía de validación manual. US1/US2 (apagar/encender/reiniciar) tienen además pruebas automatizadas
(ver `plan.md`, Testing); esta guía es la validación de extremo a extremo en navegador, y la única
cobertura formal de US3 (consola), declarada así en el Constitution Check.

## Prerrequisitos

- Proyecto levantado localmente (`./docker-dev.sh up` o `docker compose up`).
- Un usuario cátedra con al menos un servicio propio **en ejecución** (desplegado por un admin
  previamente — reusar el flujo de la spec 002 para generar el pedido, y el de despliegue ya
  existente para llevarlo a `running`).
- Un usuario cátedra con al menos un servicio propio **detenido**, para probar encender.

## Escenario 1 — Apagar un servicio propio (US1)

1. Iniciar sesión como cátedra, ir a Servicios.
2. Sobre un servicio propio en ejecución, elegir "Apagar".
3. Verificar que el sistema pide confirmación antes de ejecutar la acción.
4. Confirmar y verificar que el estado pasa a "Detenido" sin recargar la página.

**Resultado esperado**: cumple FR-001, FR-010, SC-001.

## Escenario 2 — Encender un servicio propio (US1)

1. Sobre un servicio propio detenido, elegir "Encender".
2. Verificar que la acción se ejecuta **sin** pedir confirmación.
3. Verificar que el estado pasa a "Corriendo" sin recargar la página.

**Resultado esperado**: cumple FR-001, FR-010, SC-001.

## Escenario 3 — Acción inválida para el estado actual (US1, edge case)

1. Sobre un servicio propio ya detenido, intentar "Apagar" de nuevo (o forzar la llamada si la UI
   ya oculta el botón).
2. Verificar que el mensaje de error está en lenguaje simple, sin detalles técnicos de
   infraestructura.

**Resultado esperado**: cumple FR-007.

## Escenario 4 — Reiniciar un servicio propio (US2)

1. Sobre un servicio propio en ejecución, elegir "Reiniciar".
2. Verificar que pide confirmación antes de ejecutar.
3. Confirmar y verificar que el servicio vuelve a quedar "Corriendo" (una sola acción, sin pasos
   intermedios visibles para la cátedra).

**Resultado esperado**: cumple FR-002, SC-002.

## Escenario 5 — Abrir la consola de un servicio propio (US3, alcance v3.0.0)

> **Redefinido el 2026-08-30.** Estos escenarios medían una terminal embebida en el portal, que
> resultó no ser implementable: Proxmox no acepta API tokens para el WebSocket de consola. El
> acceso se resuelve derivando a la consola de Proxmox, y esa derivación es la única excepción
> nombrada al Principio I de la constitución.

1. Con una cuenta de **cátedra**, sobre un servicio propio en ejecución, verificar que aparece la
   acción de consola.
2. Verificar que el destino es la consola del **contenedor concreto** —su VMID y su nodo—, no un
   panel de gestión de Proxmox.
3. Verificar que el portal no ofrece la acción sobre servicios de otras cátedras (no aparecen
   siquiera en el listado).

**Resultado esperado**: cumple FR-003 y FR-004 con el alcance vigente. La sesión del otro lado la
resuelve Proxmox contra la identidad de la persona, delimitada a su pool.

## Escenario 6 — La derivación no ensancha la excepción (US3, Principio I)

1. Recorrer la pantalla de Servicios con una cuenta de cátedra.
2. Verificar que **ninguna otra acción** sale del portal: apagar, encender, reiniciar, renovar y
   consultar estado siguen resolviéndose dentro.
3. Verificar que no hay enlaces hacia paneles, listados ni pantallas de gestión de Proxmox.

**Resultado esperado**: la excepción se limita a la sesión interactiva, como exige el Principio I
enmendado.

## Escenario 7 — Consola sobre un servicio detenido (US3, edge case)

1. Sobre un servicio propio detenido, verificar que la acción de consola **no se ofrece**.
2. Verificar que el servicio sí ofrece "Iniciar", que es la acción que corresponde.

**Resultado esperado**: no se ofrece un acceso que no puede funcionar (FR-008).

## Escenario 8 — Aislamiento entre cátedras (FR-005, SC-004)

1. Con sesión de una cátedra, intentar apagar, encender, reiniciar o abrir la consola de un
   `servicio_id` que pertenece a otra cátedra (llamando directo al endpoint, ya que la UI no debería
   ofrecer ese ID).
2. Verificar que las cuatro acciones devuelven un rechazo (`403`), igual que ya ocurre hoy al leer
   un servicio ajeno.

**Resultado esperado**: cumple FR-005, SC-004.

## Escenario 9 — El administrador conserva y gana las mismas capacidades (FR-006)

1. Iniciar sesión como admin.
2. Verificar que puede apagar, encender, reiniciar y abrir consola sobre un servicio de **cualquier**
   cátedra (no solo la propia), tal como ya podía con apagar/encender antes de esta feature.

**Resultado esperado**: cumple FR-006.


---

## Estado de la validación de US3 (2026-08-30)

Ejecutada con Playwright sobre el frontend real, con cuenta de **cátedra**, contra el clúster
Proxmox VE 9.2.2. Tres servicios: dos en ejecución y uno detenido.

| Verificación | Resultado |
|---|---|
| La cátedra ve la acción de consola en sus servicios en ejecución | ✅ 2 de 2 |
| El destino apunta al contenedor concreto (`vmid` + `node`), no a un panel | ✅ `?console=lxc&vmid=102&node=proxmox` |
| El servicio detenido **no** ofrece consola, y sí ofrece "Iniciar" | ✅ |
| Ningún otro enlace sale del portal | ✅ los 2 únicos externos son de consola |
| `GET /servicios/consola/proxmox-base` con rol cátedra | ✅ 200 (antes 403) |
| `POST /servicios/{id}/console-ticket` | ✅ 404 — la consola embebida se retiró entera |

**Lo que se retiró**: `ConsolaServicio.jsx`, el relay de WebSocket, el endpoint de ticket, el
emisor y consumidor de tickets en el servicio de orquestación, el schema `ConsolaTicketResponse`
y las dependencias `@xterm/xterm` y `@xterm/addon-fit`. No quedó superficie muerta.

**Lo que sigue sosteniendo el portal**: la pertenencia del servicio. Un servicio de otra cátedra no
se lista ni se resuelve por id, así que el enlace nunca se ofrece. La excepción del Principio I
cubre la sesión interactiva, no el aislamiento.
