# Factibilidad Docker/LXC — T005

Fecha: 2026-10-26. Laboratorio local; no acredita el clúster universitario.

**Estado: creación, arranque y limpieza confirmados; la comprobación de confinamiento requiere repetición con vista del nodo. T005 continúa abierta.**

## Preparado y verificado sin Proxmox

- Prototipo root con identidad persistida antes de crear, VMID fijo exclusivo de laboratorio,
  comprobación de base/capacidad/dirección, creación detenida y aislamiento previo al arranque.
- Siete pruebas de orquestación aprobadas: orden firewall/arranque, replay terminal,
  respuesta perdida tras create, recurso ajeno, limpieza fallida y recuperación sin recreación.
- Compilación Python y sintaxis de reglas nftables aprobadas. Esta última se ejecutó con
  nftables 1.1.3 en un namespace Docker aislado, con NET_ADMIN sólo dentro de ese namespace;
  no se cambió el firewall de esta PC. El nodo debe repetir su propia comprobación.
- El manifiesto público whoami fijado por digest se pudo consultar. Esto no acredita pull
  desde el guest. El registry privado ya fue comprobado en el bootstrap T004.
- Lanzadores privados de ejecución y recuperación validados con `bash -n`, sin ejecutarlos
  como root desde el agente. Paquete y configuración sensible fuera del repositorio.
- Selección completa de `infra/laboratorio/011/tests`: **41 aprobadas** (incluye las siete
  anteriores, bootstrap, preflight, registry y diagnóstico). No son 41 pruebas en Proxmox.

## Primer intento real

El recibo del nodo devolvió `probe_failed`, fase `creating`, `resource_absent: true` y ningún
perfil habilitado. La consulta de sólo lectura de la tarea `vzcreate` del VMID 900011 mostró
un error de permisos al acceder a `/var/lib/lxc/900011/rootfs` durante la extracción de Ubuntu.
El propio log de PVE confirmó la retirada del volumen temporal. No se alcanzó la instalación
del runtime ni un pull; este fallo no acredita incompatibilidad de Docker con LXC.
El recibo filtrado está en [docker-primer-intento.json](docker-primer-intento.json).

El lanzador aplicaba umask 077 también al subproceso PVE. La creación de directorios que
debe recorrer el UID mapeado necesita los permisos habituales: el código de
[PVE::LXC mount_all](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm)
crea el rootdir sin un modo explícito, y la
[extracción](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC/Create.pm)
se ejecuta en el user namespace del invitado. La corrección limita umask 022 a los
subprocesos de creación/arranque; el proceso principal y los archivos privados siguen
con umask 077 y modos 0700/0600. Se reprodujo y verificó localmente con un subproceso real.
Su efectividad en PVE sigue pendiente del nuevo intento.

Antes de ese intento, `--retire-failed-run` exige el journal root del fallo anterior con
identidad, fase y ausencia confirmada, y vuelve a comprobar que no hay CT ni volúmenes.
Sólo permite `rmdir` de los directorios vacíos esperados y sin montajes; no cambia permisos
de directorios existentes ni borra contenido. Rechaza recursos vivos, enlaces y archivos.
El paquete anterior está respaldado fuera de Git y el nuevo intento tiene identidad distinta.

Verificación posterior: **44 pruebas aprobadas**, con `NAP_INFRA_INTEGRATION=1` y selección
`infra/laboratorio/011/tests`. Incluye diez pruebas del spike, entre ellas el subproceso local
de permisos y la recuperación de directorios vacíos. No se ejecutaron pruebas reales de PVE
mediante pytest. La sonda ahora registra filesystem, driver y versiones Docker/containerd/runc.

## Segundo intento real

La tarea PVE `vzcreate` terminó con `WARNINGS: 1`: Ubuntu se extrajo y el único aviso fue la
recomendación de nesting para systemd 255. La API mostró el VMID 900011 detenido, no privilegiado,
rootfs de 8 GB y la identidad del ensayo; Draw.io (VMID 100) seguía corriendo. No se arrancó el
invitado ni se instaló Docker. El recibo devolvió `cleanup_pending` en fase `creating`.

