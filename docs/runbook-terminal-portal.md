# Runbook: terminal web de la consola dentro del portal

Para quien administra el clúster Proxmox y el portal NAP de la universidad. Con esta feature la persona abre una terminal de su Linux **dentro del portal**, sin ver Proxmox, sin
ruta de red hacia los nodos y sin credenciales de infraestructura. El portal abre la consola del contenedor por detrás con la **identidad individual** de la persona y se la muestra
en una terminal web. Valores entre `<…>` son datos propios de su instalación; este documento no contiene datos de ningún laboratorio.

Relacionado: [consola nativa (020)](runbook-consola-nativa.md) · [validación en el laboratorio](infraestructura-laboratorio/validacion-consola-2026-11-04.md) · scripts en `docs/infraestructura-laboratorio/scripts/consola/`.

## 1. Cómo funciona (en una página)

1. **Identidades automáticas.** Un reconciliador del worker calcula, para cada persona, a qué cátedras pertenece (administración: a todas las activas) y mantiene en el clúster una identidad
   individual `nap-u<id>@pve` con el rol `NapConsola` (`VM.Console` + `VM.Audit`) **sólo** sobre los pools `catedra-<N>` de esas cátedras. La contraseña es aleatoria, se guarda cifrada y nadie la ve.
2. **Terminal.** `GET /servicios/{id}/terminal` (WebSocket del portal) verifica en el portal que el servicio es de la persona, que está encendido y vigente y que su identidad está `lista`;
   entonces inicia sesión con la identidad, pide la consola del contenedor y reenvía los bytes. Nada de lo que se teclea o se ve se guarda ni se audita.
3. **Retiro.** Quitar a una persona de una cátedra (o desactivarla) hace que el reconciliador retire el permiso, **termine las sesiones en cada nodo** y, si hay un trámite de la feature 009,
   registre la evidencia observada y lo complete. La terminal abierta se corta en segundos.
4. La habilitación de la instalación **sigue exigiendo** la evidencia real de revocación de la feature 020 (`console_access_profile.gate`). Sin ella, la terminal permanece cerrada para todos.

## 2. Requisitos

| Requisito | Detalle |
|---|---|
| Red **portal → nodos** | El portal (no la persona) alcanza `<nodo>:8006`. Las personas sólo necesitan llegar al portal. |
| Certificado verificable por nodo | El portal **verifica** el certificado de cada nodo contra la CA del clúster (`terminal_ca_file`) y por el nombre con el que lo alcanza. El certificado debe incluir ese nombre (o IP) en su `subjectAltName`. Si un certificado trae un nombre viejo, regenerarlo (`pvecm updatecerts --force`) o usar el nombre correcto. |
| `RUNNER_NODES` exacto | Debe listar **exactamente** los nodos vivos del clúster. Terminar sesiones se ejecuta en cada uno: un nodo configurado que ya no existe impide completar los retiros (falla cerrado). |
| Paquete de nodo | Con el protocolo `nap-console-identity/1`, instalado en **todos** los nodos **antes** que el portal. No cambia el `policy_digest` del motor Docker. |
| Rol `NapConsola` | Creado con `scripts/consola/crear-rol-consola.sh` (sólo `VM.Console` y `VM.Audit`); el runner rechaza cualquier otro. |
| Dominio de autenticación `pve` | Las identidades son `nap-u<id>@pve`; el dominio es de todo el clúster (crear en un nodo la deja en todos). |

## 3. Configuración privada

En `console_access_profile` (contrato en `specs/020-habilitar-consola-nativa/contracts/console-profile.md`):

- `cluster_uuid`, `pve_version`, `gate` (evidencia real de revocación): como en la feature 020.
- `nodos`: por nodo, `host`/`port` (la dirección del **navegador**, sólo para el respaldo de administración) y **`portal_host`** (la dirección **del portal** al nodo, con la que se verifica el certificado).
- **`identities` ya no se usa**: la identidad y su alcance viven en la base (`identidades_consola`).

