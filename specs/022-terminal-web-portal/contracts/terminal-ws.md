# Contrato: terminal web del portal

`GET /servicios/{servicio_id}/terminal` (upgrade a WebSocket). Sin cuerpo.

## Admisión (antes de tocar la infraestructura; cada falla cierra con su código)

1. Sesión del portal válida y `Origin` permitido (sino 403 antes de aceptar).
2. Servicio vigente y perteneciente a la cátedra de la persona (o administración) → 4403 `sin_permisos`.
3. Servicio encendido y con vigencia → 4409 `servicio_no_disponible`.
4. Compuerta de instalación de la 020 (evidencia real, clúster, versión, nodos) → 4409 `consola_no_habilitada`.
5. Identidad de infraestructura del servicio confirmada → 4409 `identidad_no_confirmada`.
6. Identidad de consola de la persona `lista` y cubriendo la cátedra → 4409 `consola_no_habilitada`.
7. Cupo de sesiones de la persona → 4429 `limite_sesiones`.
8. Resolución del nodo con failover (020) → 4503 `consola_nodo_no_disponible`.

Los mensajes al navegador son texto llano en español, sin direcciones, identidades ni nombres de nodo.

## Mensajes

| Dirección | Tipo | Contenido |
|---|---|---|
| navegador → portal | binario | bytes de teclado/pegado (≤ 64 KiB por mensaje) |
| navegador → portal | texto JSON | `{"t":"resize","cols":N,"rows":N}` (1..500); `{"t":"cerrar"}` |
| portal → navegador | binario | bytes de salida de la terminal |
| portal → navegador | texto JSON | `{"t":"estado","e":"abierta"}`; `{"t":"aviso","mensaje":"…"}`; `{"t":"cierre","motivo":"inactividad\|retiro\|baja\|detencion\|cuenta\|persona\|limite\|error","mensaje":"…"}` |

## Reglas

- Una sesión = un servicio; no hay reanudación: al cortarse, la persona abre otra.
- Inactividad (por entrada de la persona), cupo y cierre inmediato como en el spec; el portal avisa antes de cerrar por inactividad.
- La primera apertura que falle por la intermitencia de la consola se reintenta una vez sin avisar.
- Ningún mensaje, registro ni auditoría guarda los bytes de la terminal.

## Códigos de cierre

`1000` normal · `4403`/`4409`/`4429`/`4503` admisión (arriba) · `4408` inactividad · `4410` retiro/baja/detención/cuenta.
