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

## Escenario 5 — Abrir la consola de un servicio propio (US3)

1. Sobre un servicio propio en ejecución, elegir "Consola".
2. Verificar que se abre una terminal interactiva dentro del portal (sin salir de la pestaña, sin
   ninguna URL visible hacia Proxmox).
3. Escribir un comando simple (por ejemplo `whoami` o `ls`) y verificar que aparece su resultado.
4. Cronometrar desde el clic en "Consola" hasta ver el resultado del comando: debe ser menor a 15
   segundos.

**Resultado esperado**: cumple FR-003, FR-004, SC-003, SC-005.

## Escenario 6 — Cerrar la consola al navegar (US3, FR-009)

1. Con la consola abierta del Escenario 5, navegar a otra pantalla del portal (por ejemplo,
   Dashboard).
2. Volver a Servicios y reabrir la consola del mismo servicio.
3. Verificar que se trata de una sesión nueva (no una reconexión automática a la anterior).

**Resultado esperado**: cumple FR-009.

## Escenario 7 — Consola sobre un servicio detenido (US3, edge case)

1. Sobre un servicio propio detenido, intentar abrir "Consola".
2. Verificar que el sistema explica que el servicio debe estar en ejecución, sin ofrecer un acceso
   que no puede funcionar.

**Resultado esperado**: cumple FR-008.

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
