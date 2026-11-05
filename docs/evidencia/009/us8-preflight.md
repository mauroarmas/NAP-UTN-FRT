# US8 — comprobaciones previas

`backend/scripts/preflight.py` genera un informe con códigos, mensajes y referencias de registros. No imprime configuración, URLs de conexión, tokens, contraseñas, claves, contenido cifrado ni resultados de descifrado. No ejecuta migraciones, seeds ni cambios en invitados.

- Sin argumentos inspecciona configuración y CA pública local: entorno/debug, JWT/CSRF/keyring independientes, origen HTTPS accesible desde el visitante, proxies delimitados, PostgreSQL, identidad/token/CA PVE, márgenes/destinos y SMTP.
- `--datos` inspecciona en transacción PostgreSQL READ ONLY el esquema actual o legado, VMID duplicados incluso con ceros iniciales, cantidades, fechas, pertenencia, snapshots, factores incompletos y despliegues heredados inciertos. Comprueba descifrado con contexto sin devolver secretos. Las ofertas publicadas/retiradas se contrastan con manifiesto, evidencia canónica, archivos/digests, clúster, red y destino del runner sin ejecutar SSH ni tomar bloqueos de escritura.
- `--datos --inventario` agrega un sondeo PVE explícito y acotado, sólo con configuración apta. Valida inventario y marcas de identidad; fallo o ausencia no modifica registros ni libera capacidad. No adopta por nombre, nodo o VMID.

La aptitud es la del alcance inspeccionado. Los problemas heredados necesitan decisiones de regularización/reconciliación; no se resuelven activando la aplicación ni editando resultados del informe. El modo de restauración y su habilitación son tareas separadas; este inspector no levanta un bloqueo de restauración.

Se añadió `proxmox_ca_file` para pasar la CA montada al transporte cuando TLS está verificado. Mantener `proxmox_verify_ssl=false` no habilita operación productiva: el informe lo rechaza. No se alteró el `.env` local ni se instaló una CA global.

Validación focal:24 pruebas de configuración/CA/secretos/artefactos/inventario/reinicio aprobadas en3,87s;41 de configuración/cliente SSH/I/O aprobaron en3,77s antes de ampliar dos casos; una prueba PostgreSQL aprobada en1,48s demuestra que ofertas, claves e inspección funcionan dentro de READ ONLY. Los transportes externos estaban bloqueados o explícitamente simulados. Se comprobó el CLI sobre la configuración local sin DB/red: devuelve no apto por su configuración de desarrollo, con códigos seguros y sin valores. No acredita producción, permisos mínimos reales ni integración PVE.

Pendiente de US8: backfill y regularización auditados, restricciones finales, configuración de despliegue, respaldo/restauración y aceptación real. Las pruebas iniciales de migración final/restauración se conservaron con fallos esperados hasta implementar sus tareas; no se presentan como una suite completa aprobada.