Además: `terminal_ca_file` (ruta a la CA del clúster, `/etc/pve/pve-root-ca.pem` del nodo) y, opcionales, `terminal_inactividad_segundos` (por omisión 900), `terminal_max_sesiones` (3) y
`terminal_max_mensaje_bytes` (65536). Sin `terminal_ca_file` y con `proxmox_verify_ssl` falso, el portal **no verifica** los nodos (sólo para desarrollo).

## 4. Instalación (orden)

1. Rol `NapConsola` y paquete de nodo (`git archive` → `install.py --source-root` en modo plan → `infra/runner/install.sh`) en **todos** los nodos.
2. Migración del portal (`alembic upgrade head`; agrega `identidades_consola` y `sesiones_terminal`), con respaldo previo de la base.
3. Configuración privada (sección 3) y recrear `api` y `worker`.
4. El worker empieza a crear las identidades de las personas con cátedras. Administración las ve en **Identidades de consola** (estados Lista / En preparación / Con error / Retirada; reintento para los errores).

## 5. Verificación

- `scripts/consola/verificar-terminal-portal.py`: abre la terminal **hablando sólo con el portal** (como un navegador), inicia sesión en el contenedor y ejecuta comandos; con `--sin-cookie` comprueba el rechazo sin sesión y con otro `--origen` el rechazo por origen.
- Repetir con un contenedor de **cada** nodo. Comprobar el corte: retirar a la persona de la cátedra con una terminal abierta (debe cortarse en pocos segundos), que no pueda reabrir y que su identidad pase a `Retirada` y desaparezca del clúster.
- Buscar la contraseña de las identidades y un texto tecleado en registros del portal, base, nodos y contenedor: no deben aparecer.

## 6. Operación y límites

- **Inactividad**: se mide por la **entrada de la persona** (la salida de un comando largo no mantiene viva la sesión); se avisa 1 minuto antes de cerrar.
- **Cupo**: máximo de terminales simultáneas por persona; las sesiones huérfanas liberan su cupo. Administración puede ver y cerrar sesiones (`/admin/sesiones-terminal`), sin contenido.
- **Reinicio del portal**: corta las terminales (se cierran sus filas al arrancar). Hoy hay un único proceso de API; con varios habría que acotar ese cierre.
- **La consola de la infraestructura es persistente**: el shell iniciado **queda abierto** aunque la persona cierre la terminal, y quien abra después la consola de ese contenedor lo encuentra
  iniciado. Indicar a las personas que escriban `exit` antes de cerrar la terminal.
- **Primera apertura**: la infraestructura a veces corta la primera apertura de una consola; el portal la reintenta una vez sin avisar.

## 7. Adopción de identidades creadas a mano

Al reconciliar, una persona con identidad manual recibe la gestionada y el inventario conserva la anterior en su historial. **El portal no elimina la manual** (el protocolo del nodo sólo
conoce `nap-u<id>@pve`, por diseño): la elimina el operador con `scripts/consola/retirar-acceso.sh --usuario <identidad> --fase identidad --aplicar` una vez comprobado que la terminal funciona.

## 8. Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| «Todavía no está habilitada» | Identidad no `lista` (ver pantalla de administración), cátedra sin pool todavía, o falta la evidencia real de la 020. |
| La terminal abre y se cierra enseguida | La infraestructura cortó la apertura (el portal ya reintentó una vez) o el nodo del contenedor no responde. |
| Un retiro queda «Con error» / no completa | Un nodo de `RUNNER_NODES` no responde o ya no existe; corregir la lista y reintentar. |
| `consola_nodo_no_disponible` | Ningún nodo es alcanzable por el portal, o el certificado no se verifica (revisar `portal_host` y `terminal_ca_file`). |
| La persona ve un shell ya iniciado | La consola es persistente: otra apertura previa no cerró su sesión (`exit`). |
