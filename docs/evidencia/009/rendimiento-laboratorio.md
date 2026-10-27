# Laboratorio reproducible SC-008

El generador rechaza SQLite, destinos remotos, otros puertos/roles/bases y parámetros de conexión alternativos. Nunca lee `.env`, no borra tablas y sólo reanuda una base marcada con el UUID de su configuración. Usa credenciales/JWT/CSRF/keyring propios, archivos regulares del operador0600, directorio0700 y un PostgreSQL dedicado. El modo `plan` no produce cambios. No activar estos scripts en operación.

Desde la raíz, con dependencias instaladas según sus locks:

```bash
backend/venv/bin/python backend/scripts/validar_carga.py plan --config /ruta/privada/configuracion.json
backend/venv/bin/python backend/scripts/validar_carga.py init --config /ruta/privada/configuracion.json --execute
# El directorio padre sigue0700. Sólo se monta este archivo en el contenedor:
chmod 0644 /ruta/privada/pg-password
NAP_PERFORMANCE_PRIVATE_DIR=/ruta/privada docker compose --env-file /dev/null -f docker-compose.performance.yml up -d --wait
backend/venv/bin/python backend/scripts/validar_carga.py prepare --config /ruta/privada/configuracion.json --execute
backend/venv/bin/python backend/scripts/validar_carga.py serve --config /ruta/privada/configuracion.json --execute
# Otra terminal, desde frontend:
PLAYWRIGHT_BROWSERS_PATH=/ruta/cache/chromium npm run test:performance -- --config /ruta/privada/configuracion.json --execute
```

`test:performance` compila la SPA, inicia preview4174 con proxy a API8044, ejecuta Chromium y detiene su preview/navegador al terminar. Si4174 está ocupado, detener sólo el preview de este ensayo antes de ejecutar. El backend se detiene con Ctrl+C en su terminal. Detener PostgreSQL conserva el volumen; no usar `down -v` si se quiere conservar evidencia. Para repetir un ensayo completo desde cero, usar una copia nueva del laboratorio y conservar la anterior; nunca modificar el UUID para adoptar una base ajena.

Las diez cuentas se autentican mediante login normal y cookies independientes (cinco docentes, cinco admins); no hay tokens en Web Storage ni storageState exportado. El navegador usa localhost y su excepción de origen confiable para cookies Secure de pruebas. No acredita configuración TLS productiva.

El fixture contiene exactamente cien servicios, tres modelos, diez cátedras con cinco titulares y noventa días a un minuto:12.960.000 observaciones. Pedidos, identidades, ledger, vigencias y eventos de asignación se siembran como **datos sintéticos**; la aplicación no declara acceso institucional verificado. Cada servicio se inserta en una transacción mediante generate_series, sin millones de objetos ORM; reanudar salta los completos y rechaza detalle parcial inesperado. Aplica las migraciones Alembic reales. Conserva corte temporal, IDs, hashes de fuentes/locks, índices, EXPLAIN ANALYZE y tamaño en fixture.json privado. SMTP está vacío y no se inicia el scheduler de métricas/purga/notificaciones durante la medición.

La API y consultas SQL son las del producto. Sólo los transportes PVE/runner son dobles:100 recursos existentes y una tarea nueva que responde running con2s de I/O por sondeo hasta el cierre explícito. El controlador usa login/CSRF/evaluación/aprobación/despliegue reales; exige202, fase tarea y confirmación final. Los endpoints privados sólo existen en scripts/rendimiento_server.py, escuchan en loopback y exigen token propio. La definición de esta tarea y sus artefactos/evidencias están marcados **simulado**, admitidos exclusivamente por app_env=test; nunca se publican en el laboratorio PVE ni sirven como T101/T102.

El primer intento completó150 calentamientos válidos pero falló antes de medir por un error del controlador al obtener CSRF desde login. Se corrigió usando GET/auth/csrf; recibo íntegro conservado en el directorio privado como intento-1.json. No tuvo muestras medidas y no se computa como aceptación.

El protocolo calcula p95 nearest-rank por recorrido y tasa de resultados válidos en<=3000ms sobre todas las muestras medidas, incluidos errores/timeouts. No compara relojes servidor/cliente. La marca inicial se toma en captura del evento DOM, antes del handler React; termina en el navegador después del pintado de filas actuales o gráfica+resumen+intervalo correctos y controles habilitados. Compara IDs y muestras contra el fixture/rango, no sólo presencia de un spinner. Mantiene caché estática normal y datos no-store. Server-Timing ofrece HTTP/DB/número de consultas como diagnóstico separado.

## Resultado del ensayo completo

[Informe completo](rendimiento-navegador.json), [diagnóstico HTTP/DB](rendimiento-diagnostico.json) y [medición anterior fallida](rendimiento-navegador-antes.json). Se verificaron450registros (150calentamientos excluidos y100medidas por cada recorrido),5calentamientos y10medidas por contexto/recorrido, cinco cuentas por rol, todas las comprobaciones de la operación pendiente y su confirmación final. El diario contiene las mismas450muestras. Ninguna muestra medida de este ensayo se descartó.

| Recorrido | p95 visible(ms) | Válidas en<=3000ms | p95 HTTP(ms), diagnóstico |
|---|---:|---:|---:|
| Pedidos |1567,9|100/100|1290,3|
| Servicios |2747,2|98/100|2501,4|
| Métricas |2472,3|100/100|1345,4|

Los tres recorridos cumplen p95<=3000ms y tasa>=95 %. El despliegue simulado f82acb52-0753-4ca2-a17a-bbe769d3a09d permaneció pendiente durante las mediciones y se confirmó al cierre (51,31s desde admisión). Host, cuotas de PostgreSQL, versión de Chromium, hashes de fuentes/locks y condiciones están dentro del informe. API/worker/proxy/navegador comparten el equipo sin cuotas adicionales; el resultado acredita SC-008 bajo esas condiciones, no promete los mismos tiempos en cualquier instalación.

Un intento intermedio se detuvo por la comprobación de viewport y se conserva como [incompleto, no aceptado](rendimiento-interrumpido.json). Se confirmó y dio de baja únicamente su recurso simulado por API/worker, manteniendo los cien servicios de referencia. Desde la última ejecución cada muestra se escribe también en un diario privado durante el ensayo; un corte posterior conserva lo ya registrado. El ensayo fallido completo anterior no se reemplazó ni presentó como aprobado.

La validación con el responsable de una cátedra y las integraciones reales de PVE/SMTP/aplicaciones siguen pendientes. SC-008 simula los transportes de infraestructura expresamente; no acredita T101/T102.
