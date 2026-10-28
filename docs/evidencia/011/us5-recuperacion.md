# US5: Reconciliación de incertidumbre, ciclo de vida y recuperación — Evidencia

## Componentes implementados y verificados (28/10/2026)

1. **Reconciliación y recuperación ante incertidumbre**:
   - Detección rigurosa de respuestas perdidas en creación e inicio sin duplicar contenedores en Proxmox.
   - Si la llamada de creación en Proxmox se pierde o reinicia el worker, el ejecutor consulta la existencia del contenedor por marcador SHA256 (`recuperar_upid` y `observar`) antes de volver a emitir órdenes o marcar fallo.
   - Ante reinicio inesperado del nodo o runner inalcanzable, la operación pasa a estado `incierta` con código `resultado_no_confirmado` o `reconciliacion_pendiente`, reteniendo los recursos en el ledger sin darlos por perdidos ni duplicarlos.
   - Ingesta de acceso HTTP con salud fallida (502 / timeout) bloquea la entrega del servicio y previene la transición a `utilizable` hasta contar con comprobación exitosa (200).

2. **Endpoints de reintento (`POST /operaciones/{id}/reintentar` y `POST /pedidos/{id}/reintentar`)**:
   - Reintento exclusivo para administradores (`401` no autenticado, `403` docente/cátedra).
   - Verificación de que la operación previa esté en estado terminal fallido confirmado (rechaza operaciones abiertas o inciertas con `409 operacion_en_curso`).
   - Admite operación hija de tipo `reparar` que reanuda las fases faltantes sobre la identidad existente sin duplicar VMID ni compromisos de capacidad.
   - Validación de contrato: rechaza pedidos sin error (`409 estado_incompatible`) u operaciones sin pedido (`409 requiere_nueva_decision`).

3. **Ciclo de vida completo sin pull ni regeneración de secretos**:
   - Operaciones `detener`, `iniciar`, `reiniciar`:
     - Actúan directamente sobre el contenedor LXC existente (`stop_lxc`, `start_lxc`, `reboot_lxc`).
     - No invocan al runner para pull de imagen ni instalación (`runner.starts` se mantiene inalterado).
     - Conservan los secretos de aplicación (`SecretoDespliegue`) con sus mismos IDs y valores cifrados originales.
     - Preservan los volúmenes de datos montados y la asignación de red.
   - Rechazo de operaciones ante identidad ajena o divergente: si el contenedor en Proxmox presenta descripción alterada o no coincide con la marca NAP, el ejecutor rechaza manipular el recurso y marca la operación como `incierta`.
   - Cobertura autorizada: servicios con vigencia vencida rechazan órdenes de inicio o reinicio con `409 sin_cobertura_actual`. Instancias existentes con oferta retirada del catálogo pueden seguir operando (ej. detenerse) normalmente.

4. **Retiro seguro de aplicaciones y limpieza pendiente**:
   - Ante fallo de eliminación en backend (`vzdestroy` falla por storage bloqueado u otro error), el recurso no se marca como retirado: `identidad.estado = 'incierta'`, `ledger.estado = 'incierto'`, y no se liberan la IP ni el ledger.
   - La liberación de capacidad y red ocurre estricta y únicamente cuando se confirma la ausencia física del recurso (`observation.estado == 'ausente'`).

5. **Pruebas concurrentes y de retención en PostgreSQL**:
   - Doble invocación concurrente de reintento sobre operación fallida serializada mediante bloqueo de capacidad: exactamente una operación `reparar` es admitida (`202`) y la competidora es rechazada con `409`.
   - Recreación / replay de asegurar secretos sobre el mismo pedido aprobado conserva idénticos IDs y textos cifrados.
   - Renovación de pedido conserva las referencias a los secretos del pedido original (ALTA); un nuevo pedido de alta genera secretos independientes y disjuntos.

