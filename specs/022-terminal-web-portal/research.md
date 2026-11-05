# Research: Terminal web de la consola dentro del portal

Fuentes: `backend/app/services/consola_gate_service.py`, `consola_destino_service.py`, `consola_access_service.py`, `guest_runner_client.py`, `infra/runner/iaas_access.py`, `infra/applications/install.py`, la validación real de la 020 (`docs/infraestructura-laboratorio/validacion-consola-2026-11-04.md`) y la constitución v4.2.0.

## R1. Un relay con ticket individual sí funciona

- **Hecho**: la constitución adoptó la excepción porque un proxy propio con **tokens de API** no llegaba a transmitir (Proxmox exige un **ticket de sesión** para el WebSocket de consola). La 020 comprobó el camino alternativo con navegador y con un cliente propio: `POST /access/ticket` con la identidad individual → `POST /nodes/{n}/lxc/{vmid}/termproxy` → WebSocket `vncwebsocket?port=…&vncticket=…` con la cookie de ese ticket → saludo `usuario:ticket` → `OK` → entrada `0:LONGITUD:DATOS`, redimensionado `1:cols:rows:`. Se abrió la consola real, se inició sesión y se ejecutó `sudo`; funcionó entrando por cualquier nodo.
- **Decisión**: el backend implementa ese mismo cliente (con `websockets`) y reenvía a un WebSocket del navegador. El portal es quien tiene el ticket; la persona sólo tiene su sesión del portal.
- **Alternativas**: seguir con la interfaz de Proxmox (no cumple el objetivo); SSO por cookie compartida (R10).

## R2. Identidad individual por persona, automática

- **Hecho**: el dominio `pve` es del clúster: una identidad creada en un nodo existe en todos (se comprobó con `ivanochoa@pve`). El rol `NapConsola` (`VM.Console` + `VM.Audit`) sobre `/pool/catedra-N` es el mínimo que abre la consola (020, hallazgo 5) y propaga a los contenedores del pool.
- **Decisión**: una identidad por persona, con nombre opaco derivado del id de usuario (`nap-u<id>@pve`; no expone correos), ACL sólo del rol de consola en los pools de las cátedras que posee. Contraseña `secrets.token_urlsafe(32)`, cifrada con el keyring en `identidades_consola`; nunca se muestra.
- **Razón**: cumple FR-008/FR-010 y no requiere que la persona maneje credenciales de infraestructura.

## R3. Acciones cerradas del runner, sin token amplio

- **Decisión**: protocolo `nap-console-identity/1` (patrón de `nap-iaas-access/1`): JSON cerrado por stdin, comando forzado por SSH, sólo biblioteca estándar. Acciones: `ensure` (crear/actualizar identidad, fijar contraseña por stdin, reconciliar ACL del rol de consola sobre los pools indicados y nada más), `retire` (quitar ACL de pools, eliminar la identidad si no quedan), `end_sessions` (terminar `termproxy` de los contenedores indicados **en ese nodo**) y `probe` (permisos efectivos y existencia, sin secretos). Valida rol, nombre de identidad (`^nap-u[0-9]+@pve$`), nombres de pool (`^catedra-[0-9]+$`); rechaza `root@pam`, otros reinos y cualquier privilegio fuera de `NapConsola`.
- **Razón**: el contrato de la 009 prohíbe «un ejecutor de administración general» y un token con `User.Modify`/`Permissions.Modify` sería una vía de escalada.
- **Alternativas**: token amplio (descartado); `pveum` por SSH genérico (descartado, no es cerrado).

## R4. Reconciliador durable (riesgo principal)

- **Decisión**: la verdad *deseada* se calcula de la base: persona activa → conjunto de cátedras que posee y están activas (administración: todas las activas) → pools `catedra-N`. La verdad *aplicada* se guarda en `identidades_consola` (pools, estado, revisión). Un bucle del worker recorre las diferencias y ejecuta `ensure`/`retire`; es idempotente, reintenta lo incierto y deja un estado `con_error` con motivo seguro visible para administración. No hay ganchos en los routers: así los cambios de cualquier camino (alta de usuario, cambio de titular, baja) convergen igual.
- **Pools inexistentes**: NAP crea el pool al desplegar; `ensure` aplica ACL sólo sobre pools existentes y responde los pendientes; el bucle reintenta tras cada despliegue y periódicamente (≤ 30 s).
- **Razón**: Principio III (recuperable) y FR-011; evita perder un alta o un retiro por un fallo entre dos escrituras.

## R5. Retiro: reutilizar el trámite de la 009 con ejecución automática

