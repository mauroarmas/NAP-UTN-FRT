# Operar el portal del laboratorio sin navegador

Herramientas para el laboratorio frt/pve91 + TrueNAS. Usan los **mismos servicios del backend** que los endpoints
(misma autorización, misma capacidad, mismas claves de idempotencia); no sustituyen la prueba de inicio de sesión de una persona.

| Archivo | Dónde corre | Para qué |
|---|---|---|
| `portal.sh` + `portal_ops.py` | PC → contenedor `api` | `cuenta`, `oferta`, `pedido`, `orden`, `reparar`, `revelar`, `capacidad`, `catedra-sintetica` |
| `consulta-sql.sh` | PC → contenedor `db` | Consultas de **lectura** al Postgres del portal |
| `acceso_mariadb.py` | PC (necesita `pymysql`) | Escribir y recuperar una fila con el acceso revelado, verificando la CA |
| `aislamiento_catedras.py` | PC (necesita `pymysql`) | Credenciales cruzadas y datos entre dos instancias de cátedras distintas |
| `sondear-red.sh` + `sondeo_red.py` | PC → LXC de un nodo | Qué alcanza una instancia hacia afuera |

Las claves de idempotencia son obligatorias: repetir un comando con la **misma** clave devuelve el mismo resultado; con otra
clave sobre el mismo contenido, no. Nada imprime contraseñas; `revelar` las guarda en un archivo de modo 0600 y hay que borrarlo al terminar.

## Cuentas

Las decisiones de administración se atribuyen a la cuenta semilla `admin@utn.frt.edu.ar` (`NAP_ADMIN_EMAIL` la cambia). Está **inactiva
por defecto**. `cuenta --activar` la enciende para operar y `cuenta --desactivar` la devuelve a su estado; sólo acepta esa cuenta y las
que terminan en `@lab.invalid`, nunca la cuenta de otra persona. Hágalo con permiso del responsable del laboratorio.

## Ciclo completo (ejemplo)

```bash
cd docs/infraestructura-laboratorio/scripts/portal
./portal.sh cuenta --activar
./portal.sh oferta --clave oferta-rev7                              # al cambiar el perfil vigente
./portal.sh pedido --usuario docente@example.edu --catedra 3 --nodo pve91 --clave demo-a
./consulta-sql.sh "select id||' '||estado||'/'||disponibilidad_aplicacion from servicios order by id desc limit 3"
./portal.sh revelar --servicio 30 --usuario docente@example.edu --salida /tmp/acceso-a.json
python3 acceso_mariadb.py escribir /tmp/acceso-a.json /tmp/marca-a.txt
./portal.sh orden --servicio 30 --accion detener --usuario docente@example.edu --clave demo-a-detener
./portal.sh orden --servicio 30 --accion iniciar --usuario docente@example.edu --clave demo-a-iniciar
python3 acceso_mariadb.py leer /tmp/acceso-a.json /tmp/marca-a.txt
./portal.sh orden --servicio 30 --accion eliminar --usuario admin@utn.frt.edu.ar --clave demo-a-baja
rm -f /tmp/acceso-a.json /tmp/marca-a.txt
./portal.sh cuenta --desactivar
```

Reparar un despliegue fallido (pedido en `ERROR`, intento anterior `fallido`): `./portal.sh reparar --pedido 49 --clave reparar-49`.
Sólo procede con el mismo perfil habilitado en el nodo; si cambió, el portal lo rechaza y la salida es la baja y un pedido nuevo.

## Dos cátedras a la vez

```bash
./portal.sh catedra-sintetica --accion crear           # usuario y cátedra sintéticos (@lab.invalid)
./portal.sh pedido --usuario docente@example.edu --catedra 3  --nodo pve91 --clave aislamiento-a
./portal.sh pedido --usuario lab-aislamiento-b@lab.invalid --catedra <id> --nodo frt --clave aislamiento-b
./portal.sh revelar --servicio <A> --usuario docente@example.edu --salida /tmp/a.json
./portal.sh revelar --servicio <B> --usuario lab-aislamiento-b@lab.invalid --salida /tmp/b.json
./portal.sh revelar --servicio <B> --usuario docente@example.edu --salida /tmp/x.json     # debe dar DENEGADO (403)
python3 aislamiento_catedras.py /tmp/a.json /tmp/b.json
./sondear-red.sh 192.168.100.91 102 instancia_B,192.168.100.105,3306 pve91_ssh,192.168.100.91,22 dns,192.168.100.1,53
./portal.sh catedra-sintetica --accion retirar
```

Antes de pedir dos instancias hay que mirar la capacidad (`./portal.sh capacidad --pedido <id> --nodo <nodo>`): en el laboratorio el
almacenamiento compartido llegó a no alcanzar para la segunda y se amplió el TrueNAS. Resultados de la prueba:
[validacion-motor-0510c1a-2026-11-02.md](../../validacion-motor-0510c1a-2026-11-02.md).

## Límites

- Sólo MariaDB 11.4 (Medium); el pedido fija 2 vCPU, 1024 MB y 8 GB.
- `portal_ops.py` importa el backend: corre únicamente dentro del contenedor `api` y necesita que ese contenedor tenga el código actual
  (recrear api y worker tras cada actualización del repositorio).
- No hay llamadas a Proxmox directas: todo pasa por el portal.
