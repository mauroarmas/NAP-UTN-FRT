# Tasks: Acceso SSH a servicios IaaS Linux

**Input**: `specs/017-acceso-ssh-iaas-linux/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: incluidas. El plan y el quickstart las exigen (seguridad de claves, idempotencia, `policy_digest` constante); la constitución obliga a pruebas en orquestación.

**Restricción dura (research R4)**: NO modificar `infra/runner/node_executor.py`, `infra/applications/job/*` ni `infra/applications/docker/*`. Entran en el `policy_digest`.

**Simplicidad (Principio VII)**: un dato nuevo para la persona (la clave pública), un bloque en el detalle, un botón «Cambiar clave». Usuario fijo `nap`, una clave por servicio.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin dependencia pendiente)
- **[Story]**: US1 = entrar a mi Ubuntu (P1) · US2 = el acceso sigue la vida del servicio (P2) · US3 = cambiar o incorporar clave (P3)

## Phase 1: Setup

- [ ] T001 Confirmar la cabeza de Alembic con `alembic heads` en `backend/` y anotarla en un comentario de `specs/017-acceso-ssh-iaas-linux/plan.md` (sección Storage)
- [ ] T002 Leer completos `backend/app/services/orquestacion_service.py` y `backend/app/routers/operaciones.py` y dejar en `specs/017-acceso-ssh-iaas-linux/research.md` (R7) los puntos exactos donde se agregan el paso `configure/probe` en `bootstrap` IaaS, el tipo `acceso_ssh` y su restricción CHECK en `operaciones_infraestructura`
- [ ] T003 [P] Agregar prueba de no regresión del digest en `infra/applications/tests/test_policy_digest_estable.py`: fija el `policy_digest()` actual como constante y falla si cambia (R4)

## Phase 2: Foundational (bloquea todas las historias)

- [ ] T004 [P] Crear `backend/app/utils/ssh_keys.py`: `validar_clave(texto) -> (tipo, clave_normalizada, huella)`; admite `ssh-ed25519`, `ecdsa-sha2-nistp256/384/521`, `ssh-rsa` ≥ 3072 bits; rechaza clave privada (`clave_ssh_privada`), varias líneas, opciones por delante, caracteres de control, tipo interno distinto del declarado; descarta el comentario; huella `SHA256:` en base64 sin relleno
- [ ] T005 [P] Pruebas de `ssh_keys` en `backend/tests/test_ssh_keys.py` con claves reales de prueba generadas en el test (ed25519, ecdsa, rsa 2048/3072), casos inválidos y huella igual a `ssh-keygen -lf`
- [ ] T006 [P] Crear modelo `ClaveAccesoServicio` en `backend/app/models/clave_acceso_servicio.py` y registrarlo en `backend/app/models/__init__.py` (campos de data-model.md; `servicio_id` único)
- [ ] T007 Crear la migración Alembic en `backend/alembic/versions/` (tabla `claves_acceso_servicio` + valor `acceso_ssh` en el tipo/CHECK de `operaciones_infraestructura` según T002) con `downgrade` completo
- [ ] T008 [P] Agregar `clave_ssh_publica` a `DatosSolicitud` en `backend/app/schemas/pedido.py` (≤ 800, opcional en el esquema; la obligatoriedad se valida en el servicio de admisión)
- [ ] T009 [P] Crear el protocolo `nap-iaas-access/1` en `backend/app/schemas/iaas_access.py` (parser estricto sin dependencias, mismo estilo que `guest_runner.py`: campos exactos, UUID, `vmid` entero, `revision`, `usuario == 'nap'`, tope 16 KiB) y copiarlo como módulo del nodo
- [ ] T010 [P] Pruebas del protocolo en `backend/tests/test_iaas_access_protocol.py` (campos extra/duplicados, clave en `probe`, usuario distinto, tamaño)

**Checkpoint**: base de validación, datos y protocolo lista; sin infraestructura.

## Phase 3: User Story 1 — Entrar a mi Ubuntu desde mi computadora (P1) 🎯 MVP

**Objetivo**: pedir un Ubuntu con clave pública, desplegarlo, ver el comando y entrar por SSH.

**Prueba independiente**: quickstart escenarios 1–4 y 11–12.

### Runner (nodo)

- [ ] T011 [P] [US1] Pruebas del módulo en `infra/runner/tests/test_iaas_access.py`: parseo estricto, identidad (`vmid`/nodo/pool/`resource_uuid`/nonce, `unprivileged`, `lxc`), `configure` y `probe` con `run_command` simulado, idempotencia por `(resource_uuid, revision)`, `GUEST_NOT_RUNNING`, `SSHD_UNAVAILABLE`, y **la clave no aparece en ningún `argv`**
- [ ] T012 [US1] Implementar `infra/runner/iaas_access.py` (solo biblioteca estándar): verificación de identidad previa a todo efecto; `configure` (usuario `nap` sin contraseña en `sudo`, `/etc/sudoers.d/nap-acceso` 0440, `~nap/.ssh/authorized_keys` 0600 con solo la clave recibida, `/etc/ssh/sshd_config.d/50-nap-acceso.conf`, `sshd -t`, habilitar y recargar `ssh`) y `probe` (escucha en 22, banner `SSH-2.0-`, huella de `authorized_keys`, `sshd -T`); contenidos por stdin a `pct exec … tee` con rutas fijas y `argv` en lista
- [ ] T013 [US1] Despachar el protocolo nuevo en `infra/runner/nap_guest_runner.py` (función `is_iaas_access_request` + `handle_iaas_access_request`, junto a la de aplicaciones) sin tocar el resto del flujo
- [ ] T014 [US1] Agregar `iaas_access.py` (y su protocolo) a `SOURCES`/`ALLOWED` en `infra/applications/install.py` con ruta instalada `/opt/nap/runner/iaas_access.py`; actualizar `infra/applications/tests` del instalador si cuentan archivos
- [ ] T015 [US1] Correr `T003` y las pruebas de `infra/runner/tests` y `infra/applications/tests`; el `policy_digest` debe seguir igual

### Portal

- [ ] T016 [US1] Agregar el transporte del protocolo nuevo a `backend/app/services/guest_runner_client.py` y `build_runner_client.py` (mismo SSH, mismo `ForceCommand`, método `execute_iaas_access`) con pruebas en `backend/tests/` junto a las del cliente existente
- [ ] T017 [US1] Crear `backend/app/services/iaas_acceso_service.py`: `registrar_en_pedido` (valida con `ssh_keys`, devuelve el bloque para `asignacion_snapshot`), `crear_fila_al_materializar`, `estado_derivado`, `construir_solicitud(servicio, operacion)` y `aplicar(...)` que llama al runner y fija `aplicada_revision` solo si `configure`+`probe` confirman
- [ ] T018 [US1] En `backend/app/services/admision_service.py` (cerca de la línea donde `assignment.update(origen='proxmox_iaas', product='linux')`): exigir `clave_ssh_publica` para IaaS Linux (`clave_ssh_requerida`), rechazarla en cualquier otro caso, y guardar la clave normalizada y su huella en `assignment['acceso_ssh']`
- [ ] T019 [US1] En `backend/app/services/orquestacion_service.py`: en `_materialize` crear la fila `claves_acceso_servicio` (revision 1) para `proxmox_iaas`; en la fase `bootstrap` IaaS reemplazar la constante `local_health: True` por la llamada a `iaas_acceso_service.aplicar`; si falla, finalizar con un motivo seguro (`acceso_ssh_no_confirmado`) y NO dejar el servicio `utilizable`; conservar `metodo: 'consola'`
- [ ] T020 [US1] En `backend/app/services/service_access_service.py` agregar el bloque `acceso_ssh` del contrato (`estado`, `usuario`, `direccion`, `puerto`, `comando`, `huella`, `verificado_at`, `puede_conectar`, `motivo`) solo para IaaS Linux; `comando` nulo si no `puede_conectar`; no tocar `metodo` ni `consola_gate_service`
- [ ] T021 [US1] Registrar eventos `acceso_ssh_registrado` y `acceso_ssh_aplicado`/`acceso_ssh_rechazado` en el historial vía `backend/app/services/historial_service.py` (autor y huella, nunca la clave)
- [ ] T022 [P] [US1] Pruebas de portal en `backend/tests/test_acceso_ssh_pedido.py` (pedido sin clave, con clave privada, inválida, válida; solo IaaS Linux) y `backend/tests/test_acceso_ssh_despliegue.py` (despliegue exitoso fija `aplicada_revision`; fallo del runner no entrega; resultado incierto no declara utilizable)
- [ ] T023 [P] [US1] Prueba de `acceso_ssh` en `backend/tests/test_acceso_ssh_detalle.py`: cada estado, `comando` nulo cuando no corresponde, ausencia de la clave en la respuesta, `metodo` sin cambios para IaaS

### Frontend

- [ ] T024 [P] [US1] En `frontend/src/components/NuevoPedidoModal.jsx` agregar el campo «Clave pública SSH» (solo `iaas` con plantilla Linux): ayuda breve («pegá el contenido de tu archivo `.pub`; se genera con `ssh-keygen -t ed25519`»), obligatorio, envía `parametros_extra.clave_ssh_publica`, muestra los errores `clave_ssh_*` junto al campo
- [ ] T025 [P] [US1] En `frontend/src/components/AccesoServicio.jsx` agregar el bloque SSH: comando copiable, usuario, huella, texto «se entra con clave, sin contraseña» y «conectate desde la red institucional»; estados `pendiente`/`fallida` con `motivo`; mantener el botón de consola
- [ ] T026 [P] [US1] Pruebas en `frontend/tests/acceso-ssh.test.jsx` (campo obligatorio y errores, bloque SSH en cada estado, copiar comando, consola intacta)

**Checkpoint US1**: un Ubuntu nuevo con clave se despliega y se entra por SSH. Es el MVP.

## Phase 4: User Story 2 — El acceso sigue la vida del servicio (P2)

**Objetivo**: detener/iniciar y reiniciar un nodo conservan el acceso; la baja lo elimina sin dejar clave reutilizable.

**Prueba independiente**: quickstart escenarios 5, 9 y 10.

- [ ] T027 [US2] En `backend/app/services/orquestacion_service.py`, tras `iniciar`/`reiniciar` de un Linux IaaS ejecutar `probe` y mantener `disponibilidad_aplicacion` distinta de `utilizable` hasta que confirme (FR-011, FR-006); no reenviar `configure` si `aplicada_revision == revision`
- [ ] T028 [US2] En `backend/app/services/service_access_service.py`: `puede_conectar` falso con servicio detenido o sin `probe` reciente; `motivo` «Iniciá el servicio…»; consistente con FR-007
- [ ] T029 [US2] En la baja del servicio (`backend/app/services/orquestacion_service.py`, rama `eliminar`) dejar la fila sin uso: no se copia ni se reasigna, y el historial conserva solo la huella
- [ ] T030 [P] [US2] Pruebas en `backend/tests/test_acceso_ssh_ciclo.py`: iniciar tras detener, reinicio de nodo (probe antes de utilizable), baja, y reutilización de `vmid` rechazada por identidad del runner (con `IDENTITY_MISMATCH`)
- [ ] T031 [P] [US2] Prueba de runner en `infra/runner/tests/test_iaas_access.py`: `vmid` reutilizado por otro recurso no recibe la clave (agregar caso)

**Checkpoint US2**: el acceso sobrevive a ciclos de vida.

## Phase 5: User Story 3 — Cambiar de computadora o de clave, y servicios ya entregados (P3)

**Objetivo**: registrar o reemplazar la clave de un servicio entregado (incluido el #41 del laboratorio), con la anterior inválida.

**Prueba independiente**: quickstart escenarios 6, 7 y 8.

- [ ] T032 [US3] Agregar la operación durable `acceso_ssh` en `backend/app/services/orquestacion_service.py` según T002: arrendamiento y CAS existentes, idempotente por `(servicio_id, revision)`, un resultado incierto se reintenta con la misma revisión; rechazo `operacion_en_curso` si hay otra activa
- [ ] T033 [US3] En `backend/app/services/iaas_acceso_service.py` agregar `registrar_o_reemplazar(db, actor, servicio_id, clave)`: valida permiso con `requiere_acceso_servicio`, `servicio_no_linux`, `servicio_no_activo`, sube `revision`, crea la operación, registra evento `acceso_ssh_reemplazado`/`registrado`
- [ ] T034 [US3] Agregar `PUT /servicios/{servicio_id}/acceso-ssh` en `backend/app/routers/servicios.py` (CSRF e `Idempotency-Key` como los demás, respuesta 202 del contrato, el router no invoca `proxmoxer`) y el esquema de entrada/salida en `backend/app/schemas/`
- [ ] T035 [P] [US3] Pruebas en `backend/tests/test_acceso_ssh_reemplazo.py`: titular, admin, tercero (403), servicio sin clave previa (alta tardía), `operacion_en_curso`, idempotencia, reintento tras incertidumbre con la misma revisión
- [ ] T036 [P] [US3] Crear `frontend/src/components/CambiarClaveSshModal.jsx` y conectarlo desde el bloque SSH de `AccesoServicio.jsx` (botón «Cambiar clave» o «Agregar clave» si no hay); feedback `pendiente → aplicada`
- [ ] T037 [P] [US3] Pruebas del modal en `frontend/tests/acceso-ssh.test.jsx` (agregar, reemplazar, error, estado pendiente)

**Checkpoint US3**: la clave se puede registrar o cambiar sin dar de baja.

## Phase 6: Polish y validación real

- [ ] T038 Correr suites completas: `backend` (pytest con PostgreSQL de `docker-compose.test.yml`), `infra/runner/tests`, `infra/applications/tests` y `frontend` (vitest); confirmar 0 regresiones en Docker/OCI, bases y consola IaaS (SC-007)
- [ ] T039 Barrido de seguridad: buscar que ninguna clave completa ni contraseña llega a registros, errores, historial ni `argv` (SC-006); actualizar `.specify`/documentación si corresponde
- [ ] T040 Actualizar `docs/infraestructura-laboratorio/` con el runbook del ensayo (reinstalar el paquete en frt y pve91 con `scripts/actualizar-nodos-011.sh --aplicar`, plan sin cambios en archivos del digest)
- [ ] T041 Ensayo real en pve91 y frt siguiendo `quickstart.md` (escenarios 1–12), previa verificación R10 (`openssh-server` en la plantilla); registrar resultados y límites en el documento de validación del laboratorio. **Requiere maestros SSH abiertos por Ivan y su aprobación para tocar los nodos**
- [ ] T042 Registrar en memoria y docs el estado final y abrir el PR a `dev` **solo cuando Ivan lo pida**

## Dependencias y orden

- Setup (T001–T003) → Foundational (T004–T010) → US1 → US2 → US3 → Polish.
- Dentro de US1: runner (T011–T015) y portal (T016–T023) dependen de Foundational; el frontend (T024–T026) depende del contrato (ya fijado) y puede ir en paralelo con el runner.
- US2 depende de US1. US3 depende de US1 (reutiliza `aplicar` y el runner) y de T002/T032.
- T041 necesita US1–US3 completas.

## Oportunidades de paralelismo

- Foundational: T004/T005, T006, T008, T009/T010 son archivos distintos.
- US1: T011 (pruebas del runner) con T022/T023 (pruebas de portal); T024, T025, T026 son tres archivos de frontend.
- US3: T035, T036, T037.

## Estrategia

1. **MVP = US1**: T001–T026. Se puede validar antes de seguir (quickstart 1–4).
2. Incrementar con US2 y US3.
3. El ensayo real (T041) se hace al final y se detiene ante cualquier incertidumbre del nodo, sin reintentar a ciegas (regla del proyecto: no ejecutar una operación incierta de nuevo).

**Total**: 42 tareas · Setup 3 · Foundational 7 · US1 16 · US2 5 · US3 6 · Polish 5.
