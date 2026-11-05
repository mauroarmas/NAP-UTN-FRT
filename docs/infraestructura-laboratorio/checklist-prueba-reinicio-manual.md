# Checklist: prueba manual de reinicio de un nodo (desde el portal)

Prueba de que, tras reiniciar `pve91`, el aislamiento nftables de una instancia se restaura
antes de que arranque ningún invitado. Contexto y resultados previos: ver la sección
"Reinicio de un nodo" de `validacion-motor-0510c1a-2026-11-02.md`.

## 1. Encender el laboratorio

- [ ] VMs en orden, esperando ~2 min al final:
  ```
  VBoxManage startvm TrueNAS --type headless
  VBoxManage startvm nap1 --type headless    # frt
  VBoxManage startvm nap2 --type headless    # pve91
  ```
- [ ] Si pve91 vuelve sin quórum: `pvecm expected 1` en el nodo (se pierde al reiniciar).
- [ ] Portal:
  ```
  cd ~/Escritorio/NAP-UTN-FRT; D=~/.local/share/nap009
  docker compose -p nap-handoff -f docker-compose.handoff.yml \
    -f $D/compose-api-lab.yml -f $D/compose-api-011.yml up -d
  ```
- [ ] Portal responde en http://127.0.0.1:5174
- [ ] (Solo apps web) `... start application_gateway`. Para MariaDB no hace falta.

## 2. Código y perfil correctos

- [ ] Rama `016-restaurar-aislamiento-al-arrancar` (todavía sin PR).
- [ ] Perfil `docker-ubuntu24:9` habilitado en frt y pve91 (`policy_digest` `f269ca1e…`).
- [ ] Si hubo `pull` o cambios: `up -d --force-recreate api worker`. Si cambió el
      `policy_digest`: perfil nuevo + gate real en cada nodo.

## 3. Accesos

- [ ] Maestro SSH a pve91 (lo abre Ivan con `!`; reabrir después del reboot):
  ```
  ! ssh -o ControlMaster=yes -o ControlPath=/tmp/nap-lab-ssh-%h -o ControlPersist=4h -Nf root@192.168.100.91
  ```
- [ ] Usuario del portal que pueda pedir e iniciar servicios (`ivan`, CATEDRA_ADMIN; tener el autenticador 2FA a mano).

## 4. Instancia MariaDB en pve91

Todo desde `docs/infraestructura-laboratorio/scripts/portal/` (los scripts usan los mismos servicios del backend que el portal;
requieren el contenedor `api` arriba). Si preferís la interfaz web, el pedido se hace igual desde http://127.0.0.1:5174 con la
cuenta `ivan`, pero revelar las credenciales es más simple con el script.

- [ ] Ver cuenta/cátedra con la que pedir (`docente@example.edu`, cátedra 3 en el ejemplo del README) y que no haya operaciones abiertas:
  ```
  ./consulta-sql.sh "select id||' '||estado||'/'||disponibilidad_aplicacion from servicios order by id desc limit 5"
  ```
- [ ] Encender la cuenta semilla (solo si usás el script, con tu permiso): `./portal.sh cuenta --activar` (al final: `--desactivar`).
- [ ] Publicar la oferta si cambió el perfil (ya se republicó con el perfil 9; repetir solo si falta):
  `./portal.sh oferta --clave oferta-rev9-reinicio`
- [ ] Revisar capacidad en pve91 (Medium: 2 vCPU / 1024 MB / 8 GB; pve91 solo aloja un Medium).
- [ ] Pedir la instancia en **pve91**:
  `./portal.sh pedido --usuario docente@example.edu --catedra 3 --nodo pve91 --clave reinicio-a`
- [ ] Esperar `ACTIVO` + `RUNNING / utilizable` (primer arranque 2–3 min; repetir la consulta SQL de arriba). Anotar el **número de servicio** (N).
- [ ] Revelar el acceso (queda en un archivo 0600, no imprime la contraseña):
  `./portal.sh revelar --servicio N --usuario docente@example.edu --salida /tmp/acceso-reinicio.json`
- [ ] Escribir el dato de prueba (verifica la CA y TLS):
  `python3 acceso_mariadb.py escribir /tmp/acceso-reinicio.json /tmp/marca-reinicio.txt`
  (necesita `pymysql`; el cliente tiene que estar en un equipo permitido, ver abajo.)
- [ ] Probar desde la **notebook** (192.168.100.185, Docker): copiar `acceso-reinicio.json` y conectar con
  `docker run --rm mariadb:11.4 mariadb --ssl-ca=<ca> --ssl-verify-server-cert -h <ip> -u <usuario> -p ...`
  (host, puerto, usuario y CA salen del JSON revelado). Tiene que conectar con TLS verificado.
  La PC (192.168.100.89) también está permitida; los nodos .90–.94 no.
- [ ] Anotar el estado previo en pve91 (por el maestro SSH): `nft list tables` → debe haber una `nap011_*`; `pct list` → el CT de la instancia `running`.

## 5. Reinicio

- [ ] `systemctl reboot` en pve91 (vuelve en ~75 s).
- [ ] Reabrir el maestro SSH.
- [ ] `journalctl -u nap-isolation-restore`: la instancia en `restaurados`, `fallidos` vacío.
- [ ] `nft list tables`: la tabla `nap011_*` existe **con el LXC aún detenido**.
- [ ] `pve-guests` arrancó después de la unidad (comparar horas en el journal).
- [ ] Portal: pasa a `stopped` a los ~2 min (mientras el nodo cae muestra un `RUNNING` falso: esperable).

## 6. Iniciar y verificar

- [ ] **Iniciar** desde el portal (confirma en ~10 s).
- [ ] Nodos `.90` y `.91` **bloqueados** al 3306.
- [ ] Notebook conecta con TLS.
- [ ] El dato escrito antes del reinicio sigue ahí.

## 7. Limpieza

- [ ] Dar de baja el servicio desde el portal y esperar la confirmación.
- [ ] Sin tablas `nap011_*` ni invitados de prueba en pve91.

## No esperar / no hacer

- Las instancias **no arrancan solas** tras el reinicio: hay que iniciarlas por el portal (`onboot` descartado a propósito).
- No se probó corte brusco ni caída de ambos nodos.
- No agregar reglas nftables a mano a una instancia viva: la baja queda `incierta`.
- No usar los nodos (.90–.94) como cliente: están excluidos de `client_cidrs`.
