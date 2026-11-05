# Runbook: habilitar la consola nativa de Linux IaaS

Para quien administra el clúster Proxmox de la universidad. Habilita que una persona de cátedra abra la consola de **su** contenedor Linux desde el navegador,
con una cuenta individual de Proxmox, sin ampliar lo que puede hacer en la infraestructura. Es la única excepción a «Proxmox es el back-end» que admite la
constitución. Valores entre `<…>` son datos propios de su instalación; este documento no contiene datos de ningún laboratorio.

Los comandos de `scripts/consola/` se ejecutan como `root` en un nodo y **por omisión sólo muestran qué harían**; `--aplicar` ejecuta. Origen de la
validación y límites: [validación en el laboratorio](infraestructura-laboratorio/validacion-consola-2026-11-04.md).

## 0. Qué se necesita

| Dato | Para qué |
|---|---|
| Acceso `root` por SSH a **todos** los nodos | Crear roles/ACL, terminar sesiones en cada nodo |
| Un dominio de autenticación para las identidades (`pve` o el institucional) | Cuentas individuales; nunca `root@pam` ni cuentas compartidas |
| Un pool por cátedra (`catedra-<N>`), creado por NAP al desplegar | Alcance de los permisos |
| Un Linux IaaS encendido en **cada** nodo, de una cátedra de prueba | Ensayar la revocación y la apertura en cada nodo |
| Alcance de red desde el navegador de la persona a `<nodo>:8006` | La consola se abre en la interfaz web del nodo |
| Certificado confiable en cada nodo (o importar su CA en el navegador) | Sin él el navegador muestra advertencias y puede bloquear la consola |
| Cuenta de administración del portal | Registrar evidencia y confirmar el trámite |

## 1. Rol de sólo consola (una vez por clúster)

```bash
scripts/consola/crear-rol-consola.sh            # plan
scripts/consola/crear-rol-consola.sh --aplicar
```

El rol `NapConsola` tiene **sólo** `VM.Console` y `VM.Audit`. `VM.Audit` es indispensable: la página de consola lee el estado del contenedor antes de abrir la
terminal y sin él responde `403`. Es lectura sobre los contenedores del pool de la persona; el script rechaza cualquier otro privilegio. Comprobado:
detener, reiniciar, cambiar configuración, tomar snapshots y ver el estado del nodo dan `403`.

## 2. Una identidad por persona

```bash
scripts/consola/crear-identidad.sh --usuario <usuario>@<dominio> --pool catedra-<N> --sin-clave --aplicar
pveum passwd <usuario>@<dominio>       # la persona o el operador, en una terminal propia; nunca por argumentos ni chat
```

- Una identidad pertenece a **una** persona; no se reutiliza. `root@pam` está prohibida.
- Una persona con varias cátedras recibe una ACL por cada pool (volver a ejecutar el script con otro `--pool`).
- Nunca conceder el rol sobre `/`, `/vms` ni `/nodes`.
- Dominio `pve`: contraseña local en Proxmox. Dominio institucional: la persona usa sus credenciales y no se fija contraseña.

## 3. Inventario en el portal

Con el actor y la referencia institucional (acta o ticket):

```bash
python -m scripts.importar_identidades_consola --archivo <inventario.json> --actor <operador> --referencia <acta>
```

El JSON lleva `usuario_id`, `estado` (`asignada` o `sin_identidad`) e `identidad`. Ausencia de dato queda **desconocida**, no «sin acceso». No se reemplaza una
identidad asignada sin completar su revocación.

## 4. Ensayo real de revocación (obligatorio)

Con una identidad de prueba con dos pools y un contenedor encendido en cada uno:

```bash
python3 scripts/consola/ensayo-revocacion.py --nodos <ip-nodo-1> <ip-nodo-2> --usuario <identidad-prueba> \
    --clave-archivo <archivo-0600> --ct <nodo>:<vmid>:catedra-<N> --otro-ct <nodo>:<vmid>:catedra-<M> --informe <salida.json>
```

