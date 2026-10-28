# US4: Progreso y consola administrativa de lectura — Evidencia

## Componentes implementados y verificados (28/10/2026)

1. **Endpoint de lectura segura (`GET /operaciones/{id}/consola`)**:
   - Exclusivo para administradores (`401` no autenticado, `403` docente/cátedra).
   - Resuelve la raíz lógica de la operación (`coalesce(operacion_raiz_id, id)`), unificando el registro a través de reintentos e intentos sucesivos.
   - Parámetros de consulta y paginación con cursores:
     - `after` exclusivo y `before` exclusivo (mutuamente excluyentes; `422` ante ambos).
     - `limit_bytes` validado en rango [1, 65536] (`422` ante fuera de rango).
     - `through_seq` para congelar exportaciones o ventanas históricas.
     - Consulta tail predeterminada cuando no se pasan cursores (últimos mensajes hasta `limit_bytes` en orden ascendente por `seq`).
   - Cabecera obligatoria `Cache-Control: no-store`.
   - Soporte para creación fallida antes de existir job en nodo (devuelve hitos seguros del portal y resultado final sin `404` ni `500`).
   - Si el registro fue recortado o expiró tras 30 días, devuelve cabecera, `expired=true`, `dropped_messages` y `resultado_final` seguro sin `404`.

2. **Ingesta y retención concurrente (PostgreSQL)**:
   - Compartición de secuencia global y cuota entre portal y runner bajo bloqueo de fila en cabecera `ConsolaOperacion`.
   - Ingestas concurrentes con claves de hito idénticas deduplicadas sin colisión.
   - Purga a 30 días verificada con preservación de cabecera y resultado seguro.
   - Exportación concurrente con `through_seq` congelado sin mezclar fragmentos generados en paralelo.

3. **Interfaz de usuario (`ConsolaOperacion.jsx` y `useConsolaOperacion.js`)**:
   - Visual estilo terminal: fondo negro `#000000`, texto blanco `#ffffff`, tipografía monoespaciada (`monospace`).
   - Texto literal depurado: sin ejecución de scripts ni parseo de tags HTML o secuencias de escape ANSI.
   - Ventana DOM acotada y deduplicación por `seq`.
   - Consulta periódica visible cada 1 s con cancelación vía `AbortController`.
   - Ante fallo de red en la consulta, conserva las líneas y el último estado conocido.
   - Ante revocación de permisos (`401`/`403`), limpia inmediatamente el buffer de consola y muestra el aviso de acceso revocado.
   - Detección de scroll: cuando el usuario sube a revisar el historial, el auto-desplazamiento se pausa y se muestra un contador de nuevos mensajes con botón para volver al final.
   - Paginación de mensajes anteriores mediante botón «▲ Cargar mensajes anteriores» con cursor `before`.
   - Copia al portapapeles y descarga de archivo `.txt` congelando `through_seq` y verificando autorización por página.

4. **Integración en vistas y seguimiento de despliegue**:
   - `ProgresoDespliegue.jsx`: adaptado a las fases reales del motor OCI (`creacion`, `instalacion`, `comprobacion`, etc.) sin inventar porcentajes de tiempo.
   - Botón «Ver consola» exclusivo para administración integrado en `Pedidos.jsx` (tarjetas y diálogo de detalle) y `Servicios.jsx` (bloque de operaciones activas y filas de servicios ocupados).
   - Separación estricta respecto de la consola interactiva IaaS (la consola de operación es estrictamente de lectura de logs).

## Comprobaciones automatizadas

- **Backend Unitarias / SQLite (`backend/tests/test_consola_operacion_011.py`)**:
  - 10 pruebas pasadas en 9.18 s:
    1. `test_consola_requiere_autenticacion_y_rol_admin`: 401 sin auth, 403 docente, 200 admin.
    2. `test_consola_operacion_no_encontrada`: 404 con código `operacion_no_encontrada`.
    3. `test_consola_tail_inicial_y_cabeceras_no_store`: tail ascendente, metadata y cabecera `no-store`.
    4. `test_consola_cursores_after_y_before_mutuamente_excluyentes`: 422 ante ambos, avance con `after`, retroceso con `before`.
    5. `test_consola_through_seq_para_exportacion`: congelamiento de corte sin incluir `seq` superiores.
    6. `test_consola_after_detras_del_rango_retenido_salta_a_disponible`: salto seguro ante mensajes recortados con `truncated=true`.
    7. `test_consola_expirada_devuelve_cabecera_y_resultado_sin_404`: 200 con `expired=true` y `resultado_final`.
    8. `test_consola_creacion_fallida_antes_de_job_nodo`: hitos del portal y fallo final sin job del nodo.
    9. `test_consola_limite_bytes_valido_y_rechazo_fuera_de_rango`: 422 ante límites fuera de rango y acotamiento de batch.
    10. `test_consola_resuelve_raiz_desde_operacion_hija`: resolución transparente de raíz lógica desde reintento.

- **Backend PostgreSQL Concurrencia (`backend/tests/postgres/test_consola_011.py`)**:
  - 5 pruebas pasadas en 9.16 s:
    1. `test_concurrent_portal_runner_replays_share_one_header_and_one_global_sequence`: secuencia y cabecera única compartida.
    2. `test_quota_is_shared_by_all_attempts_of_the_root_and_preserves_old_attempts`: cuota compartida hasta 10 MB preservando intentos antiguos.
    3. `test_identical_local_keys_are_distinct_between_producers_but_not_within_one_producer`: deduplicación estricta por productor.
    4. `test_purga_30_dias_preserva_cabecera_y_resultado_seguro`: purga temporal de fragmentos manteniendo cabecera.
    5. `test_exportacion_concurrente_con_through_seq_fijado`: exportación aislada mientras ocurre ingesta paralela.

- **Frontend Vitest (`frontend/tests/consola-operacion.test.jsx`, `frontend/tests/progreso-despliegue.test.jsx`)**:
  - 8 pruebas de consola pasadas en 1.12 s (estilos negro/blanco/mono, texto literal sin XSS/ANSI, deduplicación, páginas anteriores con cursor, conservación ante error de red, recorte/expiración, revocación 403, copia/descarga).
  - 6 pruebas de progreso pasadas en 0.58 s (fases reales OCI, incertidumbre, fallo sin spinner, acceso pendiente).

- **Medición de rendimiento y ausencia de secretos (T087 / SC-004)**:
  - Ejecución de `infra/laboratorio/011/medir_consola.py`:
    - Latencia captura→pantalla (p95): **0.0795 s** (objetivo: <= 5.0 s) -> **CUMPLIDO**.
    - Latencia máxima de apertura: **0.0122 s** (objetivo: <= 3.0 s) -> **CUMPLIDO**.
    - Secretos detectados en fragmentos/base de datos: **0**.
  - E2E instrumentados en Playwright: `despliegue-aplicaciones.spec.js` y `consola-rendimiento.spec.js`.

## Trazabilidad de tareas (US4)
- T077 a T087: Completadas y verificadas.
- Total acumulado de la spec 011: **66/95 tareas activas verificadas, 29 pendientes**.
