# Preparación del laboratorio 011

Herramientas técnicas de una sola instalación. No forman parte del formulario del portal.
Los valores actuales corresponden a la VM local: **no copiarlos al clúster universitario**.

## Orden

1. Preflight de sólo lectura y candidatos pendientes (`preflight.py`, `candidatos.json`).
2. Bootstrap del controlador: registry TLS de ensayo, publicar campus-demo, cerrar escrituras.
3. Bootstrap root del nodo: verificar prerrequisitos/TLS/bases y dejar configuración pendiente.
4. Ensayos reales Docker/Core y paquetes definitivos según las tareas. Ningún paso anterior
   habilita perfiles o crea contenedores académicos.

## Controlador

Después de construir `nap011-campus-demo:acceptance`:

```bash
backend/venv/bin/python infra/laboratorio/011/preparar_entorno.py --controller
backend/venv/bin/python infra/laboratorio/011/preparar_entorno.py --controller --apply
```

El primer comando sólo describe el plan. La aplicación genera archivos privados en
`~/.local/share/nap011/`: CA propia, certificado, credenciales aleatorias, authfile y estado.
Nunca imprimir o incorporar esos archivos al repositorio. No cambia la CA de la PC, Docker
ni del portal. El registry escucha sólo en `172.16.36.1:5443`, con TLS y autenticación.
El contenedor corre con el UID del operador, sin capabilities, con rootfs de lectura y sin
logs persistentes; sólo monta su certificado/clave de servidor, htpasswd y datos propios.
No recibe la clave de la CA ni el authfile del publicador.

Las imágenes de Distribution y la herramienta de copia están fijadas por digest en
`registry_lab.py`. La copia usa un archivo Docker de la fixture, sin montar el socket Docker
en el contenedor de copia. Tras publicar se recrea el registry en sólo lectura, incluso ante
un fallo de copia. Se comprueban TLS, 401 sin autenticación, 200 con la cuenta de lectura,
HEAD del manifiesto y rechazo de escritura. Para agregar otra imagen se necesita mantenimiento
técnico explícito; no se ofrece una cuenta de escritura a NAP ni a las aplicaciones.

