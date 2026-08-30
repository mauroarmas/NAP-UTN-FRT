# Quickstart de validación: 005-revertir-aprobacion

**Feature**: 005-revertir-aprobacion | **Fecha**: 2026-08-30

Guía para validar la feature una vez implementada. El escenario E1 reproduce la secuencia exacta que
originó la spec, encontrada el 2026-08-29 durante la validación T091 de la feature 004.

---

## Prerrequisitos

- Stack levantado: `docker compose up -d` (API en `:8001`, frontend en `:5174`)
- Proxmox alcanzable con el token configurado en `.env`
- Una cátedra con al menos una plantilla disponible

```bash
ADMIN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -d "username=admin&password=admin" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
CAT=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -d "username=catedra&password=catedra" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
```

---

## 1. Pruebas automatizadas

```bash
cd backend && ./venv/bin/python -m pytest -q
```

Deben pasar las existentes (250 al cierre de la feature 006) más las nuevas:

| Archivo | Cubre |
|---|---|
| `test_reversion_aprobacion.py` | FR-001 a FR-003, FR-006 a FR-014 |
| `test_reversion_concurrencia.py` | **FR-004, FR-005, SC-006 — compuerta de capacidad** |

```bash
cd frontend && npm run build   # sin errores
```

---

## 2. Escenarios de validación manual

### E1 — Deshacer un sobrecompromiso (US1) — **el escenario que originó la spec**

Reproduce lo ocurrido el 2026-08-29, cuando no hubo forma de deshacerlo.

1. Anotar `libre` de `GET /capacidad`.
2. Crear un pedido con una plantilla **más grande que la capacidad libre** y aprobarlo con la
   justificación que el sistema exige. El saldo libre queda **en negativo**.
3. Comprobar que ese sobrecompromiso **bloquea a otra cátedra**: pausar un servicio ajeno e intentar
   reactivarlo → `409 sin_capacidad`.
4. **Revertir la aprobación** con un motivo.
5. Verificar que `libre` volvió **exactamente** a los valores del paso 1 (SC-002).
6. Reintentar la reactivación del paso 3 → ahora funciona.

**Lo que se está midiendo**: que el daño colateral entre cátedras dure lo que tarda una persona en
advertirlo, y no las 24 h del vencimiento automático (SC-003).

### E2 — La reversión exige motivo (FR-002)

1. Revertir sin `motivo` → **400**.
2. Revertir con `motivo` en blanco (`"   "`) → **400**.
3. Verificar que en ambos casos el pedido **sigue aprobado** y la capacidad **sigue comprometida**:
   un rechazo no puede dejar la operación a medias.

### E3 — El historial distingue las tres formas de llegar a rechazado (US3, FR-009) — **bloqueante**

Es lo que hace auditable el consumo histórico (Principio V).

1. Producir los tres casos sobre pedidos distintos:
   - uno **rechazado de entrada** desde `solicitado`,
   - uno con la **aprobación revertida**,
   - uno cuya **reserva venció sola** (adelantar `reserva_expira_at` y correr
     `POST /admin/jobs/expirar_reservas`).
2. Consultar el historial de los tres y verificar que se distinguen sin ambigüedad:
   - el rechazo original tiene `estado_anterior: "solicitado"`,
   - la reversión tiene `estado_anterior: "aprobado"` y **autor persona**,
   - el vencimiento tiene `estado_anterior: "aprobado"` y **autor sistema** (`usuario_id: null`).
3. Verificar que en el pedido revertido **la entrada de la aprobación original sigue presente**, sin
   sobrescribir.

### E4 — Dos reversiones simultáneas (FR-005, SC-006) — **el bloqueante crítico**

Es el único escenario que puede inflar el saldo libre por encima de la capacidad real.

1. Aprobar un pedido y anotar `libre`.
2. Disparar **dos reversiones concurrentes** sobre el mismo pedido:
   ```bash
   for i in 1 2; do
     curl -s -o /tmp/rev_$i.json -w "%{http_code}\n" \
       -X POST "http://localhost:8001/api/v1/pedidos/$PID/revertir-aprobacion" \
       -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
       -d '{"motivo":"prueba de concurrencia"}' &
   done; wait
   ```