6. **Interfaz de usuario y frontend**:
   - `ProgresoDespliegue.jsx`: ante estado incierto muestra mensaje amigable `Comprobando el estado de la instancia` con indicación `NAP está verificando el resultado. No hace falta volver a pedir el despliegue.`, previniendo reintentos masivos del usuario.
   - `Pedidos.jsx`: botón «Reintentar despliegue» visible únicamente cuando el pedido está en `error` con fallo confirmado.
   - `Servicios.jsx`: confirmación destructiva obligatoria con advertencia clara antes de solicitar la baja del servicio y contenedor; ante cancelación no se emite ninguna petición DELETE.
   - Polling de estado en `useOperacion`: consulta repetidamente sin disparar mutaciones de reinstalación ni duplicar componentes en el DOM.

---

## Comprobaciones automatizadas

- **Backend Unitarias / SQLite (`backend/tests/test_recuperacion_aplicaciones_011.py`)**:
  - 6 pruebas pasadas en 6.22 s:
    1. `test_lost_create_reply_queries_task_without_duplicating_ct`
    2. `test_lost_start_reply_queries_status_without_duplicating_installer`
    3. `test_changed_node_boot_retains_uncertainty_without_duplicating_or_completing`
    4. `test_disappeared_job_sets_uncertainty_without_duplicating_or_completing`
    5. `test_unreachable_source_prevents_ct_creation_and_releases_unsent_resources`
    6. `test_failing_access_probe_blocks_delivery_and_records_audit`

- **Backend Ciclo de Vida (`backend/tests/test_ciclo_vida_aplicaciones_011.py`)**:
  - 5 pruebas pasadas en 6.62 s:
    1. `test_detener_iniciar_reiniciar_sin_pull_ni_reinstalar_ni_regenerar_secretos`
    2. `test_identidad_incierta_o_ajena_rechaza_operaciones`
    3. `test_baja_fallida_mantiene_limpieza_pendiente_sin_liberar_red_ni_ledger`
    4. `test_oferta_retirada_permite_operar_instancia_existente`
    5. `test_cobertura_vencida_bloquea_reinicio`

- **Backend Endpoint Reintento Operación (`backend/tests/test_endpoint_reintentar_operacion_011.py`)**:
  - 4 pruebas pasadas en 5.22 s:
    1. `test_reintentar_operacion_requiere_auth_y_admin`
    2. `test_reintentar_operacion_no_encontrada`
    3. `test_reintentar_operacion_estado_invalido_o_incierto`
    4. `test_reintentar_operacion_fallida_confirmada_crea_reparar`

- **Backend PostgreSQL Concurrencia (`backend/tests/postgres/test_reintentos_011.py`)**:
  - 3 pruebas pasadas en 6.06 s:
    1. `test_reintento_concurrente_exactamente_una_operacion_reparar`
    2. `test_recreacion_mismo_pedido_conserva_secretos_aplicacion`
    3. `test_renovacion_conserva_secretos_originales_y_nuevo_alta_genera_nuevos`

- **Frontend Vitest (`frontend/tests/recuperacion-aplicaciones.test.jsx`)**:
  - 5 pruebas pasadas en 2.15 s:
    1. `fallo confirmado muestra botón Reintentar en el detalle del pedido`
    2. `estado incierto no muestra Reintentar masivo y visibiliza estado de verificación`
    3. `limpieza pendiente y textoOperacion visible cuando falla la eliminación`
    4. `confirmación destructiva requerida antes de solicitar baja de servicio`
    5. `polling de estado no dispara reinstalación ni duplicación de vistas`

- **Script de Ensayo de Laboratorio (`infra/laboratorio/011/probar_recuperacion.py` / SC-005)**:
  - 15 pruebas pasadas en 17.11 s:
    - `fallo_simulado_red_durante_bootstrap`: **VERIFICADO**.
    - `recuperacion_sin_duplicacion`: **VERIFICADO**.
    - `preservacion_secretos_datos`: **VERIFICADO**.
    - `ciclo_vida_sin_repull`: **VERIFICADO**.
    - `limpieza_segura_anteponiendo_ausencia`: **VERIFICADO**.

---

## Trazabilidad de tareas (US5)
- T088 a T098: Completadas y verificadas.
- Total acumulado de la spec 011: **77/95 tareas activas verificadas, 18 pendientes**.
