# Research: Habilitar la consola nativa de Linux IaaS

Estado del clúster al 2026-11-04 (lectura, sin cambios): `nap-lab`, 2 nodos (`frt` .90, `pve91` .91), Proxmox VE 9.2.2, dominios `pve` y `pam`, único usuario `root@pam`, **sin ACL**, pools `catedra-3` y `catedra-25` existentes y vacíos de usuarios. El rol `PVEVMUser` incluye `VM.Console` pero también permisos de gestión.

## R1. Rol de la identidad individual

- **Decisión**: crear un rol propio (`NapConsola`) con el mínimo que exige abrir la consola de un contenedor (`VM.Console` y `VM.Audit`; ver abajo). Asignarlo a cada identidad sobre `/pool/catedra-N`, nunca sobre `/`, `/vms` ni `/nodes`.
- **Razón**: `PVEVMUser` agrega permisos de energía y configuración; entregarlos abriría una vía para operar el contenedor fuera del portal y rompería el Principio I (FR-005, FR-006).
- **Alternativas**: `PVEVMUser` (descartada por exceso); `PVEAuditor` (no permite consola).
- **Resuelto en el ensayo con navegador (2026-11-04)**: `VM.Console` solo **no alcanza**: la página de consola lee `status/current` del contenedor y responde 403 sin `VM.Audit`. El mínimo es `VM.Console` + `VM.Audit`, ambos sobre el pool de la cátedra. Con eso la identidad **lee** estado, configuración y métricas de los contenedores de su pool y los nombres de nodo, pero recibe 403 al detener, reiniciar, cambiar configuración, tomar snapshots o ver el estado del nodo. No requiere `Sys.*`.

## R2. Dominio de las identidades

- **Decisión**: dominio `pve` propio de la instalación (usuarios `nombre@pve`), distinto de `root@pam`; el operador las crea. El importador ya rechaza `root@pam` y duplicados.
- **Razón**: no requiere LDAP en el lab; las contraseñas viven en Proxmox, no en el portal. Para la universidad el runbook admite un dominio institucional si existe.
- **Alternativas**: LDAP/AD de la universidad (mejor a largo plazo, fuera del alcance del lab); tokens de API (no sirven para el WebSocket de consola, por la constitución).

## R3. Revocación: qué retira de verdad una consola abierta

Es el riesgo central (FR-007, FR-008). El contrato de la 009 prohíbe suponer una API de terminación.

- **Hipótesis a probar**: (a) quitar la ACL del pool impide **sesiones nuevas** y nuevos tickets de consola; (b) eliminar la identidad invalida los tickets de sesión guardados; (c) una sesión de terminal **ya abierta** sigue viva hasta que se cierre el proceso intermedio del nodo, por lo que el procedimiento incluye terminarlo en el nodo que aloja el contenedor.
- **Decisión de diseño**: el procedimiento institucional es *quitar ACL → eliminar o deshabilitar la identidad cuando ya no tiene ningún pool → terminar los procesos de consola del contenedor afectado → comprobar*. El ensayo registra, por separado, el resultado observado de cada uno de los tres puntos de FR-007.
- **Cómo se ensaya**: un script abre una consola **real** (ticket de sesión de la identidad de prueba, solicitud de consola del contenedor y conexión WebSocket), aplica el retiro y comprueba: la conexión deja de transmitir, el ticket guardado es rechazado, el otro pool sigue abriendo consola.
- **Salida si falla**: documentar en el informe que la consola queda cerrada para la instalación (FR-008); no se carga `console_access_profile`.

## R4. Destino por nodo con failover (FR-016)

- **Hallazgo**: `GET /servicios/{id}/consola` arma la URL con el único `proxmox_host` (en el lab, frt). Si frt está apagado, los contenedores de pve91 quedan sin consola aunque estén sanos.
- **Hecho de Proxmox**: la interfaz web de cualquier nodo del clúster abre la consola de un contenedor de otro nodo (`node=` selecciona el destino; el nodo de entrada redirige internamente).
- **Decisión**: la clave `nodos` del `console_access_profile` declara, por nodo, la dirección y el puerto alcanzables **desde el navegador de la persona**. El servicio de destino: (1) usa el nodo que aloja el contenedor; (2) si no responde a un sondeo TCP breve, prueba los demás nodos del clúster; (3) si ninguno responde, devuelve 503 con mensaje claro, nunca un destino equivocado. En todos los casos el parámetro `node` es el del contenedor.
- **Razón**: separa la dirección de administración (SSH del runner) de la que usa la persona; evita un punto único de falla sin balanceador nuevo.
- **Alternativas**: virtual IP / balanceador delante de los nodos (más infraestructura, fuera de alcance); seguir con un host único (incumple FR-016); reutilizar `runner_nodes.host` (acopla dos redes distintas).

## R5. Rama de administración sin compuerta

- **Hallazgo**: en `consola_del_servicio` la rama `ADMIN` verifica la identidad de infraestructura pero **no llama** a `exigir_gate`; la compuerta sólo se aplica a los demás roles.
- **Decisión**: `exigir_gate` (habilitación de la instalación) se aplica a **todos** los roles; la concesión por cátedra (`profile.identities`) sigue siendo por persona y para administración se exige una identidad individual asignada sin restringir cátedra (se valida en el diseño del perfil).
- **Razón**: FR-001 exige consola cerrada para toda persona mientras no haya evidencia real; hoy administración la esquiva.
- **Riesgo**: cambia el comportamiento actual de ADMIN; se cubre con pruebas y se anota en el contrato.

## R6. Evidencia y clúster

- **Decisión**: `cluster_uuid` = el `cluster_id` del `infrastructure_profile` del lab (el generado para `nap-lab`; no se inventa uno nuevo); `pve_version` = `9.2.2`. La evidencia es `revocacion_consola` con `entorno: real`, contrastada por hash (`gate.sha256`), con trámite `completado`.
- **Razón**: son los campos que valida hoy `exigir_gate`; no requiere cambios de esquema.

## R7. Credenciales y certificados del lado de la persona

- **Hallazgo**: la persona inicia sesión en la interfaz de Proxmox con su cuenta; el navegador debe confiar en el certificado del nodo o aceptarlo.
- **Decisión**: el runbook cubre certificado confiable por nodo y alcance de red al puerto de la interfaz desde las redes de cátedra. El portal no almacena ni transmite esas contraseñas. 2FA de la cuenta de Proxmox queda como recomendación, no como requisito.

## R8. Datos del laboratorio fuera del repositorio

- **Decisión**: identidades, contraseñas y direcciones del lab viven en `~/.local/share/nap009/` (privado) y en la base; los scripts reciben todo por variables/argumentos y los ejemplos del runbook usan marcadores (`<usuario>@<dominio>`, `<nodo>`). Una comprobación automatizada (SC-006) busca IDs, tokens y direcciones del lab en archivos versionados.
