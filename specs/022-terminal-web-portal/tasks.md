# Tasks: Terminal web de la consola dentro del portal

**Input**: `specs/022-terminal-web-portal/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: incluidas. Es una feature de seguridad (credenciales intermediadas, aislamiento, revocación) y de recuperación (Principio III): exige pruebas de runner, reconciliador, relay y secretos, más un ensayo real.

**Restricciones duras**: no tocar archivos del `policy_digest` del motor Docker (`infra/applications/job/*`, `docker/*`, `node_executor.py`; guarda `test_policy_digest_estable`); la contraseña de la identidad nunca va en `argv`, registros, errores, auditoría ni respuestas; el contenido de la terminal nunca se guarda; ningún token de infraestructura con permisos amplios; la constitución no se enmienda (R9). **Orden de instalación: nodos primero, portal después.**

**Marca [LAB]**: modifica el clúster real (instalar paquete de nodo, crear/retirar identidades, abrir terminales, desplegar servicios de prueba). Hace falta a Ivan para el navegador y la cuenta administradora.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin dependencia pendiente)
- **[Story]**: US1 = abrir la terminal en el portal (P1) · US2 = identidades automáticas (P1) · US3 = sesiones acotadas y auditables (P1) · US4 = adopción y operación (P2)

## Phase 1: Setup

- [x] T001 [P] Fijar en `frontend/package.json` y `package-lock.json` una versión exacta de `@xterm/xterm` y `@xterm/addon-fit` con ≥ 2 semanas de antigüedad (research R7), verificando `npm audit`; instalar en una copia del frontend del scratchpad y comprobar que `vite build` pasa
- [x] T002 [P] Prueba de higiene de datos del laboratorio ampliada: agregar `backend/app/services/terminal_*`, `identidad_consola_service.py`, `infra/runner/console_identity.py` y `docs/runbook-terminal-portal.md` al alcance de `backend/tests/test_sin_datos_lab_020.py`

## Phase 2: Foundational (bloquea las historias)

- [x] T003 Migración `backend/alembic/versions/022_01_terminal_identidades.py` (cabeza anterior `017_01_clave_acceso_servicio`): tablas `identidades_consola` y `sesiones_terminal` (data-model.md) con índices y restricciones; modelos `backend/app/models/identidad_consola.py` y `sesion_terminal.py` registrados; prueba de migración arriba/abajo en `backend/tests/test_migracion_022.py` y actualizar la prueba de cabeza de migraciones existente
- [x] T004 [P] Protocolo `nap-console-identity/1` en `backend/app/schemas/console_identity.py` (copiable al nodo, solo biblioteca estándar): validación cerrada de `ensure`/`retire`/`end_sessions`/`probe`, patrones de identidad y de pool, `password_consola`, y `parse_response`; pruebas en `backend/tests/test_console_identity_protocol.py` (campos extra, valores inválidos, `root@pam`, otros roles)
- [x] T005 Runner `infra/runner/console_identity.py`: acciones cerradas con rutas y comandos fijos (`pveum`, `pvesh`), contraseña por stdin, `ensure` idempotente (crear, fijar contraseña si difiere, ACL del rol `NapConsola` exactamente sobre los pools indicados que existen), `retire`, `end_sessions` (terminar `termproxy` de los vmids en este nodo) y `probe`; respuestas sin secretos; pruebas con doble del nodo en `infra/runner/tests/test_console_identity.py` (idempotencia, no pisar roles ajenos, rechazo de nombres inválidos, ausencia de la contraseña en argv/respuestas)
- [x] T006 Despacho y paquete de nodo: enrutar `nap-console-identity/1` en `infra/runner/nap_guest_runner.py`, registrar los archivos en el mapa de `infra/applications/install.py` y confirmar con `infra/applications/tests/test_policy_digest_estable.py` que el digest no cambia
- [x] T007 Cliente del portal `execute_console_identity` en `backend/app/services/guest_runner_client.py` (mismo SSH y comando forzado que `execute_iaas_access`; solicitud validada, respuesta validada, errores sólo con códigos) y pruebas en `backend/tests/test_console_identity_client.py`

## Phase 3: User Story 2 - Identidades automáticas (P1)

**Goal**: las identidades se crean y retiran solas según las cátedras que posee cada persona.

**Independent Test**: asignar una persona nueva a una cátedra y comprobar que su identidad llega a `lista` sin intervención; quitarle la cátedra y comprobar el retiro con sesiones terminadas y evidencia.

- [x] T008 [P] [US2] Pruebas del reconciliador en `backend/tests/test_identidades_consola_022.py`: deseado = cátedras activas que posee (administración: todas las activas); alta crea con contraseña aleatoria cifrada que nunca aparece en claro; dos personas nunca comparten identidad; cambio de titular converge; pool inexistente queda pendiente y se completa tras el despliegue; fallo/incierto reintenta con la misma contraseña sin duplicar; `con_error` con motivo seguro; retiro parcial conserva la otra cátedra
- [x] T009 [US2] `backend/app/services/identidad_consola_service.py`: cálculo del conjunto deseado desde la base, reconciliación por persona (`ensure`/`retire`/`probe`), contraseña `secrets.token_urlsafe(32)` cifrada con el keyring, estados y `revision`, motivo seguro de error
- [x] T010 [US2] Retiro automático en `backend/app/services/consola_access_service.py`: ejecutar el trámite pendiente con `retire` y `end_sessions` en **todos** los nodos, verificar con `probe`, registrar la evidencia `revocacion_consola` (`entorno: real`, operador `portal-automatico`) y completar el trámite por una vía de sistema; sin tocar el orden bloqueo → revocación → transferencia; pruebas de orden, fallo y reintento en `backend/tests/test_identidades_consola_022.py`
- [x] T011 [US2] Bucle de reconciliación en `backend/app/worker.py` (periódico ≤ 30 s y disparado por despliegues/cambios), con pruebas de convergencia tras reinicio
- [x] T012 [US2] `consola_gate_service.autorizar`: tomar la identidad y su cobertura de `identidades_consola` (estado `lista` y pools que cubren la cátedra) en lugar del perfil privado; conservar la compuerta de instalación (evidencia, clúster, versión, `nodos`); actualizar `backend/tests/test_consola_gate_020.py`, `test_convergencia_seguridad_009.py` y `test_regresion_servicios_011.py` a la nueva fuente
- [x] T013 [P] [US2] API y pantalla de administración: `backend/app/routers/admin_identidades_consola.py` (listar, reintentar, sin credenciales) y `frontend/src/pages/IdentidadesConsola.jsx` con ruta y menú sólo para administración; pruebas `backend/tests/test_admin_identidades_consola_022.py` y `frontend/tests/identidades-consola-022.test.jsx` (contracts/api-identidades-consola.md)
- [x] T014 [US2] Ejecutar `pytest infra/runner/tests backend/tests/test_console_identity_*.py backend/tests/test_identidades_consola_022.py backend/tests/test_admin_identidades_consola_022.py backend/tests/test_consola_gate_020.py backend/tests/test_convergencia_seguridad_009.py backend/tests/test_regresion_servicios_011.py`; todo en verde
- [ ] T015 [LAB] [US2] Instalar el paquete de nodo en frt y pve91 (`git archive HEAD` + `install.py --source-root` plan + `install.sh`), confirmar que el `policy_digest` no cambió, recrear api/worker y comprobar con una persona de prueba nueva que su identidad llega a `lista` sola y que `retire` la elimina

## Phase 4: User Story 1 - Abrir la terminal en el portal (P1)

**Goal**: la persona abre una terminal en el portal, sin ver Proxmox, en cualquier nodo.

**Independent Test**: con un navegador que sólo llega al portal, abrir la terminal de un Linux de cada nodo, iniciar sesión como `nap` y ejecutar `sudo`.

- [ ] T016 [P] [US1] Pruebas del relay en `backend/tests/test_terminal_022.py` con dobles del nodo (ticket, termproxy, WebSocket de infraestructura): admisión (permisos, servicio detenido/sin vigencia, compuerta, identidad no lista → mensajes y códigos del contrato), nodo del contenedor y failover, 503 si ninguno responde, reintento único de la primera apertura, reenvío bidireccional, redimensionado, mensajes > 64 KiB rechazados, cola acotada, `Origin` no permitido, la contraseña nunca en mensajes/registros
- [ ] T017 [US1] `backend/app/services/terminal_relay_service.py`: iniciar sesión con la identidad de la persona (contraseña descifrada sólo en memoria), `termproxy`, WebSocket de infraestructura con verificación TLS contra la CA configurada, reenvío con límites de tamaño y backpressure, redimensionado y reintento único; reutiliza `consola_destino_service.resolver_destino` (`nodos` alcanzables desde el portal)
- [ ] T018 [US1] `backend/app/routers/terminal.py`: `GET /servicios/{id}/terminal` (WebSocket) con sesión del portal, validación de `Origin`, admisión del contrato y cierre con códigos; registrar el router en `app/main.py`
- [ ] T019 [P] [US1] `frontend/src/components/TerminalConsola.jsx` (xterm + fit, WebSocket binario, redimensionado, avisos y cierre) integrado en `AccesoServicio.jsx` como «Abrir terminal»; quitar el enlace a Proxmox de la persona (mantener «Consultar consola» sólo como respaldo de administración); pruebas `frontend/tests/terminal-consola-022.test.jsx` con doble de WebSocket
- [ ] T020 [US1] Ejecutar las suites de T014 más `backend/tests/test_terminal_022.py` y los vitest de T019; en verde
- [ ] T021 [LAB] [US1] Verificación real en frt y pve91: abrir la terminal desde un cliente que sólo llega al portal (sin ruta a los nodos), un Linux por nodo, iniciar sesión como `nap`, `sudo`; confirmar con Ivan en el navegador; comprobar que no aparece ninguna pantalla de Proxmox

## Phase 5: User Story 3 - Sesiones acotadas y auditables (P1)

**Goal**: inactividad, cupo por persona, cierre inmediato y auditoría sin contenido.

**Independent Test**: inactividad hasta el cierre; abrir hasta el cupo y ver el rechazo; dar de baja el servicio con una terminal abierta; buscar texto tecleado en la auditoría.

- [ ] T022 [P] [US3] Pruebas en `backend/tests/test_terminal_sesiones_022.py`: cupo por persona con bloqueo de fila (carrera de dos aperturas), inactividad por entrada de la persona (no por salida), latido y sesiones huérfanas liberadas, cierre solicitado por retiro/baja/detención/cuenta en < 5 s, cierre al reiniciar el portal, auditoría `terminal_abierta`/`terminal_cerrada` con duración y motivo, ausencia de contenido y contraseñas en tablas, registros y respuestas
- [ ] T023 [US3] `backend/app/services/terminal_sesiones_service.py` y su integración en el relay (T017/T018): cupo, latido, inactividad configurable (15 min), consulta cada 2 s de cierre solicitado, cierre y auditoría; configuración en `app/config.py` (inactividad, cupo, tamaño de mensaje)
- [ ] T024 [US3] Disparar el cierre solicitado desde retiro de acceso, baja y detención de servicio y desactivación de cuenta (`orquestacion_service`, `consola_access_service`, `usuarios`), con pruebas
- [ ] T025 [US3] Cierre al arrancar el portal de las filas abiertas (`reinicio_portal`) y avisos de cierre al cliente; prueba de arranque
- [ ] T026 [LAB] [US3] En real: inactividad hasta el cierre, cupo, baja de servicio con terminal abierta y retiro de una persona con terminal abierta (corte < 5 s, no reabre, su otra cátedra sigue), y búsqueda de la contraseña y del texto tecleado en logs del portal, base completa, nodos y contenedor (SC-004/SC-006/SC-007)

## Phase 6: User Story 4 - Adopción y operación (P2)

**Goal**: personas con identidad manual pasan al modelo gestionado; procedimiento reutilizable.

- [ ] T027 [P] [US4] Pruebas de adopción en `backend/tests/test_identidades_consola_022.py`: crea la gestionada, valida con `probe`, retira la manual sólo después, actualiza `usuarios.identidad_consola` e inventario (`AUTO-022`); la persona conserva acceso durante la transición; falla a mitad no deja a la persona sin acceso
- [ ] T028 [US4] Implementar la adopción en `identidad_consola_service.py`
- [ ] T029 [LAB] [US4] Adoptar la identidad manual de Ivan (`ivanochoa@pve`): comprobar que su terminal funciona antes y después y que la manual desaparece del clúster
- [ ] T030 [P] [US4] `docs/runbook-terminal-portal.md` (habilitación, evidencia de revocación de la 020, instalación nodos → portal, límites configurables, operación y retiro) sin valores del laboratorio; enlazar desde `docs/runbook-consola-nativa.md` y `docs/conexion-infraestructura.md`; ampliar la guarda de datos del laboratorio (T002)

## Phase 7: Polish & cross-cutting

- [ ] T031 Ejecutar las suites completas (`pytest backend/tests infra/runner/tests infra/applications/tests` en segundo plano; `vitest` en una copia del frontend) y comparar con la línea base conocida (3 fallas previas por orden de ejecución en `caplog`); sin regresiones nuevas
- [ ] T032 [LAB] Limpiar el laboratorio: servicios y personas de prueba, identidades temporales, cuenta semilla inactiva, archivos con contraseñas destruidos
- [ ] T033 Actualizar este `tasks.md`, `spec.md` (Status) y la memoria del proyecto; abrir el PR a `master` (sin co-autor en los commits; el PR sólo con el OK de Ivan)

## Dependencies & Execution Order

- Fase 1 y Fase 2 primero; T004 y T005 son independientes entre sí; T003 bloquea el reconciliador y el relay; T007 bloquea T009.
- US2 (aprovisionamiento) antes que US1: sin identidad `lista` la terminal no abre. T012 depende de T009.
- US1 depende de T012 y T017; US3 se integra sobre US1 (T023 modifica el relay).
- US4 depende de US2.

```text
T001,T002 ─────────────────────────────────────────────────────────┐
T003 ──┬────────────────────────────────────────────────────────┐  │
T004,T005 ► T006 ► T007 ► T008 ► T009 ► T010 ► T011 ► T012 ► T013 ► T014 ► T015
                                              └───────────────► T016 ► T017 ► T018 ► T019 ► T020 ► T021
                                                                          T022 ► T023 ► T024 ► T025 ► T026
                                                          T027 ► T028 ► T029        T030
                                                                       T031 ► T032 ► T033
```

## Implementation Strategy

1. **MVP**: Fases 1–2 + US2 + US1 (T001–T021): identidades automáticas y terminal abierta en ambos nodos.
2. Luego US3 (límites, cortes, auditoría) y US4 (adopción y runbook), con ensayo real cada una.
3. Commits chicos por tarea, sin co-autor; el PR al final, con tu OK.
