# Factibilidad Docker/LXC — T005

Fecha: 2026-10-26. Laboratorio local; no acredita el clúster universitario.

**Estado: ensayo real pendiente. T005 continúa abierta.**

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

## Resultado real requerido

Registrar el recibo seguro del nodo y comprobar: LXC no privilegiado; nesting/keyctl exactos;
AppArmor/seccomp activos; filesystem/runtime y versiones; pull público y privado con CA;
ausencia de authfile antes del arranque; dato persistente tras reiniciar; uso total dentro de
Medium; aislamiento de administración y otro guest con contadores externos; y ausencia del
CT/discos/reglas temporales al finalizar. No aceptar fallback privilegiado o unconfined.

El prototipo no crea una oferta del catálogo ni demuestra el acceso final HTTPS de NAP.
El paquete definitivo se valida otra vez en T050 antes de habilitar su perfil.
