# Contrato: runner `nap-console-identity/1`

Protocolo cerrado del nodo, mismo canal que `nap-iaas-access/1` (SSH con comando forzado, JSON por stdin, sólo biblioteca estándar). La contraseña viaja sólo por stdin y nunca en `argv`.

## Solicitud (campos comunes)

`protocol`, `operation_id` (UUID), `action`, `cluster_uuid`, `identidad` (`^nap-u[0-9]+@pve$`), `revision` (entero ≥ 1).

| `action` | Campos extra | Efecto |
|---|---|---|
| `ensure` | `password_consola` (`^[A-Za-z0-9_-]{32,128}$`), `pools` (lista de `catedra-N`, ≤ 200) | crea la identidad si no existe; fija la contraseña si es nueva o difiere de `password_consola`; deja el rol `NapConsola` **exactamente** sobre los pools indicados que existen y quita el resto; no concede ningún otro rol ni permiso |
| `retire` | `pools` (opcional) | con `pools`: quita el rol de esos pools; sin `pools`: quita todo y **elimina** la identidad |
| `end_sessions` | `vmids` (lista de enteros) | termina, **en este nodo**, los procesos de consola de esos contenedores (el portal la ejecuta en cada nodo) |
| `probe` | — | informa existencia y permisos efectivos de la identidad |

## Respuesta

`status` (`succeeded`/`failed`/`unconfirmed`), `phase`, `result` por acción:
`ensure` → `{ "pools_aplicados": […], "pools_pendientes": […], "creada": bool, "password": "aplicada|sin_cambios" }`; `retire` → `{ "retirada": bool, "pools_quitados": […] }`; `end_sessions` → `{ "terminadas": N }`; `probe` → `{ "existe": bool, "pools": […], "roles": ["NapConsola"] }`.

Nunca incluye contraseñas, hashes, tickets ni texto del sistema; los errores llevan sólo códigos (`INVALID_REQUEST`, `IDENTITY_MISMATCH`, `ROLE_UNAVAILABLE`, `PROBE_FAILED`, `UNCONFIRMED`, …).

## Garantías

- Rechaza `root@pam`, otros reinos, otros roles y nombres fuera del patrón.
- Idempotente por `(identidad, revision)`; un efecto posible sin confirmar queda `unconfirmed` y se reintenta con la misma contraseña.
- Se instala en el paquete de nodo (mapa de archivos de `install.py`); no toca ningún archivo del `policy_digest` del motor Docker.
