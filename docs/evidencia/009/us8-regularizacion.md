# Regularización administrativa del legado — T125

Comprobación del 2026-10-21 en entornos aislados. No se modificó la base operativa ni se ejecutaron acciones sobre Proxmox real.

Desde Servicios, administración puede revisar registros LXC pendientes. La evaluación explícita consulta inventario y configuración: exige identidad ya ligada al servicio, UUID/nonce/pool/clúster propios, nodo/VMID coherentes, contenedor sin privilegios y cantidades/volumen comprobados. No adopta por nombre o VMID ni inventa hashes de definición o bundle. Los GET comunes conservan consultas exclusivamente a la base de datos.

La confirmación requiere fechas completas y respaldo/motivo; las desconocidas aparecen vacías. Conserva los períodos aprobados y las decisiones publicadas. Guarda snapshot histórico parcial, compromiso único, período cuando falta y bitácora/historia con actor. El acceso queda no verificado. Un recurso detenido comprobado puede liberar cómputo; el disco se conserva. Si sigue encendido fuera de cobertura, retiene cómputo y admite una pausa pendiente, cuyo efecto deberá confirmar el worker.

Los registros duplicados se archivan por decisión explícita únicamente cuando el principal de la misma cátedra tiene propiedad comprobada y el duplicado no tiene identidad, compromiso ni operaciones abiertas. Se conserva el recurso y la historia. Conflictos entre cátedras, falta de prueba de propiedad y datos de versiones publicadas permanecen pendientes de su procedimiento institucional. No hay SQL manual ni edición libre de identidad desde el portal.

La confirmación reevalúa propiedad/cantidades, compara huella de datos y serializa mediante el bloqueo común de capacidad y filas. Los reinicios y nuevos inicios con compromiso o identidad inciertos se rechazan; una pausa conservadora sigue su protocolo de confirmación. Los reintentos conservan clave idempotente. Una decisión concurrente que cambió los datos exige reevaluar.

Resultados:

- 27 pruebas focalizadas de backend aprobadas, 17,16 s: regularización, backfill, admisión de inicio y proyecciones de vigencia. Incluyen permisos, repetición, propiedad alterada, cantidades distintas, fechas aprobadas, pausa futura y duplicados no verificables.
- Dos pruebas de concurrencia PostgreSQL real aprobadas, 3,40 s: dos sesiones de regularización producen una decisión y un conflicto, sin duplicar período/bitácora; se conserva el ensayo concurrente del backfill.
- Cuatro pruebas Vitest aprobadas, 2,71 s: fechas vacías, permisos docentes, doble envío, cierre bloqueado, errores sin pérdida de datos y selección explícita del principal. Después se preservó el selector de principal mientras carga su evaluación; la prueba de navegador verifica el código compilado posterior.
- Dos pruebas Chromium aprobadas, 5,30 s: teclado, doble Enter, Escape durante escritura, los dos controles de cierre deshabilitados, retorno de foco y exclusión de gestión docente. Primera ejecución: un fallo de selector ambiguo entre ambos botones Cerrar; corregido el test y repetido. API simulada y red externa bloqueada, sin atribuir este ensayo a Proxmox real.
- Compilación de producción correcta y lint sin errores; advertencias existentes sobre Fast Refresh y dependencias useMemo.

Estas comprobaciones no cierran el ensayo con el responsable de cátedra, T101/T102 reales ni la migración definitiva/restore de las tareas siguientes.