Se encontró un error del adaptador del prototipo: `pct config` aplica `encode_text` a description
([fuente de pct](https://github.com/proxmox/pve-container/blob/master/src/PVE/CLI/pct.pm)), mientras
el prototipo intentaba interpretar ese texto directamente como JSON. Al no reconocer su marcador,
rechazó tanto el avance como la eliminación. Se corrigió para leer la configuración JSON nativa
mediante pvesh. La prueba de regresión usa una descripción JSON con el salto de línea observado
y comprueba también el rechazo de una descripción dañada. No se modificó el control de pertenencia.

El paquete nuevo calcula la huella exacta del programa anterior desde su archivo respaldado.
Sólo el modo de limpieza permite aceptar explícitamente esa huella previa, junto al mismo
journal y marcador. La ejecución normal mantiene el rechazo de una petición cambiada.
El lanzador recupera primero el ensayo anterior y exige ausencia confirmada antes de crear
otro; si la limpieza falla se detiene. Ambas acciones requieren la terminal root del operador.
El recibo filtrado del segundo intento está en [docker-segundo-intento.json](docker-segundo-intento.json).

Verificación posterior: **47 pruebas locales aprobadas**, trece del spike; incluyen el adaptador
JSON y recuperación con huella anterior exacta, sin autorizar recreaciones ni recursos ajenos.
El paquete coincide con las fuentes y pasó el modo de plan sin cambios. La recuperación real
y la factibilidad de Docker permanecen pendientes; ningún perfil fue habilitado.

## Tercer intento real

El recibo confirmó `previous_probe_cleaned: true`: se recuperó el segundo intento, se creó y
arrancó otro LXC y se detuvo el ensayo en fase `probing` con `UNSAFE_APPARMOR`. La comprobación
ocurría antes de instalar Docker. La limpieza terminó con `resource_absent: true`; una consulta
posterior por API mostró únicamente Draw.io (VMID 100) corriendo, sin VMID 900011.
Ver [docker-tercer-intento.json](docker-tercer-intento.json).

La sonda anterior exigía que `/proc/1/attr/current`, leído desde el guest, comenzara por `lxc-`
y no contuviera `unconfined`. No guardó esa etiqueta, por lo que **no se puede concluir todavía**
si había una configuración insegura o una vista parcial del namespace. La documentación de
[AppArmor sobre stacking y namespaces](https://www.apparmor.net/advanced/AppArmorStacking/)
explica que una política externa puede quedar oculta desde el namespace interior. El
[código de LXC](https://github.com/lxc/lxc/blob/main/src/lxc/lsm/apparmor.c) genera el perfil
externo con el nombre del contenedor y apila el namespace interno cuando está disponible.

Se actualizó la comprobación para obtener el PID desde PVE y leer su etiqueta **desde el nodo**,
exigir el perfil exacto del VMID cargado en modo enforce, UID mapeado y filtro seccomp activo.
Revalida identidad/PID antes de aceptar la observación. La vista interior queda sólo como
diagnóstico seguro, con longitud/caracteres limitados. Un host sin perfil, con perfil ajeno o
modo complain sigue rechazado; no se agrega configuración unconfined ni un CT privilegiado.
Las comprobaciones posteriores del perfil de la aplicación Docker permanecen vigentes.

**57 pruebas locales aprobadas**, 23 del spike. Las nuevas cubren stacking con namespace
interior, host realmente unconfined, perfil ausente/ajeno/complain, PID cambiado y seccomp
desactivado. La API real confirmó que el status expone PID; el paquete pasó plan sin cambios
y coincide con las fuentes. Falta ejecutar la comprobación actualizada en el nodo.

## Resultado real requerido

Registrar el recibo seguro del nodo y comprobar: LXC no privilegiado; nesting/keyctl exactos;
AppArmor/seccomp activos; filesystem/runtime y versiones; pull público y privado con CA;
ausencia de authfile antes del arranque; dato persistente tras reiniciar; uso total dentro de
Medium; aislamiento de administración y otro guest con contadores externos; y ausencia del
CT/discos/reglas temporales al finalizar. No aceptar fallback privilegiado o unconfined.

El prototipo no crea una oferta del catálogo ni demuestra el acceso final HTTPS de NAP.
El paquete definitivo se valida otra vez en T050 antes de habilitar su perfil.
