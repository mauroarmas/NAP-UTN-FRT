# Matriz de trazabilidad de la spec 009

Revisión del 25 de octubre de 2026. Referencia de ejecución: [convergencia.md](convergencia.md). Esta matriz localiza código, pruebas y tareas existentes; no convierte cobertura de código o una simulación en aceptación institucional. La preparación del clúster/red y la revisión por un lector ajeno siguen pendientes.

## Requisitos funcionales

| Requisito | Tareas de origen | Ubicación principal | Prueba o evidencia localizada |
|---|---|---|---|
| FR-001 | T020, T021, T022, T023, T024, T025, T026, T027, T029, T112 | [backend/app/services/acceso_service.py](../../../backend/app/services/acceso_service.py) | [backend/tests/test_aislamiento_multicatedra.py](../../../backend/tests/test_aislamiento_multicatedra.py) |
| FR-002 | T020, T021, T022, T023, T024, T025, T026, T029 | [backend/app/services/acceso_service.py](../../../backend/app/services/acceso_service.py) | [backend/tests/test_aislamiento_multicatedra.py](../../../backend/tests/test_aislamiento_multicatedra.py) |
| FR-003 | T021, T022, T023, T025, T026, T028, T029 | [backend/app/services/acceso_service.py](../../../backend/app/services/acceso_service.py) | [backend/tests/test_aislamiento_multicatedra.py](../../../backend/tests/test_aislamiento_multicatedra.py) |
| FR-004 | T030, T032, T033, T034, T036, T037, T044, T046, T121 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-005 | T030, T032, T033, T034, T037, T043, T044, T046 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-006 | T030, T031, T033, T034, T036, T037, T046 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-007 | T031, T033, T035, T037, T046 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-008 | T039, T040, T041, T042, T046, T122, T127, T130 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-009 | T031, T033, T038, T046 | [backend/app/services/auth_service.py](../../../backend/app/services/auth_service.py) | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) |
| FR-010 | T019, T021, T028, T047, T048, T053, T055, T058 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-011 | T011, T047, T052, T057, T058, T067, T126 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-012 | T009, T016, T048, T053, T055, T056, T058, T061 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-013 | T047, T051, T052, T055, T058 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-014 | T047, T049, T054, T058, T065, T085, T093, T094 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-015 | T048, T049, T054, T055, T058, T081 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-016 | T050, T057, T058 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-017 | T015, T053, T056, T058, T068, T125 | [backend/app/services/admision_service.py](../../../backend/app/services/admision_service.py) | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) |
| FR-018 | T056, T072, T076, T077, T082, T083 | [backend/app/services/renovacion_service.py](../../../backend/app/services/renovacion_service.py) | [backend/tests/postgres/test_renovacion_periodos_009.py](../../../backend/tests/postgres/test_renovacion_periodos_009.py) |
| FR-019 | T059, T060, T062, T064, T066, T068, T069, T070, T077, T094, T095, T097, T109 | [backend/app/services/orquestacion_service.py](../../../backend/app/services/orquestacion_service.py) | [backend/tests/test_operaciones_recuperacion.py](../../../backend/tests/test_operaciones_recuperacion.py) |
| FR-020 | T057, T059, T060, T061, T062, T063, T064, T065, T066, T067, T068, T069, T070, T085, T093, T094 | [backend/app/services/orquestacion_service.py](../../../backend/app/services/orquestacion_service.py) | [backend/tests/test_operaciones_recuperacion.py](../../../backend/tests/test_operaciones_recuperacion.py) |
| FR-021 | T011, T060, T061, T062, T063, T065, T066, T067, T070, T085, T093, T095 | [backend/app/services/orquestacion_service.py](../../../backend/app/services/orquestacion_service.py) | [backend/tests/test_operaciones_recuperacion.py](../../../backend/tests/test_operaciones_recuperacion.py) |
| FR-022 | T009, T011, T012, T016, T019, T028, T057, T059, T061, T062, T063, T067, T068, T070, T097 | [backend/app/services/orquestacion_service.py](../../../backend/app/services/orquestacion_service.py) | [backend/tests/test_operaciones_recuperacion.py](../../../backend/tests/test_operaciones_recuperacion.py) |
| FR-023 | T071, T073, T080, T083 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-024 | T071, T073, T075, T078, T080, T083, T088 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-025 | T071, T073, T075, T080, T083 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-026 | T049, T054, T073, T081, T083 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-027 | T008, T014, T071, T073, T078, T080, T081, T083 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-028 | T012, T076, T078, T082, T083, T084, T087, T088, T096, T098, T102, T124 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-029 | T106, T114, T119 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-030 | T015, T071, T074, T075, T079, T081, T082, T083, T125 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-031 | T008, T015, T071, T074, T075, T080, T083, T125 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-032 | T072, T076, T077, T082, T083, T109 | [backend/app/services/solicitud_service.py](../../../backend/app/services/solicitud_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-033 | T066, T078, T084, T088 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-034 | T066, T070, T078, T084, T088, T090, T101, T102 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-035 | T010, T018, T086, T090, T091, T092, T095, T096, T097, T099, T102 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-036 | T017, T024, T040, T041, T085, T086, T095, T096, T097, T099, T102, T126 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-037 | T010, T018, T084, T087, T089, T098, T100 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-038 | T089, T091, T092, T095, T100, T101, T102 | [backend/app/services/catalogo_service.py](../../../backend/app/services/catalogo_service.py) | [backend/tests/test_entrega_acceso_009.py](../../../backend/tests/test_entrega_acceso_009.py) |
| FR-039 | T104, T107, T110, T112, T113, T114, T119 | [backend/app/services/alerta_service.py](../../../backend/app/services/alerta_service.py) | [backend/tests/test_alertas_009.py](../../../backend/tests/test_alertas_009.py) |
| FR-040 | T040, T041, T104, T109, T110, T112, T114, T119 | [backend/app/services/alerta_service.py](../../../backend/app/services/alerta_service.py) | [backend/tests/test_alertas_009.py](../../../backend/tests/test_alertas_009.py) |
| FR-041 | T015, T071, T074, T075, T077, T079, T082, T083 | [backend/app/services/calendario_service.py](../../../backend/app/services/calendario_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-042 | T103, T107, T108, T109, T113, T119 | [backend/app/services/metricas_service.py](../../../backend/app/services/metricas_service.py) | [backend/tests/test_metricas_intervalos_009.py](../../../backend/tests/test_metricas_intervalos_009.py) |
| FR-043 | T103, T105, T107, T108, T111, T112, T114, T116, T119 | [backend/app/services/metricas_service.py](../../../backend/app/services/metricas_service.py) | [backend/tests/test_metricas_intervalos_009.py](../../../backend/tests/test_metricas_intervalos_009.py) |
| FR-044 | T069, T106, T114, T119 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-045 | T106, T115, T119 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-046 | T030, T032, T034, T037, T043, T044 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-047 | T069, T099, T106, T114, T115, T119 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-048 | T041, T063, T064, T068, T070, T094, T108, T112, T113, T116, T117, T118, T119, T127 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-049 | T103, T107, T108, T112, T113, T116, T117, T119 | [frontend/src/hooks/useRemoteData.js](../../../frontend/src/hooks/useRemoteData.js) | [frontend/tests/estados-accesibilidad.test.jsx](../../../frontend/tests/estados-accesibilidad.test.jsx) |
| FR-050 | T019, T105, T107, T111, T113, T117, T119, T124 | [backend/app/services/resumen_metricas_service.py](../../../backend/app/services/resumen_metricas_service.py) | [backend/tests/test_resumen_historico_009.py](../../../backend/tests/test_resumen_historico_009.py) |
| FR-051 | T042, T043, T122, T123, T127, T133, T137 | [backend/app/services/preflight_service.py](../../../backend/app/services/preflight_service.py) | [backend/tests/postgres/test_migracion_cierre_009.py](../../../backend/tests/postgres/test_migracion_cierre_009.py) |
| FR-052 | T010, T017, T018, T022, T024, T026, T027, T051, T085, T090, T093, T094, T096, T101, T122, T123, T127, T133 | [backend/app/services/preflight_service.py](../../../backend/app/services/preflight_service.py) | [backend/tests/postgres/test_migracion_cierre_009.py](../../../backend/tests/postgres/test_migracion_cierre_009.py) |
| FR-053 | T008, T010, T011, T012, T013, T014, T033, T040, T107, T120, T123, T124, T125, T126 | [backend/app/services/preflight_service.py](../../../backend/app/services/preflight_service.py) | [backend/tests/postgres/test_migracion_cierre_009.py](../../../backend/tests/postgres/test_migracion_cierre_009.py) |
| FR-054 | T001, T006, T013, T042, T120, T122, T123, T124, T125, T126, T127, T134 | [backend/app/services/preflight_service.py](../../../backend/app/services/preflight_service.py) | [backend/tests/postgres/test_migracion_cierre_009.py](../../../backend/tests/postgres/test_migracion_cierre_009.py) |
| FR-055 | T121, T129, T130, T131, T137 | [backend/app/services/restauracion_service.py](../../../backend/app/services/restauracion_service.py) | [backend/tests/postgres/test_restauracion_009.py](../../../backend/tests/postgres/test_restauracion_009.py) |
| FR-056 | T002, T128 | [backend/requirements.lock](../../../backend/requirements.lock) | [docs/evidencia/009/dependencias.md](dependencias.md) |
| FR-057 | T003, T004, T005, T007, T009, T010, T045, T048, T060, T128, T133, T134, T135 | [.github/workflows/009-validation.yml](../../../.github/workflows/009-validation.yml) | [docs/evidencia/009/convergencia.md](convergencia.md) |
| FR-058 | T001, T007, T029, T046, T058, T070, T101, T102, T119, T131, T133, T134, T135, T136, T138 | [.github/workflows/009-validation.yml](../../../.github/workflows/009-validation.yml) | [docs/evidencia/009/convergencia.md](convergencia.md) |
| FR-059 | T132, T133, T135, T136, T137, T138 | [docs/manual-administrador.md](../../manual-administrador.md) | [docs/conexion-infraestructura.md](../../conexion-infraestructura.md) |
| FR-060 | T129, T132, T133, T136, T137, T138 | [docs/manual-administrador.md](../../manual-administrador.md) | [docs/conexion-infraestructura.md](../../conexion-infraestructura.md) |
| FR-061 | T011, T084, T087, T088, T089, T098, T100, T101 | [backend/app/services/preparacion_service.py](../../../backend/app/services/preparacion_service.py) | [backend/tests/test_reserva_red_009.py](../../../backend/tests/test_reserva_red_009.py) |
| FR-062 | T085, T089, T090, T091, T092, T093, T095, T098, T100, T101, T102 | [backend/app/services/preparacion_service.py](../../../backend/app/services/preparacion_service.py) | [backend/tests/test_reserva_red_009.py](../../../backend/tests/test_reserva_red_009.py) |
| FR-063 | T085, T086, T089, T090, T091, T092, T093, T095, T096, T101, T102 | [backend/app/services/preparacion_service.py](../../../backend/app/services/preparacion_service.py) | [backend/tests/test_reserva_red_009.py](../../../backend/tests/test_reserva_red_009.py) |
| FR-064 | T011, T071, T074, T079, T083 | [backend/app/services/vigencia_service.py](../../../backend/app/services/vigencia_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-065 | T012, T071, T075, T076, T083, T084, T087, T098 | [backend/app/services/vigencia_service.py](../../../backend/app/services/vigencia_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-066 | T050, T055, T058, T071, T075, T083 | [backend/app/services/vigencia_service.py](../../../backend/app/services/vigencia_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-067 | T087, T098, T100, T102 | [backend/app/services/vigencia_service.py](../../../backend/app/services/vigencia_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-068 | T015, T050, T071, T075, T082, T083 | [backend/app/services/vigencia_service.py](../../../backend/app/services/vigencia_service.py) | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) |
| FR-069 | T017, T031, T032, T033, T036, T037, T044, T046 | [backend/app/services/segundo_factor_service.py](../../../backend/app/services/segundo_factor_service.py) | [backend/tests/postgres/test_auth_concurrencia_009.py](../../../backend/tests/postgres/test_auth_concurrencia_009.py) |
| FR-070 | T031, T032, T033, T036, T037, T039, T044, T046, T121, T130 | [backend/app/services/segundo_factor_service.py](../../../backend/app/services/segundo_factor_service.py) | [backend/tests/postgres/test_auth_concurrencia_009.py](../../../backend/tests/postgres/test_auth_concurrencia_009.py) |
| FR-071 | T030, T031, T032, T036, T037, T044, T046 | [backend/app/services/segundo_factor_service.py](../../../backend/app/services/segundo_factor_service.py) | [backend/tests/postgres/test_auth_concurrencia_009.py](../../../backend/tests/postgres/test_auth_concurrencia_009.py) |
| FR-072 | T072, T076, T077, T082, T083 | [backend/app/services/renovacion_service.py](../../../backend/app/services/renovacion_service.py) | [backend/tests/postgres/test_renovacion_periodos_009.py](../../../backend/tests/postgres/test_renovacion_periodos_009.py) |
| FR-073 | T086, T092, T099, T100, T102 | [infra/services/bookstack/bootstrap.py](../../../infra/services/bookstack/bootstrap.py) | [infra/services/tests/test_bookstack.py](../../../infra/services/tests/test_bookstack.py) |

Los requisitos completos y sus escenarios se conservan en la [spec](../../../specs/009-remediar-hallazgos-cierre/spec.md). La columna principal es una entrada al dominio; la cobertura completa y sus dependencias están en las tareas enlazadas por ID, no se presume un test único por requisito.

## Criterios de éxito

| Criterio | Prueba o referencia | Estado de aceptación |
|---|---|---|
| SC-001 | [backend/tests/test_convergencia_seguridad_009.py](../../../backend/tests/test_convergencia_seguridad_009.py) | Aislamiento/gate con dobles; revocación nativa institucional pendiente T102/T133. |
| SC-002 | [backend/tests/test_auth_contrato_009.py](../../../backend/tests/test_auth_contrato_009.py) | Regresiones aisladas; no exige inscripción 2FA a cuentas sin factor. |
| SC-003 | [backend/tests/postgres/test_admision_capacidad_009.py](../../../backend/tests/postgres/test_admision_capacidad_009.py) | Concurrencia PostgreSQL aislada; inventario institucional por comprobar. |
| SC-004 | [backend/tests/test_operaciones_recuperacion.py](../../../backend/tests/test_operaciones_recuperacion.py) | Fallo/reinicio con doble; integración externa pendiente T133. |
| SC-005 | [backend/tests/test_reserva_red_009.py](../../../backend/tests/test_reserva_red_009.py) | Dos instancias por aplicación con dobles; aceptación funcional/red real pendiente T102. |
| SC-006 | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) | Períodos/fechas con reloj controlado en entorno aislado. |
| SC-007 | [docs/evidencia/009/us7.md](us7.md) | Pendiente responsable de una cátedra, formulario <=3min y feedback T119. |
| SC-008 | [docs/evidencia/009/rendimiento-navegador.json](rendimiento-navegador.json) | Referencia histórica del laboratorio del 21/10; no repetida ni acreditada para la instalación universitaria en esta revisión. |
| SC-009 | [backend/tests/test_alertas_009.py](../../../backend/tests/test_alertas_009.py) | Incidentes/deduplicación con muestras y SMTP simulados. |
| SC-010 | [frontend/tests/e2e/teclado.spec.js](../../../frontend/tests/e2e/teclado.spec.js) | Recorridos automatizados; feedback de usuario pendiente T119. |
| SC-011 | [docs/evidencia/009/restauracion-control.md](restauracion-control.md) | Control de restauración y esquema probados; restore completo portal+keyring y aplicaciones pendiente T131, sin evidencia de pg_dump/pg_restore completa disponible. |
| SC-012 | [docs/evidencia/009/cierre.md](cierre.md) | Entrega integral no aceptada: pendientes T102/T119/T131/T133 y lectura externa de manuales. |
| SC-013 | [backend/tests/test_reserva_red_009.py](../../../backend/tests/test_reserva_red_009.py) | Pool/despliegue cotidiano simulado; despliegues desde catálogo y red real pendiente T102. |
| SC-014 | [backend/tests/test_calendario_vigencias_009.py](../../../backend/tests/test_calendario_vigencias_009.py) | Límites/snapshots/reservas futuras con reloj controlado. |
| SC-015 | [backend/tests/postgres/test_auth_concurrencia_009.py](../../../backend/tests/postgres/test_auth_concurrencia_009.py) | 2FA/códigos/administración con DB aislada. |
| SC-016 | [backend/tests/postgres/test_renovacion_periodos_009.py](../../../backend/tests/postgres/test_renovacion_periodos_009.py) | Receso y admisión con dobles; dato persistente real por validar T102/T133. |
| SC-017 | [infra/services/tests/test_bookstack.py](../../../infra/services/tests/test_bookstack.py) | Receta simulada; dos lectores por instancia, revocación y archivos reales pendiente T102. |

## Hallazgos A01–A16 y convergencia

| Hallazgo | Cobertura |
|---|---|
| A01: pedidos ajenos | US1; FR-001–FR-003; SC-001. |
| A02: aprobar sin reserva | US3; FR-010–FR-012; SC-003. |
| A03: segundo factor/cambio inicial | US2; FR-004–FR-007, FR-069–FR-071; SC-002, SC-015. |
| A04: cuentas y configuración de desarrollo | US2/US8; FR-008, FR-051–FR-052; SC-002, SC-012. |
| A05: reservas en despliegue y caducidad | US3/US4; FR-011, FR-016, FR-020–FR-021, FR-066; SC-003–SC-004, SC-014. |
| A06: capacidad del destino real | US3; FR-013; SC-003. |
| A07: inicio evita controles | US3/US5; FR-012, FR-017–FR-018, FR-072; SC-003, SC-016. |
| A08: overrides cambian invariantes | US3; FR-014, FR-027; SC-003–SC-004. |
| A09: servicio/accesos no comprobados | US6; FR-035–FR-038, FR-061–FR-063, FR-065, FR-067, FR-073; SC-005, SC-013, SC-017. |
| A10: vigencia incompleta | US5; FR-025, FR-030–FR-032, FR-041, FR-064–FR-066, FR-068, FR-072; SC-006, SC-014, SC-016. |
| A11: lentitud bloquea el portal | US4/US7; FR-048; SC-008. |
| A12: pausas sin confirmar | US4; FR-019–FR-022; SC-004. |
| A13: contadores/cobertura | US7; FR-042, FR-049; SC-009, SC-011. |
| A14: métricas ajenas/último admin | US1/US2; FR-001–FR-002, FR-009; SC-001–SC-002. |
| A15: oferta incompatible/estado transitorio | US4/US6; FR-033–FR-034; SC-004–SC-005. |
| A16: dependencia vulnerable | US8; FR-056–FR-058; SC-012. |

| Convergencia | Corrección / tarea |
|---|---|
| F1 | Gate explícito de instalación/identidad/scopes: T139. |
| F2 | Fachada de estado retirada también en servicios: T140. |
| F3 | Pausa/reactivación confirmada y cierre ERROR reconciliado: T141. |
| F4 | Pool de red/TLS/DHCP preparado en lote y reserva duradera: T142. |
| F5 | Avisos de vencimiento en outbox, deduplicación y concurrencia: T143. |
| F6 | Retiro del publicador local; comprobación de archivos sin mutaciones: T144. |
| F7 | Manuales ajustados a CLI/API/UI; revisión por lector externo pendiente: T145. |
| F8 | Trazabilidad, enlaces y estados comprobables: T146. |

La evidencia local anterior está en [preparación](preparacion-servicios.md), [producción aislada](produccion.md), [dependencias](dependencias.md) y [regresión histórica](regresion-cierre.md). No existen los antiguos destinos `dependencias-seguridad.md`, `migracion-respaldo.md` ni `rendimiento-api.json`: no se citan como comprobaciones realizadas.
