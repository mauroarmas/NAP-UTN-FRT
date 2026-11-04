# Contrato: consola de un servicio

`GET /servicios/{servicio_id}/consola` — usuario autenticado; sin cuerpo ni efectos sobre infraestructura.

## Orden de comprobaciones (cada una corta con su error)

1. Servicio vigente y pertenencia al portal (404/403).
2. Servicio `RUNNING` (409 `servicio_no_disponible`).
3. Vigencia activa (409 `servicio_no_disponible`).
4. Servicio con nodo y VMID (400 `sin_vmid`).
5. **Compuerta de instalación para todos los roles** (409 `consola_no_habilitada`): evidencia real vigente, clúster, versión, trámite completado.
6. Identidad de infraestructura del servicio confirmada (409 `identidad_no_confirmada`).
7. Personas no administradoras: identidad individual asignada y alcance de cátedra con revisión actual (409 `consola_no_habilitada`).
8. Resolución del destino (503 `consola_nodo_no_disponible`).

## Respuesta 200

```json
{ "url": "https://<nodo-alcanzable>:<puerto>/?console=lxc&xtermjs=1&vmid=<vmid>&node=<nodo-del-contenedor>",
  "login_url": "https://<nodo-alcanzable>:<puerto>/",
  "servicio_id": 45, "vmid": 100, "node": "frt" }
```

- `node` es siempre el nodo que aloja el contenedor; el host de `url` es el primer nodo alcanzable (el propio, y si no responde, otro del clúster).
- `login_url` es el inicio de sesión del **mismo** nodo que `url`: la página de consola no muestra login propio y usa la sesión que la persona ya tenga en ese nodo; sin ella responde «401 no ticket» (hallazgo del ensayo con navegador, 2026-11-04). La sesión dura unas 2 horas.
- No se devuelven tickets, cookies, contraseñas ni la identidad de la persona.

## Errores

| Estado | `codigo` | Mensaje para la persona |
|---|---|---|
| 409 | `servicio_no_disponible` | El servicio debe estar encendido y con vigencia para abrir la consola. |
| 409 | `consola_no_habilitada` | La consola todavía no está habilitada para tu cuenta. Pedíselo a administración. |
| 409 | `identidad_no_confirmada` | No se pudo confirmar la instancia de esta consola. Probá de nuevo en un momento. |
| 503 | `consola_nodo_no_disponible` | La consola no está disponible ahora. Probá de nuevo en unos minutos. |

La respuesta nunca incluye detalles de infraestructura (identidades, pools, direcciones de otros nodos).
