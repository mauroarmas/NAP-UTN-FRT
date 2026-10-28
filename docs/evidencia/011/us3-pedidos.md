# US3: Solicitar y recibir una instancia por cátedra — Evidencia

## Componentes implementados y verificados (27/10/2026)

1. **Aislamiento estricto entre cátedras**:
   - Cada cátedra sólo visualiza, crea, solicita aclaración y consulta sus propios pedidos y servicios (`test_aislamiento_entre_catedras` en `test_pedidos_aplicaciones_011.py`).
   - Acceso cruzado responde con HTTP 403 Forbidden.
   - No se mezclan credenciales ni recursos entre cátedras que solicitan la misma aplicación.

2. **Cero CTs ni compromisos prematuros al registrar el pedido**:
   - Registrar un pedido docente (incluyendo la opción «Otro» con referencia de imagen opcional e instrucciones de uso) no crea contenedores LXC, no inicia workers ni reserva capacidad en Proxmox (`test_solicitud_otro_sin_hardware_ni_reservas_prematuras`).
   - Solicitudes de aclaración, rechazos y reenvíos por parte del docente preservan el estado sin alterar la capacidad del nodo ni crear artefactos anticipados (`test_flujo_aclaracion_rechazo_reenvio_sin_reservas_prematuras`).
   - Referencias con credenciales incrustadas (`usuario:password@host` o `docker://auth@...`) son rechazadas estrictamente con HTTP 422 (`credenciales_en_referencia`).

3. **Aprobación con reserva atómica e inicio diferido de despliegue**:
   - La aprobación administrativa realiza la reserva indivisible de capacidad (`CompromisoCapacidad`) en una sola transacción (`aprobar` en `admision_service.py`).
   - Concurrencia evaluada bajo PostgreSQL real (`test_dos_aprobaciones_capacidad_compartida_una_sola_reserva` en `test_despliegue_011.py`): ante dos aprobaciones concurrentes compitiendo por el último cupo, una sola reserva es efectiva y la otra falla limpiamente.
   - Decisión unificada en aprobación:
     - Pedidos inmediatos (`solicitar_despliegue = True` con inicio vigente): se encola la operación de despliegue.
     - Pedidos con vigencia futura (`solicitar_despliegue = True` con inicio futuro): se registra `despliegue_programado_at` sin crear CT ni operación anticipada. El worker periódico (`despliegue_programado_service.py`) despacha el despliegue al llegar la fecha de inicio.
     - Decisiones contradictorias (ej. vigencia futura con solicitud de despliegue inmediato) son rechazadas con HTTP 422 (`decision_despliegue_invalida`).
   - Renovaciones conservan el snapshot de asignación sin duplicar reservas de capacidad (`test_renovacion_conserva_snapshot_y_una_unica_reserva`).

4. **Configuración write-only y protección de secretos**:
   - Los campos sensibles de despliegue (`valores_privados`) son ingresados exclusivamente por el administrador en la aprobación si el perfil lo requiere.
   - Son cifrados antes de su persistencia en base de datos (`secreto_despliegue_service.py`).
   - No se almacenan en texto claro en snapshots de asignación (`asignacion_snapshot`), ni en respuestas de pedidos, ni en logs de idempotencia (`test_aprobacion_congela_revision_y_valores_sensibles_write_only`).

5. **Experiencia de usuario simplificada (docente y administrador)**:
   - Formulario docente (`NuevoPedidoModal.jsx`): selección de aplicación/propósito/fechas. Si elige «Otro», puede ingresar opcionalmente la referencia de imagen y las instrucciones de uso; sin exponer configuraciones técnicas de hardware (vCPUs/RAM/disco).
   - Modal de aprobación (`AprobarPedidoModal.jsx`): selección de tamaño permitido (Small / Medium), destino y decisión clara unificada («Programar despliegue al inicio de vigencia» vs «Desplegar después de aprobar»), con solicitud de campos privados cuando el perfil lo exige.

## Comprobaciones automatizadas

- **Backend SQLite / Unitarias**:
  - `backend/tests/test_pedidos_aplicaciones_011.py`: 8 pruebas pasadas (aislamiento entre cátedras, solicitud "Otro", rechazo credenciales en URL, aclaración/rechazo/reenvío, congelamiento de revisión, secretos write-only).
  - `backend/tests/test_despliegue_programado_011.py`: 6 pruebas pasadas (reloj controlado, inicio inclusivo, tick idempotente, invalidación por cambio de revisión o cancelación, perfil bloqueado, período de gracia de reserva).
- **Backend PostgreSQL Concurrencia**:
  - `backend/tests/postgres/test_despliegue_011.py`: 4 pruebas pasadas (dos aprobaciones concurrentes en capacidad compartida, oferta modificada en evaluación, dos admisiones concurrentes sobre mismo pedido, renovación conservando snapshot).
- **Frontend Vitest**:
  - `frontend/tests/pedidos-formularios.test.jsx`: 13 pruebas pasadas (incluye las pruebas de "Otro" con referencia/instrucciones sin hardware y aprobación unificada con campos privados y programación futura).

## Trazabilidad de tareas (US3)
- T065 a T076: Completadas y verificadas.
- Total acumulado de la spec 011: **55/95 tareas activas verificadas, 40 pendientes**.

