# Factibilidad Docker/LXC — T005

Fecha: 2026-10-26. Laboratorio local; no acredita el clúster universitario.

**Estado: primer ensayo real fallido durante la creación; nuevo intento pendiente. T005 continúa abierta.**

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

## Resultado real requerido

Registrar el recibo seguro del nodo y comprobar: LXC no privilegiado; nesting/keyctl exactos;
AppArmor/seccomp activos; filesystem/runtime y versiones; pull público y privado con CA;
ausencia de authfile antes del arranque; dato persistente tras reiniciar; uso total dentro de
Medium; aislamiento de administración y otro guest con contadores externos; y ausencia del
CT/discos/reglas temporales al finalizar. No aceptar fallback privilegiado o unconfined.

El prototipo no crea una oferta del catálogo ni demuestra el acceso final HTTPS de NAP.
El paquete definitivo se valida otra vez en T050 antes de habilitar su perfil.
