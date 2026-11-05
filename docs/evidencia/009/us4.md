# US4 — Operaciones durables y recuperación

Estado: implementación y comprobaciones automatizadas T059–T070 completadas. **La infraestructura de estas pruebas es simulada**; no acreditan provisión, runner ni acceso desde otra computadora.

## Comportamiento implementado

- Órdenes con `Idempotency-Key`, respuesta 202, `Location`, consulta autorizada y restauración por listado/servicio al recargar. `restart` y `reboot` comparten la intención idempotente.
- Identidad global por clúster/VMID, UUID y nonce cifrado antes de crear. Configuración cerrada, LXC no privilegiado y sin sobrescritura de recursos; sin adopción por hostname, URL ni credenciales ficticias.
- Worker separado del API, lease/generación, comparación de propietario y sesiones PostgreSQL independientes. La API no inicia scheduler ni espera una tarea PVE.
- `dispatch_started` confirmado antes de enviar, UPID persistido al recibirlo y recuperación mediante identidad y lista de tareas. Un envío sin respuesta nunca habilita otro POST de creación automáticamente.
- Confirmación de tarea y recurso, y para creación/reparación además preparación y salud local. La operación puede terminar confirmada mientras aplicación y pedido esperan la evidencia de acceso de US6.
- Detención conserva CPU/RAM hasta tarea terminal y estado detenido. Eliminación detiene primero y exige ausencia global y ausencia de volúmenes identificables antes de liberar y retirar la identidad. Resultado desconocido conserva identidad/compromiso.
- Consulta externa fuera del event loop con pool real de cuatro threads, presupuesto de espera y timeout de transporte; cada cliente HTTP se crea/cierra dentro de su llamada. Vencer la espera no libera un thread que todavía trabaja ni cancela un efecto PVE.

## Resultados automatizados

| Ejecución | Resultado | Tiempo |
|---|---|---|
| Adaptador, identidad, recuperación, efectos, contratos, evaluación e inventario | 34 pasaron antes de agregar el caso de listado autorizado | 17,80 s |
| Revisión final de contratos/listado, recuperación e identidad | 15 pasaron, incluido el caso nuevo | 10,77 s |
| PostgreSQL: leases y migraciones fresh/upgrade | 8 pasaron | 5,78 s |
| PostgreSQL: worker, recuperación entre sesiones, VMID concurrente y HTTP durante envío lento | 4 pasaron | 5,06 s |
| Vitest frontend | 12 pasaron | 3,68 s |
| Playwright completo disponible: autenticación y operaciones | 5 pasaron | 9,1 s |
| Build frontend | correcto; 808,21 kB JS / 237,92 kB gzip | 694 ms |
| Lint frontend | sin errores; 16 advertencias existentes | — |

Casos comprobados: corte después del POST y antes del commit del UPID, respuesta perdida, tarea tardía, tarea fallida con recurso persistente, falta de historial de tarea, colisión con recurso ajeno, éxito fuera de cobertura, worker con lease vencido, cuatro reclamaciones concurrentes aunque `nextid` repita el candidato, detención/eliminación en fases y reparación sin segunda creación. La creación recuperada mantiene un único UUID y un solo recurso propio.

La consulta HTTP independiente responde mientras el POST simulado permanece bloqueado, con un límite de espera de prueba de 700 ms. Es una comprobación de aislamiento del event loop; **no sustituye la medición de navegador SC-008**.

Logs locales: `/tmp/nap009-us4-backend.txt`, `/tmp/nap009-us4-contract-final.txt`, `/tmp/nap009-worker-us4-postgres.txt`, `/tmp/nap009-worker-effects-postgres.txt`, `/tmp/nap009-us4-browser.txt` y `/tmp/nap009-frontend-us4-lint.txt`.

## Fuentes y límites

La recuperación consulta tareas por VMID/tipo/instante y distingue tarea terminal de recurso observado, siguiendo [la implementación oficial de Tasks](https://raw.githubusercontent.com/proxmox/pve-manager/master/PVE/API2/Tasks.pm). Para comprobar ausencia global se utiliza `GET /cluster/nextid?vmid=...`, cuya [implementación oficial](https://raw.githubusercontent.com/proxmox/pve-manager/master/PVE/API2/Cluster.pm) verifica explícitamente que el VMID está libre. Un listado filtrado por permisos o un error 500 de config no prueban ausencia. La creación usa los parámetros cerrados de [LXC](https://raw.githubusercontent.com/proxmox/pve-container/master/src/PVE/API2/LXC.pm).

El puerto `bootstrap_service.validar_preparacion/preparar` bloquea la creación real hasta implementar y validar definiciones, red y runner en US6. Las pruebas lo sustituyen explícitamente por un doble; no existe un bypass de producción por entorno de test.

Se verificó por separado, por pedido del usuario, conexión de solo lectura al Proxmox configurado: versión 9.2.2 y nodo online, ambos con HTTP 200. Eso no acredita permisos de creación, inventario completo, imágenes, consola ni aplicaciones. No se desplegaron recursos reales ni se aplicaron migraciones a una base operativa. Las comprobaciones reales siguen en T101/T102/T133.

La suite backend completa todavía necesita adaptar pruebas heredadas a los contratos nuevos, y permanece pendiente la expectativa obsoleta del límite fijo de disco (T134). El bundle se optimiza en US7. Los algoritmos completos de períodos/renovaciones y observación continúan en US5/US7; los jobs ya admiten operaciones durables y no liberan por el simple envío de stop.
