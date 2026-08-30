# Contratos de API: 005-revertir-aprobacion

**Fecha**: 2026-08-30 | Prefijo: `/api/v1`

Solo se documenta el endpoint **nuevo** y el que cambia de comportamiento. Los no listados mantienen
su contrato actual. Códigos de error según Principio III: 502 infraestructura, 409 conflicto de
estado, 403 permisos.

---

## `POST /pedidos/{pedido_id}/revertir-aprobacion` — nuevo

Deshace una aprobación antes de que el servicio se despliegue, liberando en el acto la capacidad que
esa aprobación comprometió (FR-001, FR-003).

Exige **rol administrador** (FR-012).

```jsonc
// Request — el motivo es obligatorio (FR-002)
{
  "motivo": "Aprobé el pedido equivocado; la cátedra había pedido el template chico"
}
```

```jsonc
// 200 OK
{
  "id": 12,
  "estado": "rechazado",
  "motivo_rechazo": "Aprobación revertida: Aprobé el pedido equivocado; la cátedra había pedido el template chico",
  "reserva_vcpus": 0,
  "reserva_ram_mb": 0,
  "reserva_disk_gb": 0,
  "reserva_expira_at": null,

  // La capacidad que volvió a estar libre, para que la interfaz lo muestre sin
  // tener que volver a consultar
  "capacidad_liberada": { "vcpus": 4, "ram_mb": 4096, "storage_gb": 8 },

  "historial": [ /* … la aprobación original sigue estando, y se suma la reversión */ ]
}
```

| Código | Caso |
|---|---|
| 400 | `motivo` vacío o ausente (FR-002). **No se toca** ni el pedido ni la capacidad |
| 403 | Quien llama no es administrador |
| 404 | El pedido no existe o está dado de baja |
| 409 | `pedido_no_aprobado` — el pedido nunca estuvo aprobado (FR-007) |
| 409 | `despliegue_en_curso` — el despliegue ya empezó (FR-006) |
| 409 | `reserva_ya_vencida` — el sistema la liberó solo (FR-014) |
| 409 | `ya_revertido` — otra reversión se adelantó (FR-005) |

**Ningún caso devuelve 500**, y ninguno deja el pedido en un estado intermedio.

### Los cuatro conflictos, en detalle

Comparten código HTTP pero son situaciones distintas para quien las recibe, así que cada una nombra
su salida:

```jsonc
// 409 — el pedido nunca estuvo aprobado (FR-007)
{
  "detail": {
    "codigo": "pedido_no_aprobado",
    "mensaje": "Este pedido no tiene ninguna aprobación que deshacer. Si querés que no avance, rechazalo.",
    "estado_actual": "solicitado"
  }
}
```

```jsonc
// 409 — el despliegue ya empezó (FR-006)
{
  "detail": {
    "codigo": "despliegue_en_curso",
    "mensaje": "El servicio ya se está creando o ya existe. Para deshacerlo hay que dar de baja el servicio, no la aprobación.",
    "estado_actual": "activo"
  }
}
```

```jsonc
// 409 — la reserva venció sola (FR-014)
{
  "detail": {
    "codigo": "reserva_ya_vencida",
    "mensaje": "La reserva de este pedido ya se liberó sola porque el despliegue nunca se concretó. No hay capacidad que recuperar."
  }
}
```

```jsonc
// 409 — dos reversiones a la vez (FR-005)
{
  "detail": {
    "codigo": "ya_revertido",
    "mensaje": "Otra persona revirtió esta aprobación recién. La capacidad ya está liberada."
  }
}
```

> Los dos últimos comparten la condición técnica —el pedido ya no está en `APROBADO`— pero se
> distinguen por el autor de la última transición: sistema es vencimiento, persona es reversión. Para
> quien las recibe son cosas distintas y el mensaje lo refleja (R6).

---

## `PATCH /pedidos/{pedido_id}/estado` — sin cambios

**Sigue rechazando** `aprobado → rechazado` con el mensaje actual. La reversión es una operación con
nombre propio, no un cambio de estado a mano: mover el estado sin liberar la reserva dejaría
capacidad huérfana, que es exactamente lo que esa restricción previene (R1).

---

## `GET /pedidos/{pedido_id}` — sin cambios de forma

El historial que ya devuelve permite distinguir las tres formas de llegar a `rechazado`, sin campos
nuevos (R4):

```jsonc
"historial": [
  { "estado_anterior": "nuevo",      "estado_nuevo": "solicitado", "usuario_id": 2,    "comentario": "Pedido creado" },
  { "estado_anterior": "solicitado", "estado_nuevo": "aprobado",   "usuario_id": 1,    "comentario": "Pedido aprobado" },
  { "estado_anterior": "aprobado",   "estado_nuevo": "rechazado",  "usuario_id": 1,    "comentario": "Aprobación revertida: …" }
  //                   ▲ aprobado distingue del rechazo original   ▲ persona distingue del vencimiento
]
```

Para el vencimiento automático la última entrada es idéntica en forma pero con `usuario_id: null`.

---

## `GET /capacidad/` — sin cambios

Tras una reversión, los valores vuelven exactamente a los previos a la aprobación (SC-002). No hace
falta tocar nada: el pedido revertido deja de cumplir la condición de reserva vigente y el cómputo lo
excluye solo.
