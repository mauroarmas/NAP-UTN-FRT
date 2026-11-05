# Consola nativa: scripts de operación

Procedimiento completo y criterios en [`docs/runbook-consola-nativa.md`](../../../runbook-consola-nativa.md). Se ejecutan como `root` en un nodo Proxmox y **muestran un plan salvo `--aplicar`**.

| Script | Uso |
|---|---|
| `crear-rol-consola.sh` | Rol `NapConsola` con `VM.Console` y `VM.Audit` (rechaza otros privilegios). |
| `crear-identidad.sh --usuario <u>@<dominio> --pool catedra-<N> [--sin-clave]` | Identidad individual y ACL del rol sólo sobre el pool. La clave, por entrada estándar o con `pveum passwd`. |
| `retirar-acceso.sh --usuario <u>@<dominio> [--pool …] [--vmid …] [--fase acl\|identidad\|sesiones\|todas]` | Retiro por fases; la de sesiones va en **cada** nodo. |
| `verificar-login-consola.py` | Inicio de sesión REAL dentro del contenedor por el protocolo de consola: `usuario:archivo-de-clave` → `entra` o `rechazado` (feature 021). |
| `ensayo-revocacion.py` | Ensayo real (consolas abiertas, retiro, comprobaciones). Requiere `websockets`. Informe sin tickets. |

Copiar los `.sh` a `/root/nap-consola` en cada nodo (el ensayo los invoca por SSH). Del lado del portal: `../portal/consola.sh` (`sintetico`, `inventario`, `tramite`, `evidencia`, `confirmar`, `perfil`)
usa los mismos servicios que las pantallas de administración desde el contenedor `api`.
