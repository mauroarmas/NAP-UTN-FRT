# Data Model: Acceso SSH a servicios IaaS Linux

## ClaveAccesoServicio (tabla nueva `claves_acceso_servicio`)

Una fila por servicio Linux IaaS. Solo guarda material público.

| Campo | Tipo | Regla |
|---|---|---|
| `id` | PK | |
| `servicio_id` | FK `servicios.id`, **único** | Una clave por servicio. Se elimina con la baja lógica del servicio (no se reutiliza). |
| `tipo` | texto | `ssh-ed25519`, `ecdsa-sha2-nistp256/384/521` o `ssh-rsa` (≥ 3072 bits). Sale de la propia clave. |
| `clave_publica` | texto ≤ 800 | Una línea, `tipo base64`, **sin comentario ni opciones** (se normaliza). |
| `huella_sha256` | texto | `SHA256:…`. Es lo único que se muestra y se registra en el historial. |
| `usuario` | texto | Fijo `nap`. |
| `revision` | entero ≥ 1 | Sube con cada alta o reemplazo. |
| `aplicada_revision` | entero, nulo | Revisión que el runner confirmó. Nulo = nunca aplicada. |
| `registrada_por_id` | FK `usuarios.id` | Quién la registró o reemplazó por última vez. |
| `registrada_at` / `aplicada_at` | fecha | |

**Estado derivado** (sin columna): `pendiente` si `aplicada_revision` es nulo o menor que `revision`; `aplicada` si son iguales.

**Validación** (`app/utils/ssh_keys.py`, única fuente): una sola línea; tipo admitido; la base64 decodifica y el tipo interno coincide con
el declarado; RSA ≥ 3072 bits; se rechaza `PRIVATE KEY`, opciones por delante (`command=`, `from=`…), varias líneas y caracteres de control;
el comentario se descarta. Devuelve `(tipo, clave_normalizada, huella)` o un error con código estable.

## Cambios en tablas existentes

- `pedidos.parametros_extra` (JSON): admite `clave_ssh_publica` cuando `modelo_servicio = iaas` con base Linux. Al aprobar, la clave normalizada
  pasa a `asignacion_snapshot['acceso_ssh']` junto con su huella; `_materialize` crea la fila de `claves_acceso_servicio` con `revision = 1`.
- `operaciones_infraestructura.tipo`: nuevo valor `acceso_ssh`. Contexto seguro: `servicio_id`, `revision`. **No** guarda la clave (se lee de la tabla al ejecutar).
- `historial_servicio`: eventos `acceso_ssh_registrado`, `acceso_ssh_reemplazado`, `acceso_ssh_aplicado`, `acceso_ssh_rechazado`, con autor y huella (nunca la clave).

## Flujos de estado

```
 pedido con clave ──aprobar──► asignación (acceso_ssh) ──materializar──► fila revision=1, aplicada=nulo
                                                                              │
              operación acceso_ssh (configure + probe, idempotente por revisión)
                                                                              ▼
                          confirmada ──► aplicada_revision = revision ──► servicio utilizable (si el resto también)
                          fallida/incierta ──► servicio NO utilizable, motivo visible, reintento = misma revisión

 reemplazo / alta tardía ──► revision += 1 ──► operación acceso_ssh ──► (igual que arriba)
 baja del servicio ──► la fila no se reutiliza; la huella solo queda en el historial
```

## Reglas de integridad

- Un servicio no puede tener dos operaciones `acceso_ssh` activas (se rechaza con 409 `operacion_en_curso`).
- Reemplazar mientras hay una operación activa no se admite: la persona espera a que termine.
- Solo servicios con `modelo_servicio = iaas` y `asignacion_snapshot.origen = proxmox_iaas` tienen fila; el resto responde 409 `servicio_no_linux`.
- La clave de un servicio dado de baja no se copia a otro: la fila pertenece al `servicio_id` y el runner además verifica identidad del invitado
  (`vmid`, nodo, `resource_uuid`, `nonce`) antes de escribir, de modo que una reutilización del `vmid` no recibe la clave anterior.