- **Hecho**: reducir acceso ya crea un `CambioAccesoConsola` que bloquea operaciones y espera que un operador revoque y registre evidencia; hoy es manual.
- **Decisión**: el reconciliador ejecuta el retiro con las acciones del runner (`retire` y `end_sessions` en **todos** los nodos), verifica con `probe` y registra la evidencia `revocacion_consola` (`entorno: real`, operador `portal-automatico`) con lo observado, y completa el trámite por una vía de sistema. La terminal abierta se corta además por el relay del portal (R6). La evidencia por trámite sigue siendo una declaración auditada; la prueba real de instalación (020) no se sustituye.
- **Razón**: FR-012/FR-013 sin intervención manual y manteniendo el orden bloqueo → revocación → transferencia.

## R6. Sesiones: cupo, inactividad, cierre inmediato

- **Decisión**: `sesiones_terminal` guarda apertura, último latido, cierre solicitado y motivo (sin contenido). El relay (una tarea por sesión) refresca el latido, mide inactividad por **entrada de la persona** (la salida de un comando largo no mantiene viva la sesión), consulta cada 2 s si hay cierre solicitado y cierra al instante en proceso cuando puede. El cupo por persona se cuenta con filas abiertas y vigentes (latido reciente), no con memoria: funciona con más de un proceso. Un retiro, baja o detención marca cierre solicitado y avisa en proceso; en el peor caso el corte ocurre en la siguiente consulta (< 5 s, SC-004).
- **Límites**: mensaje máximo de 64 KiB de entrada, cola de salida acotada (si el navegador no consume, se cierra la sesión), una apertura por vez por persona en el instante del cupo (bloqueo de fila), valores por omisión inactividad 15 min y 3 sesiones, configurables.
- **Auditoría**: `eventos_seguridad` con `terminal_abierta`/`terminal_cerrada` (persona, servicio, nodo, duración, motivo) y filas de `sesiones_terminal`; el relay no registra ni guarda bytes.

## R7. Frontend: terminal

- **Decisión**: `@xterm/xterm` + `@xterm/addon-fit`, empaquetados por Vite (sin CDN), con versión exacta del lockfile y antigüedad ≥ 2 semanas: `@xterm/xterm` 6.0.0 (publicada 2025-12-22) y `@xterm/addon-fit` 0.11.0 (2025-12-22), verificadas con `npm audit`. Mensajes binarios de entrada/salida y un mensaje de control para redimensionar.
- **Razón**: estándar de hecho para terminales web; mismo protocolo de teclas que la consola nativa.

## R8. Autorización y alcance del WebSocket

- **Decisión**: el WebSocket exige la sesión del portal (cookie), valida `Origin` contra los orígenes permitidos (equivalente al CSRF de los POST), resuelve el servicio y comprueba pertenencia, estado encendido, vigencia e identidad confirmada **antes** de tocar la infraestructura, y exige la compuerta de instalación de la 020 (evidencia real, clúster, versión, nodos). La identidad de la persona debe estar `lista` y cubrir la cátedra del servicio; si no, se informa «todavía no está habilitado».
- **Resolución del nodo**: `consola_destino_service.resolver_destino` (020) con `nodos` entendido ahora como direcciones alcanzables **desde el portal**; prueba el nodo del contenedor y luego los demás. La primera apertura que falle por la intermitencia de la consola se reintenta una vez (FR-021).

## R9. Constitución: escenario elegido

- **Decisión**: esta feature **no enmienda** la constitución. La excepción del Principio I queda como respaldo; la terminal del portal es el camino normal y la UI de la persona deja de enlazar a Proxmox. Se conserva `GET /servicios/{id}/consola` (para administración/respaldo) hasta que el equipo decida.
- **Si el equipo retira la excepción** (MAJOR): se elimina ese endpoint y la cláusula de identidad se reformula para describir la identidad individual del portal; ver la tabla del spec.

## R10. SSO por cookie compartida: descartado

- Exige nombres DNS y certificados reales en los nodos y un dominio padre común; con IPs no funciona (el laboratorio), y la persona seguiría viendo la página de consola de Proxmox. No cumple «no entrar al entorno».

## R11. Pasar a las personas con identidad manual (US4)

- **Decisión**: la primera reconciliación crea la identidad gestionada (`ensure`), la valida y actualiza `usuarios.identidad_consola`/inventario (`AUTO-022`), dejando la identidad manual anterior en `inventario_consola_historial`. **El portal no elimina la manual**: el protocolo del nodo es cerrado y sólo acepta nombres gestionados (`nap-u<id>@pve`) por diseño; la elimina el operador con `retirar-acceso.sh --fase identidad` (runbook). Mientras tanto la persona conserva ambos accesos. Es la ruta de adopción y también cubre a quien nunca tuvo identidad.

## R12. Deuda aceptada

- Un único proceso de API: las sesiones viven en él; el cupo y los cortes usan la base para no impedir escalar luego. Reiniciar el portal corta las terminales (aviso al cliente, filas cerradas al arrancar).
- La persona sigue escribiendo `nap` y su contraseña; el inicio automático queda para otra feature.
