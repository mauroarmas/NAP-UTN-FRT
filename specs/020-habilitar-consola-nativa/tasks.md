# Tasks: Habilitar la consola nativa de Linux IaaS

**Input**: `specs/020-habilitar-consola-nativa/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: incluidas para el código del portal (compuerta, destino por nodo, mensajes). El ensayo real en el clúster es una tarea explícita (T017) y su evidencia se separa de las pruebas con dobles.

**Reglas duras**: no ampliar la excepción de la constitución (rol de sólo consola); ningún dato del laboratorio en archivos versionados (FR-012); NO modificar archivos que entren en el `policy_digest` del motor Docker; no hay migración. Las tareas marcadas **[LAB]** modifican el clúster real o requieren a Ivan (credenciales, cuenta administradora, navegador).

**Puerta de decisión (FR-008)**: si T017 no demuestra los tres puntos de revocación, se salta a T018 y la consola queda cerrada: no se ejecutan T019–T022.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin dependencia pendiente)
- **[Story]**: US1 = abrir la consola desde el navegador (P1) · US2 = retirar el acceso de verdad (P1) · US3 = evidencia y habilitación (P2) · US4 = runbook (P3)

## Phase 1: Setup

- [x] T001 [P] Crear la prueba de higiene `backend/tests/test_sin_datos_lab_020.py` que recorra los archivos versionados (`git ls-files`) y falle si encuentra direcciones `192.168.100.`, `172.16.36.`, tokens, el UUID del clúster del lab (por su prefijo), o identidades `@pve`/`@pam` distintas de los marcadores y de `root@pam` en el importador (SC-006)
- [x] T002 [P] Verificar que la configuración privada del lab (`~/.local/share/nap009/`) sigue fuera del repositorio y que `.gitignore` cubre lo que el ensayo genere (salidas del ensayo en el scratchpad, no en el árbol)

## Phase 2: Foundational (bloquea las historias)

- [x] T003 [P] Crear `docs/infraestructura-laboratorio/scripts/consola/crear-rol-consola.sh`: recibe nodo por argumento, crea el rol `NapConsola` con sólo `VM.Console` (más lo mínimo que demuestre el ensayo) por `pveum role add`, idempotente, con modo `--plan` que sólo muestra qué haría (research R1)
- [x] T004 [P] Crear `docs/infraestructura-laboratorio/scripts/consola/crear-identidad.sh`: crea `usuario@dominio` en el dominio propio, contraseña por entrada estándar (nunca en argv ni en el repo), ACL `NapConsola` sobre `/pool/catedra-<N>` y nada en `/`, `/vms` ni `/nodes`; `--plan` por defecto, `--aplicar` explícito (research R2, FR-004, FR-005)
- [x] T005 [P] Crear `docs/infraestructura-laboratorio/scripts/consola/retirar-acceso.sh`: quita la ACL del pool indicado, elimina la identidad cuando no le quedan pools y termina en el nodo que aloja el contenedor los procesos de consola afectados; `--plan` por defecto; imprime qué retiró (research R3, FR-007)

## Phase 3: User Story 1 - Abrir la consola de mi Linux desde el navegador (P1)

**Goal**: una persona con identidad asignada abre la consola de su Linux IaaS, en cualquier nodo, con un clic.

**Independent Test**: con la compuerta habilitada, una persona de la cátedra 3 abre la consola de un Ubuntu de frt y de otro de pve91; la cátedra ajena y quien no tiene identidad son rechazados antes de recibir destino.

### Tests (primero, deben fallar)

- [x] T006 [P] [US1] Pruebas del destino por nodo en `backend/tests/test_consola_destino_020.py`: usa el nodo del contenedor; failover al otro nodo si el primero no responde al sondeo (doble de red); 503 `consola_nodo_no_disponible` si ninguno responde; nodo ausente en `nodos` no se usa; `node=` de la URL es siempre el del contenedor; la respuesta no contiene tickets ni otros hosts (FR-016, SC-007)
- [x] T007 [P] [US1] Pruebas de la compuerta en `backend/tests/test_consola_gate_020.py`: ADMIN también pasa por `exigir_gate` (sin perfil → 409 `consola_no_habilitada`); persona sin identidad, con identidad de otra cátedra o con revisión vencida → 409; perfil sin `nodos` → cerrada; servicio detenido/sin vigencia/sin identidad de infraestructura → rechazo con su código (FR-001–FR-003)

### Implementación

- [x] T008 [US1] Crear `backend/app/services/consola_destino_service.py`: `resolver_destino(profile, nodo_contenedor)` con orden propio→resto, sondeo TCP asíncrono de ≤ 2 s por nodo, devuelve host/puerto o lanza 503 `consola_nodo_no_disponible`; no registra tickets ni secretos (research R4)
- [x] T009 [US1] Ampliar `backend/app/services/consola_gate_service.py`: `exigir_gate` valida la clave `nodos` (host y puerto bien formados, sin duplicados) y cierra en falla si falta; sin cambiar los campos que ya consume (contracts/console-profile.md)
- [x] T010 [US1] Modificar `consola_del_servicio` en `backend/app/routers/servicios.py`: llamar a `exigir_gate` para todos los roles (también ADMIN), mantener `autorizar` para no administradores, construir la URL con `consola_destino_service` en lugar de `settings.proxmox_host` (research R4, R5; contracts/console-endpoint.md)
- [x] T011 [P] [US1] Mensajes por motivo en `frontend/src/components/AccesoServicio.jsx` (`consola_no_habilitada`, `servicio_no_disponible`, `identidad_no_confirmada`, `consola_nodo_no_disponible`) en lenguaje no técnico, y prueba en `frontend/tests/acceso-consola-020.test.jsx` (FR-014)
- [x] T012 [P] [US1] Agregar `nodos` con marcadores a `infra/production/settings.example.json` dentro de `console_access_profile` y mantener el contrato `specs/020-habilitar-consola-nativa/contracts/console-profile.md` alineado
- [x] T013 [US1] Ejecutar `pytest backend/tests/test_consola_destino_020.py backend/tests/test_consola_gate_020.py backend/tests/test_revocacion_consola_009.py backend/tests/test_convergencia_seguridad_009.py` y la prueba de vitest de T011; todo en verde antes de pasar al laboratorio
- [x] T014 [LAB] [US1] Preparar en el clúster: crear el rol (T003) en un nodo (los roles son de clúster), la identidad individual de prueba (T004) con ACL sobre `/pool/catedra-3`, y comprobar con la propia identidad que no ve nodos, almacenamiento ni acciones de energía (FR-005, SC-004)
- [ ] T015 [LAB] [US1] Tener un Linux IaaS `RUNNING` con vigencia en **frt** y otro en **pve91** (pedido por la interfaz, aprobación de administración por Ivan)

**Checkpoint**: backend y frontend verdes; identidad de prueba creada; un Linux por nodo.

## Phase 4: User Story 2 - Retirar el acceso de verdad (P1)

**Goal**: al retirar el acceso se corta la sesión abierta, se rechaza el ticket guardado y se conserva el otro pool.

**Independent Test**: ensayo con cuenta de prueba que resulta en los tres resultados observados por separado.

- [x] T016 [US2] Crear `docs/infraestructura-laboratorio/scripts/consola/ensayo-revocacion.py` (entorno de ensayo con `websockets`): con la identidad de prueba obtiene ticket de sesión, solicita la consola del contenedor y abre la conexión; ejecuta el retiro (T005); comprueba (1) la conexión deja de transmitir dentro del plazo medido, (2) el ticket y la solicitud guardados son rechazados, (3) con el otro pool vigente una sesión nueva abre; emite un informe JSON sin tickets ni cookies
- [x] T017 [LAB] [US2] Ejecutar el ensayo real en frt y en pve91 y registrar el resultado en `docs/infraestructura-laboratorio/validacion-consola-2026-11-04.md`, separando comprobado, doble y pendiente (FR-007, SC-003)
- [x] T018 [US2] **Puerta de decisión**: si algún punto de T017 falla, documentar en ese informe el diagnóstico y que la consola queda cerrada (FR-008), actualizar `spec.md` (Status) y terminar sin T019–T022; si pasa, continuar

## Phase 5: User Story 3 - Dejar constancia y habilitar por instalación (P2)

**Goal**: la instalación queda habilitada con evidencia real, trámite completado y perfil cargado; cualquier cambio de revisión la cierra.

**Independent Test**: tras cargar el perfil la compuerta abre; alterar la revisión de la cátedra la vuelve a cerrar.

- [ ] T019 [LAB] [US3] Importar el inventario de la identidad de prueba con `python -m scripts.importar_identidades_consola --archivo <json> --actor <operador> --referencia <acta>` dentro del contenedor `api` (el JSON con datos del lab queda en el scratchpad)
- [ ] T020 [LAB] [US3] Registrar la evidencia `revocacion_consola` (`entorno: real`, `cluster_uuid` del clúster del lab, `pve_version` 9.2.2) desde el informe de T017 y confirmar el trámite en `/admin/cambios-consola` con administración (Ivan)
- [ ] T021 [LAB] [US3] Cargar `console_access_profile` (evidencia, hash, `nodos`, identidad con revisiones vigentes) en la configuración privada del lab y recrear `api` y `worker`
- [ ] T022 [LAB] [US3] Verificación funcional (quickstart paso 6): consola abierta desde el navegador para un Linux de frt y otro de pve91; la misma cuenta rechazada en la cátedra 25; usuario sin identidad con mensaje claro; con un nodo apagado la consola del otro sigue abriendo por el nodo vivo (SC-001, SC-002, SC-007); y cambiar la revisión de la cátedra cierra la compuerta (FR-011)

## Phase 6: User Story 4 - Runbook para la universidad (P3)

**Goal**: infraestructura de la universidad habilita la consola siguiendo un documento, sin valores del laboratorio.

**Independent Test**: un revisor sin acceso al lab confirma que cada paso nombra el dato propio necesario y que T001 pasa.

- [ ] T023 [US4] Escribir `docs/runbook-consola-nativa.md`: inventario previo, dominio e identidades, rol y ACL por pool, alcance de red y certificados por nodo (research R7), ensayo de revocación con criterios de aprobación y salida si falla, registro de evidencia, carga de `console_access_profile` con `nodos`, verificación y retiro; sólo marcadores (`<nodo>`, `<usuario>@<dominio>`)
- [ ] T024 [P] [US4] Escribir `docs/infraestructura-laboratorio/scripts/consola/README.md` (uso de los scripts T003–T005 y T016, requisitos, ejemplos con marcadores) y enlazar el runbook desde `docs/conexion-infraestructura.md` y `docs/manual-administrador.md`
- [ ] T025 [US4] Ejecutar `pytest backend/tests/test_sin_datos_lab_020.py` (T001) y corregir cualquier dato del laboratorio hallado en archivos versionados

## Phase 7: Polish & cross-cutting

- [ ] T026 Ejecutar las suites completas: `pytest backend/tests` (PostgreSQL de pruebas: `docker compose -f docker-compose.test.yml up -d --wait`) y `vitest` en una copia del frontend en el scratchpad (`npm ci`); sin regresiones
- [ ] T027 Actualizar `specs/020-habilitar-consola-nativa/tasks.md` con lo realizado, `spec.md` (Status) y `checklists/requirements.md`; dejar retirados los servicios e identidades temporales del lab
- [ ] T028 Actualizar la memoria del proyecto (estado de la consola, cómo operarla, decisión tomada en T018) y preparar el PR a `dev` (sin co-autor en los commits)

## Dependencies & Execution Order

- Fase 1 y Fase 2 sin dependencias entre sí; Fase 2 bloquea T014 y T016.
- US1 código (T006–T013) es independiente del lab y se hace primero; T014–T015 requieren Fase 2.
- US2 depende de T014–T015; T017 decide si se sigue (T018).
- US3 depende de T017 aprobada. US4 puede escribirse con T017 conocida (para incluir los criterios reales).

```text
T001,T002 ──┐
T003,T004,T005 (P)──► T014 ──► T016 ──► T017 ──► T018 ──► T019 ► T020 ► T021 ► T022
T006,T007 (P) ► T008,T009 ► T010 ► T011,T012 ► T013                       └► T023 ► T024 ► T025 ► T026 ► T027 ► T028
T015 (pedido por la UI) ─────────────► T016
```

## Parallel Example

- T001 y T002; T003, T004 y T005; T006 y T007; T011 y T012 pueden avanzar en paralelo.

## Implementation Strategy

1. **MVP**: Fases 1–2 + US1 código (T006–T013) + US2 (T014–T018). Si T017 pasa, US3 entrega la habilitación; si no, el diagnóstico es el entregable.
2. US4 y la polish cierran la feature para la universidad.
3. Commits chicos por tarea, sin co-autor; el PR a `dev` al final.
