# Phase 1 — Quickstart: validación end-to-end

**Feature**: `001-pedido-soft-delete-retry`

Cómo verificar que el feature funciona. Los detalles de forma de request/response están en [contracts/api.md](./contracts/api.md); los cambios de esquema en [data-model.md](./data-model.md).

---

## Prerrequisitos

- PostgreSQL levantado (`docker compose up -d db` desde la raíz del repo).
- Entorno virtual del backend activo con las dependencias instaladas, incluidas las nuevas de testing:
  ```bash
  cd backend
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- Migración aplicada:
  ```bash
  cd backend && alembic upgrade head
  ```
  Verificar que `pedidos` tiene `deleted_at` y `vmid_reservado`, y `servicios` tiene `deleted_at`.
- Datos de prueba cargados: `python scripts/seed_dev.py` (crea cátedras, usuarios y templates).

---

## Validación automatizada (camino principal)

Es la vía primaria: no requiere un Proxmox real, porque el cliente se sustituye por un doble de prueba que puede simular fallos de forma determinística.

```bash
cd backend
pytest -v
```

**Resultado esperado**: todas las pruebas en verde, cubriendo como mínimo:

| Escenario | Archivo | Valida |
|-----------|---------|--------|
| Reintento exitoso desde ERROR | `tests/test_reintento_despliegue.py` | US1 esc. 1, FR-001, FR-003 |
| Reintento que vuelve a fallar deja historial nuevo | `tests/test_reintento_despliegue.py` | US1 esc. 2, FR-005 |
| Reintento sobre pedido que no está en ERROR → 409 | `tests/test_reintento_despliegue.py` | US1 esc. 3, FR-002 |
| Reutilización del VMID reservado libre | `tests/test_reintento_despliegue.py` | US1 esc. 4, FR-004 |
| VMID tomado por un tercero → se pide uno nuevo | `tests/test_reintento_despliegue.py` | US1 esc. 5, edge case |
| Contenedor huérfano con hostname propio → se adopta | `tests/test_reintento_despliegue.py` | research R2 |
| Reintento por usuario no admin → 403 | `tests/test_reintento_despliegue.py` | FR-006 |
| Baja de servicio excluye de listados pero preserva la fila | `tests/test_soft_delete.py` | US2 esc. 1–3, FR-007..FR-009 |
| Fallo de Proxmox al liberar → no se marca `deleted_at` | `tests/test_soft_delete.py` | FR-010 |
| Baja de pedido sin servicio (rechazado) | `tests/test_soft_delete.py` | US2 esc. 6, FR-013 |
| Baja de pedido con servicio vigente → 409 | `tests/test_soft_delete.py` | US2 esc. 7, FR-014 |
| Doble baja es idempotente | `tests/test_soft_delete.py` | US2 esc. 5 |
| Servicio dado de baja no consume cuota | `tests/test_soft_delete.py` | FR-012, SC-005 |

---

## Validación manual contra Proxmox real (opcional)

Solo si se quiere confirmar el comportamiento contra el clúster de verdad. Requiere credenciales válidas de Proxmox en `.env`.

```bash
cd backend && uvicorn app.main:app --reload
```

### A. Reintento tras un fallo real

1. Autenticarse como admin en `POST /api/v1/auth/login` y guardar el token.
2. Crear un pedido y llevarlo a `aprobado` mediante `PATCH /api/v1/pedidos/{id}/estado`.
3. **Provocar el fallo**: la forma más simple es apuntar temporalmente `proxmox_host` en `.env` a una IP inalcanzable, o usar un `storage` inexistente en el body del despliegue.
4. `POST /api/v1/servicios/desplegar/{pedido_id}` → esperar `502`; el pedido queda en `error`.
5. Confirmar en `GET /api/v1/pedidos/{id}` que `vmid_reservado` quedó grabado (esto es lo que hoy **no** ocurre).
6. Restaurar la configuración correcta.
7. `POST /api/v1/pedidos/{pedido_id}/reintentar` → esperar `200` con el `ServicioResponse`.
8. Verificar en la interfaz de Proxmox que existe **un solo** contenedor, con el VMID reservado en el paso 5.
9. `GET /api/v1/pedidos/{id}` → el historial debe mostrar la secuencia completa: `aprobado → en_despliegue → error → en_despliegue → activo`.

### B. Baja lógica preservando historial

1. Sobre el servicio recién desplegado: `DELETE /api/v1/servicios/{servicio_id}` → `200`.
2. Verificar en Proxmox que el contenedor **ya no existe**.
3. `GET /api/v1/servicios/` → el servicio **no** aparece.
4. Consultar la fila directamente en la base para confirmar que **sigue existiendo** con `deleted_at` poblado:
   ```bash
   docker compose exec db psql -U ps_user -d ps_db \
     -c "SELECT id, catedra_id, vcpus_asignados, ram_asignada_mb, deleted_at FROM servicios WHERE id = <servicio_id>;"
   ```
5. `GET /api/v1/catedras/{catedra_id}` → el uso de recursos informado **no** debe incluir ese servicio (cuota liberada, SC-005).
6. `DELETE /api/v1/pedidos/{pedido_id}` → ahora que el servicio está dado de baja, debe responder `200`. Intentarlo antes del paso 1 debe dar `409`.

---

## Criterios de aceptación de la validación

- [ ] `pytest` pasa completo, sin pruebas omitidas.
- [ ] Un pedido en `error` se recupera con **una sola** llamada al endpoint de reintento (SC-001).
- [ ] El historial del pedido muestra **todos** los intentos, en orden cronológico (SC-002).
- [ ] Los servicios dados de baja siguen consultables en la base con sus recursos asignados (SC-003).
- [ ] Los listados de `/pedidos/` y `/servicios/` no devuelven ningún registro dado de baja (SC-004).
- [ ] Ningún registro dado de baja consume cuota de su cátedra (SC-005).
- [ ] Ningún reintento produce contenedores duplicados en Proxmox.