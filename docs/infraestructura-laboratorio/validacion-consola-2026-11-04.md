# Validación real de la consola nativa (spec 020) — 2026-11-04

Clúster `nap-lab` (frt y pve91), Proxmox VE 9.2.2. Ensayo ejecutado con `scripts/consola/ensayo-revocacion.py` contra
consolas **reales** (ticket de sesión, solicitud de consola y conexión WebSocket); no son dobles. Informes crudos en el scratchpad de la sesión
(sin tickets ni cookies). Esto acredita la revocación en **este** clúster y versión; no reemplaza repetirla en otra instalación.

## Configuración probada

- Rol propio `NapConsola` con **`VM.Console` y `VM.Audit`** (el ensayo de protocolo se hizo con sólo `VM.Console`; el navegador exigió `VM.Audit`, ver hallazgo 5); identidad individual en el dominio `pve` con ese rol sobre `/pool/catedra-3` y `/pool/catedra-25`.
- Con esa identidad: iniciar/detener y leer configuración de un contenedor → 403; almacenamiento y pools → listas vacías; estado de nodo → 403.
  Sólo ve nombres y huellas TLS de los nodos; ningún contenedor ni recurso.
- La consola se abrió **entrando por un nodo distinto del que aloja el contenedor** (API de frt, contenedor en pve91, y al revés).

## Resultado (FR-007)

| Prueba | Entrada frt → CT en pve91 | Entrada pve91 → CT en frt |
|---|---|---|
| 1. La sesión abierta del pool retirado termina | sí (< 1,5 s) | sí (< 1,5 s) |
| 2. Ticket/solicitud guardados son rechazados | sí (solicitud: 403) | sí (solicitud: 403) |
| 3. El otro pool sigue abriendo consola | sí | sí |
| 4. Retiro total (identidad eliminada) | sí (ticket: 401, login imposible) | sí (ticket: 401, login imposible) |

Resultado global: **aprobado** en ambos sentidos.

## Hallazgos que fijan el procedimiento

1. **Quitar sólo la ACL no basta.** Tras retirar el rol del pool, una solicitud nueva da 403 pero la sesión ya abierta **siguió transmitiendo**.
2. **La sesión la sostiene `termproxy` en el nodo por el que entró la persona**, que puede no ser el del contenedor (el proceso verifica el permiso sólo al conectar y
   abre un `ssh` al nodo del contenedor). Por eso las sesiones se terminan en **cada nodo** del clúster; terminar `termproxy` corta la sesión en menos de 1,5 s.
3. **Eliminar la identidad invalida sus tickets de sesión** (401) y su inicio de sesión; las consolas abiertas se terminan igual con el paso de sesiones.
4. Las sesiones de consola no dejan procesos de `termproxy` tras el corte; el servicio `dtach` del contenedor persiste, como es normal en la consola de Proxmox.

5. **La página de consola necesita `VM.Audit`**: lee el estado del contenedor antes de abrir la terminal y con sólo `VM.Console` responde 403. Además exige que el navegador tenga una **sesión de Proxmox en ese nodo** (sin ella, «401 no ticket»); el portal lleva primero al inicio de sesión del mismo nodo (`login_url`). Con `VM.Console`+`VM.Audit` se comprobó 403 en detener, reiniciar, cambiar configuración, snapshots y estado de nodo.

## Pendiente (no acreditado por este ensayo)

- Sin 2FA en la identidad de ensayo; sin probar un dominio institucional (LDAP/AD).
- No se probó un navegador real con la interfaz de Proxmox, sólo el protocolo de consola (se verifica en T022).
- Ensayo con un único usuario de prueba; la instalación de la universidad debe repetirlo con su procedimiento.
