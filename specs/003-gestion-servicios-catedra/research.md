# Research: Gestión de servicios para cátedra

## R1: ¿Cómo reiniciar un contenedor LXC en Proxmox?

- **Decision**: Usar el endpoint nativo de reinicio de Proxmox para LXC
  (`nodes/{node}/lxc/{vmid}/status/reboot`, expuesto por `proxmoxer` como
  `api.nodes(node).lxc(vmid).status.reboot.post()`), agregado como `reboot_lxc(node, vmid)` en
  `ProxmoxClient`, siguiendo exactamente el mismo patrón que `start_lxc`/`stop_lxc`.
- **Rationale**: Es una única llamada atómica del lado de Proxmox (apagado + encendido
  gestionados por el propio hypervisor), coherente con la Assumption del spec ("reinicio
  estándar"). No requiere que nuestro backend orqueste dos llamadas separadas (stop luego start),
  lo que evitaría una ventana donde el servicio quede "stopped" en nuestra base si el proceso se
  interrumpe entre medio.
- **Alternatives considered**: Implementar el reinicio en el backend como `stop_lxc` seguido de
  `start_lxc`. Se descarta: agrega una ventana de estado intermedio real (el contenedor
  efectivamente apagado) que el reboot nativo de Proxmox no tiene, y duplica lógica de manejo de
  errores para dos llamadas en vez de una.

## R2: Arquitectura de la consola — el navegador nunca habla directo con Proxmox

- **Decision**: El backend actúa de proxy de WebSocket. El navegador abre un WebSocket contra
  **nuestro propio backend** (`wss://.../api/v1/servicios/{id}/console`); el backend, al recibir
  esa conexión, abre su propia conexión saliente al `termproxy`/`vncwebsocket` de Proxmox y relay
  bytes en ambas direcciones mientras la conexión del navegador esté viva. El navegador nunca
  recibe el host, puerto ni ticket de Proxmox.
- **Rationale**: Es la única arquitectura compatible con el Principio I de la constitución
  ("Proxmox es el back-end, nunca la interfaz"). El propio spec lo exige en FR-004.
- **Alternatives considered**: Devolverle al navegador el host/puerto/ticket de Proxmox y que el
  `xterm.js` del frontend abra el WebSocket directo contra Proxmox (patrón que usa la propia
  consola web de Proxmox). **Rechazada**: expondría la infraestructura subyacente directamente al
  navegador de la cátedra, violando el Principio I de forma literal — es exactamente el escenario
  que ese principio existe para prevenir.

## R3: Autenticación del lado de Proxmox para abrir la consola

- **Decision**: El backend solicita el ticket de consola llamando a
  `nodes/{node}/lxc/{vmid}/termproxy` (expuesto como `abrir_termproxy(node, vmid)` en
  `ProxmoxClient`) usando la misma autenticación por API token que ya usa para todas las demás
  llamadas (`create_lxc`, `start_lxc`, etc. — ver `proxmox_client.py`). Proxmox devuelve
  `{user, ticket, port}`; el backend usa ese ticket para abrir su propia conexión saliente al
  `vncwebsocket` de Proxmox.
- **Rationale**: `termproxy` es una llamada REST autenticada más — no requiere un modelo de
  autenticación distinto al que ya usa el resto de `ProxmoxClient`. El ticket que devuelve es
  válido para el handshake del WebSocket independientemente de que la llamada que lo generó haya
  sido autenticada con token de API (no se necesita el ticket de sesión de usuario/contraseña que
  usa la interfaz web de Proxmox).
- **Alternatives considered**: Ninguna — no hay un mecanismo alternativo documentado por Proxmox
  para este flujo; se valida el detalle exacto de la respuesta contra la instancia real durante la
  implementación (riesgo de integración bajo: incluso si el formato de respuesta difiere
  ligeramente de lo documentado, es un ajuste de parseo, no un cambio de arquitectura).

## R4: Autenticación del WebSocket de consola desde el navegador

- **Decision**: Emitir un ticket de consola propio (del portal, no de Proxmox), de un solo uso y
  vida corta, desde un endpoint REST ya autenticado con el Bearer JWT normal
  (`POST /servicios/{id}/console-ticket`); el frontend abre el WebSocket pasando ese ticket como
  query param (`GET .../servicios/{id}/console?ticket=...`).
- **Rationale**: El WebSocket nativo del navegador no permite mandar headers custom en el
  handshake, así que el `Authorization: Bearer` que usa el resto de la app (ver el interceptor de
  `services/api.js`) no puede viajar tal cual. Poner el JWT de sesión completo en la URL lo
  expondría en logs de acceso; un ticket de un solo uso, de vida corta y atado al servicio y a la
  persona que lo pidió, acota esa superficie sin cambiarle el modelo de autenticación al resto del
  sistema.
- **Alternatives considered**: Pasar el JWT de sesión completo como query param — rechazado, queda
  registrado en logs de acceso del servidor. Adoptar autenticación por cookies para todo el
  sistema — rechazado, el resto de la app ya funciona con JWT vía header y cambiar ese modelo solo
  para esta feature sería inconsistente y de alcance mucho mayor al pedido.

## R5: Cliente WebSocket saliente en el backend

- **Decision**: Usar el paquete `websockets` (cliente asíncrono nativo de `asyncio`) para la
  conexión saliente del backend hacia el `vncwebsocket` de Proxmox.
- **Rationale**: Es un simple pipe bidireccional de bytes entre dos WebSockets (navegador↔backend
  y backend↔Proxmox); `websockets` es liviano, estándar y compatible de forma directa con las
  rutas WebSocket nativas de FastAPI (también sobre `asyncio`).
- **Alternatives considered**: `aiohttp` — tiene cliente WebSocket, pero traería consigo toda su
  maquinaria de sesión/conexión HTTP para un caso de uso que no la necesita. `httpx` — no soporta
  WebSockets, descartado.

## R6: Terminal interactiva en el frontend

- **Decision**: `@xterm/xterm` (el paquete activamente mantenido, sucesor del histórico `xterm`)
  más su addon `@xterm/addon-fit` para que la terminal ocupe el tamaño disponible del contenedor
  en la UI.
- **Rationale**: Es el estándar de facto para terminales interactivas embebidas en la web (lo usa
  VSCode, Hyper, y la propia consola web de Proxmox); soporta directamente conectarse a un
  WebSocket de texto/binario como el que expone `R2`.
- **Alternatives considered**: Implementar un emulador de terminal propio — rechazado sin
  discusión, es reinventar una rueda compleja y bien resuelta para un problema que no lo amerita.

## R7: Alcance de la compuerta de calidad (pruebas automatizadas)

- **Decision**: US1/US2 (apagar, encender, reiniciar) llevan pruebas automatizadas con al menos
  un camino de fallo de infraestructura simulado, extendiendo `backend/tests/fakes.py` con
  `reboot_lxc` y knobs `fallar_start`/`fallar_stop`/`fallar_reboot`. US3 (consola) se declara
  **exenta** de prueba automatizada de extremo a extremo (el relay de bytes sobre WebSocket) —
  sí se cubren con test automatizado las partes no-WebSocket: que `POST /console-ticket` rechace
  servicios ajenos (403) y servicios que no estén en ejecución (409/400).
- **Rationale**: `orquestacion_service.py` ya está dentro del alcance de la compuerta de calidad
  de la constitución (toca "orquestación"); US1/US2 caen ahí sin ambigüedad. El relay de WebSocket
  de US3 no cambia estado ni cuota — probarlo de punta a punta requeriría levantar un servidor
  WebSocket falso que imite el protocolo de `termproxy` de Proxmox, una inversión de
  infraestructura de test que no se justifica en esta iteración; la constitución permite declarar
  esta clase de compuerta como no verificada automáticamente en el plan en lugar de darla por
  cumplida, así que se declara acá en vez de fingir cobertura.
- **Alternatives considered**: Cubrir también el relay con un servidor WebSocket falso end-to-end.
  Se deja como mejora futura si la consola demuestra ser frágil en uso real; no se justifica
  construirla de entrada para una capacidad que además tiene su propio timeout de sesión (FR-009)
  que acota el radio de un fallo no detectado.

## R8: Confirmación de acciones disruptivas (apagar / reiniciar)

- **Decision**: Reusar el mismo patrón ya presente en `Servicios.jsx` (`confirm()` nativo del
  navegador, ya usado hoy para "¿Detener el servicio?" del lado admin) para apagar y reiniciar
  desde el lado cátedra, sin introducir una librería de diálogos nueva. Encender no pide
  confirmación.
- **Rationale**: Ya resuelto en la sesión de `/speckit-clarify` del spec (ver `spec.md` §
  Clarifications). Reusar el patrón nativo ya existente en el mismo archivo evita divergencia de
  estilo entre la acción de stop que ya tiene el admin y las nuevas que gana la cátedra.
- **Alternatives considered**: Ninguna — decisión ya tomada en la clarificación del spec; esto
  solo documenta cómo se traduce a la implementación existente.

## Resumen de unknowns resueltos

Ningún ítem del Technical Context quedó como NEEDS CLARIFICATION. El único riesgo de integración
no verificable sin acceso al clúster real (formato exacto de la respuesta de `termproxy`, R3) es
de bajo impacto — un ajuste de parseo, no de arquitectura — y se resuelve durante la
implementación, no bloquea el diseño.