Requiere `pip install websockets` y los scripts copiados en `/root/nap-consola` de cada nodo. **Repetir entrando por cada nodo** (el proceso que sostiene la sesión
vive en el nodo de entrada, que puede no ser el del contenedor). Criterios de aprobación (los cuatro deben dar `ok`):

1. La sesión abierta del pool retirado termina dentro del plazo (≤ 15 s; en el laboratorio < 1,5 s).
2. Un ticket y una solicitud guardados antes del retiro son rechazados.
3. Una sesión nueva sobre el otro pool vigente sigue abriendo.
4. Con la identidad eliminada no hay login posible y sus consolas restantes terminan.

**Si algún punto falla, la consola permanece deshabilitada**: no cargar el perfil (paso 6) y documentar el diagnóstico. No suponer una función de terminación que no exista.

### Procedimiento de retiro de acceso (el que se ensaya)

`scripts/consola/retirar-acceso.sh` en fases; **la de sesiones se ejecuta en cada nodo**:

| Fase | Efecto | Por sí sola |
|---|---|---|
| `acl` | quita el rol del pool | impide sesiones **nuevas**; una consola abierta sigue viva |
| `identidad` | elimina la cuenta | invalida sus tickets de sesión |
| `sesiones --vmid <id>` | termina los procesos de consola de ese contenedor | corta la terminal abierta |

## 5. Evidencia y trámite

1. Solicitar el trámite de retiro de acceso de una cuenta de prueba (desde el portal, **Cambios de consola**).
2. Ejecutar el ensayo (paso 4) **después** de la solicitud; la evidencia debe ser posterior al trámite.
3. Registrar la evidencia `revocacion_consola` (`entorno: real`, `cluster_uuid`, `pve_version`) en **Registrar evidencia institucional** y confirmar el trámite por su UUID.

## 6. Habilitación de la instalación

En la configuración privada `console_access_profile` (contrato en `specs/020-habilitar-consola-nativa/contracts/console-profile.md`):

- `cluster_uuid` y `pve_version` iguales a los de la evidencia.
- `gate.evidencia_ref` y `gate.sha256` de la evidencia registrada.
- **`nodos`**: por nodo, `host` y `port` alcanzables **desde el navegador de la persona**. Todo nodo con contenedores debe figurar.
- `identities`: por identidad, `usuario_id`, `revision_admin`, `referencia_institucional` y `catedras` con su revisión vigente.

Recrear api y worker. Cambiar el clúster, la versión, la evidencia o una revisión (de la persona o de la cátedra) **cierra** la habilitación hasta repetir el trámite.

## 7. Verificación

1. La persona abre **Ver acceso → Consultar consola**. El portal le lleva primero a **iniciar sesión en Proxmox** en el mismo nodo (dominio de la identidad) y luego a abrir la consola. Sin
   sesión previa en ese nodo, la página de consola responde «401 no ticket»; la sesión dura unas 2 horas y es por nodo.
2. Dentro de la consola entra con el usuario del contenedor. En esta versión del servicio es `root` con el «acceso inicial» del portal; `nap` sólo entra por SSH con clave.
3. Repetir con un contenedor de **cada** nodo; con una cuenta de **otra** cátedra (debe rechazarse), con una persona sin identidad (mensaje claro) y tras cambiar una revisión (se cierra).

Errores frecuentes: `401 no ticket` → falta iniciar sesión en ese nodo; `403` al abrir → el rol no tiene `VM.Audit` o falta la ACL del pool; consola «no habilitada» → falta
el perfil, el nodo no figura en `nodos` o una revisión cambió.

## 8. Retirar a una persona

Iniciar el trámite de retiro desde el portal (bloquea primero), aplicar `retirar-acceso.sh` (`acl`, `identidad` si ya no le queda ningún pool, y `sesiones` en **cada** nodo para cada
contenedor afectado), probar que una consola abierta y un ticket guardado quedan inutilizados, registrar la evidencia y confirmar el trámite. Si falla, registrar el motivo: el trámite queda abierto y no se transfiere nada.
