# Contratos de API: 006-ciclo-vida-entidades

**Fecha**: 2026-08-30 | Prefijo: `/api/v1`

Solo se documentan los endpoints **nuevos** y los que **cambian de forma**. Los no listados mantienen
su contrato actual. Códigos de error según Principio III: 502 infraestructura, 409 conflicto de
estado, 403 permisos.

Todos los endpoints de este documento exigen **rol administrador**: FR-008 lo fija para plantillas,
y para personas se conserva el `require_admin` que ya rige hoy (la spec lo registra como supuesto
explícito, no como capacidad nueva).

---

## Plantillas

### `PATCH /templates/{template_id}` — nuevo

Corrige una plantilla existente, o la retira del catálogo. Todos los campos son opcionales: se
aplican solo los enviados (FR-001, FR-004).

```jsonc
// Request — corregir la imagen mal cargada (el caso que motivó la feature)
{
  "os_template": "local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst"
}
```

```jsonc
// Request — retirar del catálogo
{
  "activo": false
}
```

Campos aceptados: `nombre`, `descripcion`, `default_vcpus`, `default_ram_mb`, `default_disk_gb`,
`justificacion_disco`, `os_template`, `config_extra`, `activo`.

**`tipo` no se acepta** (regla T4): cambiar `lxc` por `qemu` altera la naturaleza de lo que ya se
aprobó sobre esa plantilla. Enviarlo devuelve 400.

```jsonc
// 200 OK
{
  "id": 6,
  "nombre": "Debian 13 LXC small",
  "tipo": "lxc",
  "default_vcpus": 1, "default_ram_mb": 256, "default_disk_gb": 4,
  "justificacion_disco": null,
  "os_template": "local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst",
  "config_extra": null,
  "activo": true,

  // Informativo, no bloqueante (FR-003): qué queda fuera del alcance del cambio
  "alcance_del_cambio": {
    "servicios_desplegados": 3,      // no se ven afectados
    "pedidos_aprobados_pendientes": 1 // se desplegarán con lo que reservaron
  }
}
```

| Código | Caso |
|---|---|
| 400 | `default_disk_gb` supera el tope sin `justificacion_disco` (FR-007) |
| 400 | Se envió `tipo` (T4) |
| 403 | Quien llama no es administrador |
| 404 | La plantilla no existe |
| 409 | El `nombre` nuevo ya lo usa otra plantilla (T6) |

**Notas**:

- Retirar una plantilla ya en uso **no** requiere confirmación: no rompe nada. Los servicios
  desplegados siguen igual (T1) y los pedidos aprobados conservan su reserva (T2).
- Reactivar es `{"activo": true}`; no tiene tratamiento especial.

### `GET /templates/` — sin cambios

Sigue devolviendo solo las plantillas activas. Ya lo hacía.

### `GET /templates/{template_id}` — sin cambios

Sigue resolviendo cualquier plantilla, activa o retirada, para que el historial sea legible (FR-006).
Ya lo hacía.

### `POST /pedidos/` — sin cambios de forma

Sigue rechazando con 404 los pedidos que apunten a una plantilla inactiva (FR-005). Ya lo hacía
(`pedido_service.py:100`).

---

## Personas

### `DELETE /usuarios/{usuario_id}` — cambia de semántica y de respuesta

Retira a una persona. **Deja de ser un borrado físico incondicional** (FR-009, FR-010).

El sistema decide por sí solo entre baja lógica y borrado real, según haya o no historial: quien
llama no necesita saberlo de antemano (US2, escenario 3).

```jsonc
// 200 OK — persona con historial: baja lógica
{
  "id": 3,
  "username": "ajeno",
  "resultado": "desactivado",
  "mensaje": "La cuenta quedó dada de baja. Sus pedidos siguen figurando en el historial de la cátedra."
}
```

```jsonc
// 200 OK — persona sin historial: borrado real
{
  "id": 9,
  "username": "tipeo_mal",
  "resultado": "eliminado",
  "mensaje": "La cuenta se eliminó. No tenía pedidos ni cátedras a cargo."
}
```

> **Cambio de contrato**: antes devolvía `204 No Content`. Ahora devuelve `200` con cuerpo, para que
> la interfaz pueda decir qué ocurrió. El frontend (`api.js: deleteUsuario`) debe contemplarlo.

| Código | Caso |
|---|---|
| 400 | Intento de retirarse a uno mismo (U7, ya existía) |
| 403 | Quien llama no es administrador |
| 404 | La persona no existe |
| 409 | `ultimo_administrador` — es la última cuenta admin activa (U6, FR-013) |
| 409 | `catedras_sin_responsable` — tiene cátedras a cargo (U8, FR-016) |

**Ningún caso devuelve 500.** Es el requisito central de la US2 (FR-015).

```jsonc
// 409 — último administrador
{
  "detail": {
    "codigo": "ultimo_administrador",
    "mensaje": "Es la única cuenta de administrador activa. Designá otro administrador antes de dar de baja esta cuenta."
  }
}
```

```jsonc
// 409 — cátedras a cargo (mensaje corregido, FR-016/FR-017)
{
  "detail": {
    "codigo": "catedras_sin_responsable",
    "mensaje": "Esta persona es titular de cátedras que quedarían sin responsable. Reasignalas a otra persona antes de dar de baja la cuenta.",
    "catedras": [{"id": 3, "nombre": "Catedra Ajena T091"}]
  }
}
```

> **Qué cambió en el texto**: se eliminó "o dalas de baja". Se verificó en entorno real que dar la
> cátedra de baja **no** destraba la operación, porque una cátedra inactiva puede conservar servicios
> corriendo y sigue necesitando responsable (R5). El único camino que funciona es reasignar, y ahora
> el mensaje dice solo eso.

### `PATCH /usuarios/{usuario_id}` — cambia el mensaje de bloqueo

Mismo contrato. El 409 `catedras_sin_responsable` adopta el texto corregido de arriba (FR-016).

### `GET /usuarios/` — cambia el comportamiento por defecto

Pasa a devolver solo las personas **activas** (FR-012, R6), en línea con el criterio que el
Principio V ya fija para pedidos y servicios.

```text
GET /usuarios/                    → solo activas (nuevo comportamiento por defecto)
GET /usuarios/?incluir_bajas=true → todas, activas y retiradas
```

Cada elemento incorpora `activo` para que la interfaz pueda distinguirlas cuando se piden todas.

### `GET /usuarios/{usuario_id}` — sin cambios

Sigue resolviendo a cualquier persona, activa o retirada: el historial de un pedido tiene que poder
mostrar quién lo pidió aunque ya no esté (R6).

---

## Efecto indirecto: el despliegue

No hay endpoint nuevo, pero `POST /servicios/desplegar/{pedido_id}` **cambia de comportamiento
observable** (R2, FR-018):

- **Antes**: armaba el contenedor con `template.default_vcpus / default_ram_mb / default_disk_gb`.
- **Ahora**: lo arma con `pedido.reserva_vcpus / reserva_ram_mb / reserva_disk_gb`.

Para todo pedido aprobado antes de esta feature los valores coinciden, así que no hay cambio
perceptible. La diferencia aparece solo si la plantilla se editó entre la aprobación y el despliegue
— que es justamente lo que esta feature vuelve posible.

Sin este cambio, editar una plantilla sobrecomprometería el clúster de forma retroactiva y silenciosa.