3. Verificar que **exactamente una** devuelve 200 y la otra **409 `ya_revertido`**.
4. **Verificar que `libre` subió una sola vez**: si subió el doble, la capacidad quedó inflada y el
   sistema aprobará sobre recursos que no existen.

### E5 — No se puede revertir un despliegue en curso (FR-006)

1. Aprobar un pedido y **desplegarlo**.
2. Intentar revertir → **409 `despliegue_en_curso`**, con el mensaje indicando que la vía es dar de
   baja el servicio.
3. Verificar que el servicio **sigue funcionando** y que su contenedor sigue en Proxmox.

### E6 — No se puede revertir lo que nunca se aprobó (FR-007)

1. Sobre un pedido en `solicitado`, intentar revertir → **409 `pedido_no_aprobado`**, sugiriendo
   rechazarlo.

### E7 — La reserva ya vencida da su propio mensaje (FR-014)

1. Aprobar un pedido, adelantar `reserva_expira_at` y correr `expirar_reservas`.
2. Intentar revertir → **409 `reserva_ya_vencida`**, y **no** un genérico "transición inválida".
3. Verificar que la capacidad **no** se libera por segunda vez.

### E8 — La cátedra entiende qué pasó (US2, FR-010) — **bloqueante**

1. Con una cuenta de cátedra, mirar un pedido propio **antes** de la reversión: figura aprobado.
2. Un administrador lo revierte con un motivo.
3. Verificar que la cátedra ve el cambio **y el motivo**, redactado de forma entendible sin
   conocimientos técnicos.
4. Verificar que el portal lo presenta como una **aprobación revertida** y no como un rechazo a
   secas.

### E9 — La cátedra puede volver a pedir lo mismo (FR-011)

1. Tras la reversión, crear un pedido nuevo por el mismo recurso.
2. Verificar que se acepta con normalidad y aparece en la bandeja del administrador. La reversión no
   es una sanción.

### E10 — Revertir una renovación no toca el servicio (FR-013)

1. Solicitar la renovación de un servicio y aprobarla, **sin ejecutarla**.
2. Anotar el `vence_at` del servicio.
3. Revertir la aprobación de la renovación.
4. Verificar que el servicio **conserva su `vence_at` anterior**, sigue corriendo, y su contenedor
   está intacto en Proxmox.

### E11 — Solo el administrador revierte (FR-012)

1. Con una cuenta de cátedra, intentar revertir un pedido **propio** → **403**.

---

## 3. Verificación de capacidad

Para E1 y E4, contrastar los tres valores antes y después:

```bash
curl -s http://localhost:8001/api/v1/capacidad/ -H "Authorization: Bearer $ADMIN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('reservado:',d['reservado'],'libre:',d['libre'])"
```

Tras revertir, `reservado` debe haber bajado exactamente lo que ese pedido tenía comprometido, y
`libre` debe haber subido lo mismo. Ni más ni menos.

---

## Criterios de aceptación de la validación

| Escenario | Requisitos | Bloqueante |
|---|---|---|
| Suite de pruebas en verde | Compuerta constitucional | ✅ |
| E4 (dos reversiones simultáneas) | FR-005, SC-006 | ✅ |
| E3 (el historial distingue los tres casos) | FR-009, SC-004 | ✅ |
| E8 (la cátedra entiende qué pasó) | FR-010, SC-005 | ✅ |
| E1 (deshacer un sobrecompromiso) | FR-001, FR-003, SC-001, SC-002 | ✅ |
| E2, E5, E6, E7, E9, E10, E11 | US1–US3 | ⚠ |

**E4 es el más importante**: es el único que puede dejar el sistema peor que antes de la feature. Una
capacidad libre inflada hace que el administrador apruebe sobre recursos que no existen, que es
exactamente el defecto que la feature 004 vino a cerrar.
