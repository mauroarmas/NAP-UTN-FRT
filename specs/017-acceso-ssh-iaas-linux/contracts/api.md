# Contrato HTTP: acceso SSH a servicios Linux IaaS

Prefijo `/api/v1`. Autenticación, CSRF e `Idempotency-Key` como el resto de los endpoints que mutan (ver `routers/servicios.py`).

## 1. Crear pedido (cambio)

`POST /pedidos` — `parametros_extra` admite un campo nuevo:

| Campo | Tipo | Regla |
|---|---|---|
| `clave_ssh_publica` | string ≤ 800 | **Obligatorio** si `modelo_servicio = iaas` y la plantilla es una base Linux del catálogo; prohibido en el resto. |

Errores (422, cuerpo estándar de `error()`):

| Código | Cuándo |
|---|---|
| `clave_ssh_requerida` | IaaS Linux sin clave. |
| `clave_ssh_invalida` | Formato, tipo no admitido, RSA < 3072 bits, varias líneas, opciones por delante. El mensaje dice qué corregir. |
| `clave_ssh_privada` | Parece una clave privada. «Pegá solo la clave pública (el archivo que termina en `.pub`).» |

Los demás modelos de servicio y los Docker/OCI no cambian.

## 2. Registrar o reemplazar la clave de un servicio entregado (nuevo)

`PUT /servicios/{servicio_id}/acceso-ssh`

Cuerpo: `{ "clave_publica": "ssh-ed25519 AAAA…" }`

Permisos: titular del servicio o administración (`requiere_acceso_servicio`). Cualquier otra persona recibe 403, sin revelar si la clave existe.

Respuesta `202`:

```json
{ "servicio_id": 41, "operacion_id": "…", "huella": "SHA256:…", "revision": 2, "estado": "pendiente" }
```

Errores: 403 permisos · 404 servicio · 409 `servicio_no_linux` · 409 `operacion_en_curso` · 409 `servicio_no_activo` (dado de baja o en baja) ·
422 `clave_ssh_invalida` / `clave_ssh_privada`. Mismo `Idempotency-Key` + mismo cuerpo devuelve la misma respuesta; mismo `Idempotency-Key` con otra clave es 409.

Registrar sobre un servicio sin clave y reemplazar son la misma operación (la revisión pasa de inexistente a 1, o de N a N+1).

## 3. Consultar el acceso (cambio aditivo)

`GET /servicios/{servicio_id}/acceso` conserva todos los campos actuales (incluidos `metodo` y la compuerta de consola) y agrega, **solo** para Linux IaaS:

```json
"acceso_ssh": {
  "estado": "sin_clave | pendiente | aplicada | fallida",
  "usuario": "nap",
  "direccion": "192.168.100.120",
  "puerto": 22,
  "comando": "ssh nap@192.168.100.120",
  "huella": "SHA256:…",
  "verificado_at": "2026-11-03T21:10:00Z",
  "puede_conectar": true,
  "motivo": null
}
```

- `puede_conectar` es `true` solo con `estado = aplicada`, servicio `RUNNING` y vigencia cubierta; si no, `comando` es `null` y `motivo` lo explica en lenguaje llano.
- `fallida` incluye `motivo` seguro (sin salida cruda del nodo).
- Nunca se devuelve la clave, solo la huella.
- `metodo` sigue siendo `consola` (FR-015). El front muestra el bloque SSH además del botón de consola.

## 4. Historial

`GET /servicios/{id}/historial` incluye los eventos `acceso_ssh_*` con autor, momento y huella.