Configuración basada en las referencias de
[Distribution](https://distribution.github.io/distribution/about/configuration/) y
[despliegue del registry](https://distribution.github.io/distribution/about/deploying/).
No se usa HTTP inseguro, `--tls-verify=false` ni credenciales en argumentos.

## Nodo

El operador ejecuta el lanzador privado preparado para este laboratorio. Verifica hash del
paquete y hostkey SSH, pide la contraseña sólo en la terminal y transmite por stdin. Los cuatro
archivos se validan y extraen en un directorio root temporal, sin rutas libres/enlaces; se retiran
al finalizar. El secreto de lectura del registry se usa para comprobar conexión y **no se guarda
en el namespace del nodo**. La fuente privada del controlador se conserva para el futuro worker.

El instalador deja exclusivamente `/etc/nap/applications-011/`, con permisos privados:

- Candidatos pendientes con hashes realmente observados de las bases Ubuntu/Debian.
- CA pública del registry y referencia al endpoint; sin contraseña ni claves privadas.
- Inventario estable y política candidata de red para `.81–.88`, separada de rangos legacy.

Si falla la conexión, usar el lanzador privado de diagnóstico o `--diagnose` con el mismo
manifest/configuración. Este modo consulta TCP, TLS/autenticación e inventario sin aplicar ni
crear el namespace del nodo; no se combina con `--apply`. Devuelve códigos cerrados para timeout,
ruta, rechazo de certificado, autenticación y redirecciones, sin mensajes o cuerpos externos.
No repetir el instalador hasta conocer la causa; nunca omitir la verificación TLS.

La CA y el certificado incluyen identificadores SKI/AKI y usos de clave. Tanto controlador como
nodo usan verificación X.509 estricta. Una prueba TLS con BIO en memoria reproduce el intercambio
completo con esa política, sin red. Ver [SSL de Python](https://docs.python.org/3.13/library/ssl.html)
y [extensiones X.509](https://cryptography.io/en/latest/x509/reference/).

El modo de plan no crea archivos. Aplicar exige root y prerrequisitos comprobados; un archivo
existente distinto, enlace o permisos inseguros detiene el proceso antes de copiar. No sobrescribe
datos anteriores. Un fallo de escritura retira sólo archivos propios de ese intento. Repetir
con el mismo contenido conserva inodes; cambios de espacio libre no rompen la idempotencia.

La política candidata **no cambia puentes, firewall global, DNS, cuentas, SSH, pools ni invitados**.
Su aislamiento debe imponerse y comprobarse antes de arrancar los invitados de ensayo y luego
cada instancia. `preflight` sólo acredita inventario de nodo; no anuncia red, registry o perfiles
operativos por encontrar binarios. Las habilitaciones siguen dependiendo de los gates reales.

## Ensayo Docker (T005)

`spike_docker.py` usa únicamente el VMID de laboratorio `900011` y la primera dirección
candidata (`172.16.36.81`). Se detiene si están ocupados, no coincide el hash de la base o
falta capacidad. Guarda primero su identidad y crea un LXC **detenido y no privilegiado**.
Instala reglas nftables limitadas a ese veth antes de arrancar, con nesting/keyctl exactos;
no cambia políticas generales ni instala Docker en el host. Las reglas bloquean administración,
otros invitados y redes privadas, salvo DNS y el registry autorizados. La sintaxis se verifica
antes de crear el guest y los contadores del nodo deben confirmar los bloqueos ejercitados.
El uso de hooks bridge sigue la [documentación de nftables](https://wiki.nftables.org/wiki-nftables/index.php/Bridge_filtering).

`guest_docker_probe.py` comprueba pull público/privado, AppArmor/seccomp, persistencia tras
reinicio y uso de RAM/disco dentro de Medium. El secreto del registry llega sólo por stdin;
su authfile temporal se retira antes de arrancar la aplicación, que usa el digest observado.
La salida contiene únicamente resultados y medidas; no se retienen logs de Docker.
Las versiones candidatas se instalan en el guest, sin que esto constituya el perfil definitivo.

Al terminar se elimina sólo el CT con el marcador exacto del ensayo, se confirma ausencia de
sus volúmenes y se retira su tabla nftables. Una respuesta perdida no autoriza otro create.
El journal root permite `--apply --cleanup-only` con el mismo paquete e identidad para
recuperar una interrupción o limpieza pendiente; este modo nunca crea ni arranca invitados.
Si aparece un recurso ajeno, se conserva y el ensayo exige diagnóstico.

El operador usa `~/.local/share/nap011/ensayar-docker.sh`; sólo tras diagnosticar una limpieza
pendiente, `limpiar-ensayo-docker.sh`. Ambos verifican paquete y hostkey, transmiten siete
archivos regulares exactos a un directorio root temporal y retiran el secreto al salir.
El journal queda en `/var/lib/nap-lab011/`, sin credenciales. Los resultados se registran en
`docs/evidencia/011/factibilidad-docker.md`; el ensayo **no habilita perfiles**.

La creación y el arranque mediante pct usan umask 022 exclusivamente en esos subprocesos:
sus directorios deben poder recorrerse desde el user namespace. El proceso principal conserva
umask 077. Ante una extracción fallida y ausencia confirmada, `--retire-failed-run` admite
retirar sólo directorios vacíos identificados mediante el journal root anterior; exige otra
identidad para el nuevo intento. No cambia permisos de carpetas existentes ni elimina archivos.

## Pruebas sin nodo

```bash
backend/venv/bin/pytest -q -c infra/pytest.ini infra/laboratorio/011/tests
```

Cubren idempotencia, secretos fuera de recibos/archivos públicos, entradas maliciosas, fallo TLS,
colisiones con archivos existentes y rollback de disco. El laboratorio real y la infraestructura
universitaria se registran separadamente en `docs/evidencia/011/`.
