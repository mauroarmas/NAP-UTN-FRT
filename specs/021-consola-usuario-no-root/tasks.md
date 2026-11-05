# Tasks: Usuario no root en la consola de Linux IaaS

**Input**: `specs/021-consola-usuario-no-root/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: incluidas. La feature es de seguridad de credenciales, idempotencia y recuperación (Principio III): exige pruebas del runner, del flujo del portal y de higiene de secretos, más un ensayo real.

**Restricción dura (research R4)**: NO modificar `infra/runner/node_executor.py`, `infra/applications/job/*` ni `infra/applications/docker/*`: entran en el `policy_digest`. Sin migración. La contraseña nunca va en `argv`, registros, errores ni auditoría.

**Marca [LAB]**: modifica el clúster real (reinstalar el paquete de nodo, desplegar/actualizar servicios de prueba). **Orden de instalación: nodos primero, portal después.**

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin dependencia pendiente)
- **[Story]**: US1 = entrar como `nap` en servicios nuevos (P1) · US2 = actualizar los ya entregados (P1) · US3 = secretos sólo en «Revelar acceso inicial» (P2)

## Phase 1: Setup

- [x] T001 [P] Comprobar o crear la guarda del digest en `infra/applications/tests/test_policy_digest_estable.py`: fija el `policy_digest()` vigente como constante y falla si cambia (research R4)

## Phase 2: Foundational (bloquea las historias)

- [x] T002 [P] Agregar el campo **opcional** `password_consola` (`^[A-Za-z0-9_-]{32,128}$`) a `configure` en `backend/app/schemas/iaas_access.py`, rechazado en `probe`, y sus pruebas en `backend/tests/test_iaas_access_protocol.py` (contracts/runner-iaas-access.md)
- [x] T003 Extender `infra/runner/iaas_access.py`: con `password_consola`, fijar la contraseña de `nap` con `chpasswd` por stdin si está bloqueada, no cambiar si coincide (`sin_cambios`), no pisar si es otra (`conservada`), dejar `root` con `*`, verificar y devolver `consola` en `result`; sin el campo no toca contraseñas. Pruebas en `infra/runner/tests/test_iaas_access.py` ampliando el doble `Nodo` (sombra de contraseñas, `chpasswd`), incluidos fallos y la ausencia de la contraseña en respuestas

## Phase 3: User Story 1 - Entrar como `nap` en servicios nuevos (P1)

**Goal**: un Linux IaaS nuevo muestra `nap` en «Revelar acceso inicial», la consola admite a `nap`, `root` no, y SSH sigue sin contraseñas.

**Independent Test**: desplegar un Linux nuevo, revelar, abrir la consola como `nap`, `sudo`, rechazo de `root` y de SSH por contraseña.

- [x] T004 [P] [US1] Pruebas del flujo en `backend/tests/test_acceso_consola_021.py` (reutiliza `tests/iaas_ssh_helpers.py`): la creación NO envía `password` a Proxmox; `configure` incluye `password_consola` igual al `guest_password` guardado; `acceso_metadata.username` es `nap`; «Revelar acceso inicial» devuelve `nap` y esa contraseña; un nodo que responde con fallo no entrega el servicio
- [x] T005 [US1] En `backend/app/services/orquestacion_service.py`, no enviar `config['password']` a Proxmox al crear un `proxmox_iaas`; conservar la generación cifrada del `guest_password`
- [x] T006 [US1] En `backend/app/services/iaas_acceso_service.py`, `aplicar(..., password_consola=None)` y `_solicitud` envían el campo cuando corresponde y exigen `consola` ∈ {`aplicada`,`sin_cambios`} en la respuesta cuando se envió
- [x] T007 [US1] En el bloque de preparación IaaS de `backend/app/services/orquestacion_service.py`: pasar la contraseña a `aplicar` para despliegues nuevos, y fijar `acceso_metadata.username = "nap"` y `acceso_metadata.consola` sólo cuando se aplicó; conservar `root` en el resto (reparaciones de clave de servicios no actualizados)
- [x] T008 [US1] Agregar `consola_usuario` (`nap`|`root`) a `GET /servicios/{id}/acceso` en `backend/app/services/service_access_service.py` y `backend/app/schemas/servicio.py` (contracts/api-acceso-consola.md)
- [x] T009 [P] [US1] En `frontend/src/components/AccesoServicio.jsx`, la indicación dentro de la consola nombra al usuario según `consola_usuario` (sin mencionar `root` cuando es `nap`) y prueba en `frontend/tests/acceso-consola-021.test.jsx` (FR-011)
- [ ] T010 [US1] Ejecutar `pytest infra/runner/tests backend/tests/test_acceso_consola_021.py backend/tests/test_acceso_ssh.py backend/tests/test_iaas_access_protocol.py backend/tests/test_iaas_access_client.py backend/tests/test_regresion_servicios_011.py` y el vitest de T009; todo en verde antes de tocar los nodos
- [ ] T011 [LAB] [US1] Reinstalar el paquete de nodo en frt y pve91 (`git archive HEAD` + `install.py --source-root` + `infra/runner/install.sh`), confirmar que el `policy_digest` y los perfiles Docker siguen vigentes (T001), y recrear api/worker del portal
- [ ] T012 [LAB] [US1] Desplegar un Linux nuevo y comprobar de punta a punta: «Revelar acceso inicial» muestra `nap`; inicio de sesión real por la consola como `nap` (verificado con una identidad de ensayo por el protocolo de consola y con confirmación en navegador); `sudo` funciona; `root` rechazado; SSH por contraseña rechazado y por clave entra; la acción privilegiada queda a nombre de `nap` en el registro

**Checkpoint**: servicios nuevos usan `nap`; nodos y portal en la versión nueva.

## Phase 4: User Story 2 - Actualizar los servicios ya entregados (P1)

**Goal**: administración pasa un servicio existente al modelo nuevo sin perder datos, con contraseña nueva e idempotente.

**Independent Test**: con el #42 en uso, actualizar el acceso; datos y clave SSH intactos, `nap` entra con la contraseña nueva, la de `root` ya no sirve; repetir 3 veces no cambia nada.

- [ ] T013 [P] [US2] Pruebas en `backend/tests/test_acceso_consola_021.py`: sólo administración (403 al resto); 409 `servicio_no_linux`/`servicio_detenido`/`operacion_en_curso`/`sin_clave`; 200 `sin_cambios` si ya está actualizado; la contraseña nueva se cifra en el contexto de la operación ANTES de enviar y se promueve a credencial sólo tras confirmar; un fallo definitivo deja la credencial y el usuario anteriores; un resultado incierto se reintenta con la MISMA contraseña; el resultado `conservada` no promueve
- [ ] T014 [US2] Crear `actualizar_acceso_consola` en `backend/app/services/iaas_acceso_service.py` (idempotente por `Idempotency-Key`, operación `reparar` con marca `acceso_consola`, historial «Acceso de consola actualizado: se entra como nap»)
- [ ] T015 [US2] Exponer `POST /servicios/{servicio_id}/acceso-consola` (sólo administración) en `backend/app/routers/servicios.py` (contracts/api-acceso-consola.md)
- [ ] T016 [US2] En el bloque de preparación de `backend/app/services/orquestacion_service.py`: para una operación con `acceso_consola`, enviar la contraseña pendiente y, con confirmación, promoverla a `credenciales_encrypted`, fijar `username = "nap"` y eliminar el secreto pendiente del contexto
- [ ] T017 [P] [US2] Acción «Actualizar acceso de consola» para administración en `frontend/src/components/AccesoServicio.jsx` (visible si `consola_usuario` es `root` en un Linux IaaS), con aviso de que la persona debe volver a revelar el acceso, y prueba en `frontend/tests/acceso-consola-021.test.jsx`
- [ ] T018 [P] [US2] Comando `actualizar-consola --servicio N --clave K` en `docs/infraestructura-laboratorio/scripts/portal/portal_ops.py` (misma lógica que el endpoint, para operar el laboratorio sin navegador)
- [ ] T019 [US2] Ejecutar las suites de T010 más las de T013; en verde
- [ ] T020 [LAB] [US2] Actualizar el #42 (con un archivo de prueba dentro): comprobar que el archivo, la clave SSH y la dirección siguen iguales, que `nap` entra por consola con la contraseña nueva, que `root` quedó bloqueado, y repetir la actualización 3 veces sin que cambie la contraseña de `nap` (SC-003, SC-004)

## Phase 5: User Story 3 - Secretos sólo en «Revelar acceso inicial» (P2)

**Goal**: la contraseña no aparece en ningún registro, error ni auditoría.

**Independent Test**: provocar fallos en despliegue y actualización y buscar el valor en respuestas, registros y auditoría.

- [ ] T021 [P] [US3] Pruebas de higiene en `backend/tests/test_acceso_consola_021.py` e `infra/runner/tests/test_iaas_access.py`: forzar fallos y excepciones del runner y del portal y comprobar que la contraseña (y su hash) no aparece en respuestas, `caplog`, historial ni eventos de seguridad; la revelación queda auditada sin valor; una cátedra ajena sigue rechazada (FR-009, FR-010)
- [ ] T022 [US3] Corregir cualquier fuga que T021 detecte en `backend/app/services/*` o `infra/runner/iaas_access.py`
- [ ] T023 [LAB] [US3] Tras los ensayos reales, buscar la contraseña en los registros del portal (`docker logs api`/`worker`), del runner y del nodo (journal) y en la base (historial y eventos); sin coincidencias (SC-005)

## Phase 6: Polish & cross-cutting

- [ ] T024 [P] Actualizar `docs/runbook-consola-nativa.md` (se entra como `nap`, `root` bloqueado), `docs/infraestructura-laboratorio/scripts/consola/README.md` si corresponde, y anotar la actualización de servicios existentes y el orden nodos→portal
- [ ] T025 Ejecutar las suites completas (`pytest backend/tests infra/runner/tests` en segundo plano; `vitest` en una copia del frontend en el scratchpad); sin regresiones
- [ ] T026 [LAB] Limpiar: dar de baja los servicios de prueba creados, dejar el #42 en su estado previo (detenido), cuenta semilla inactiva, identidades y contenedores temporales borrados
- [ ] T027 Actualizar este `tasks.md`, `spec.md` (Status) y la memoria del proyecto; abrir el PR a `dev` (sin co-autor en los commits; el PR sólo con tu OK)

## Dependencies & Execution Order

- T001, T002 y T003 sin dependencias entre sí; T002 y T003 bloquean US1.
- US1 código (T004–T010) antes de [LAB] (T011–T012). US2 depende del runner (T003) y de T006/T007.
- US3 puede escribirse junto con US1/US2 pero se cierra después de T012 y T020.

```text
T001 ─────────────────────────────────────────────┐
T002 ─┐                                           ▼
T003 ─┴─► T004 ► T005 ► T006 ► T007 ► T008 ► T009 ► T010 ► T011 ► T012
                         └────────────► T013 ► T014 ► T015 ► T016 ► T017,T018 ► T019 ► T020
                                                      T021 ► T022 ─────────────────────► T023
                                                                        T024 ► T025 ► T026 ► T027
```

## Parallel Example

- T001, T002; T004 y T009; T013, T017 y T018; T021 y T024 pueden avanzar en paralelo.

## Implementation Strategy

1. **MVP**: Fase 2 + US1 (T001–T012): servicios nuevos con `nap`.
2. Luego US2 (servicios existentes) y US3 (secretos), con ensayo real cada una.
3. Commits chicos por tarea, sin co-autor; el PR a `dev` al final.
