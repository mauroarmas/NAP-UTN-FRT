# Mediciones de aceptación — pendientes (T072)

No se midieron tiempos humanos de SC-001 (<2 min) ni SC-004 (<3 min), ni p95 de consultas/estado con 10 sesiones y 100 muestras en entorno representativo. Los tiempos de pytest/Playwright y los tests con fuente simulada no sustituyen estas mediciones.

La implementación limita cada consulta externa a 10 s (conexión 3 s), 8 MiB/10.000 entradas y cache 15 min, probados con transportes controlados. Polling de ensayo cada 5 s sólo con pestaña visible. Queda medir el recorrido humano con fuente disponible y la carga autorizada en staging según quickstart; conservar muestras, concurrencia, hardware, estado de cache y percentiles. No se afirma cumplir el objetivo p95 por el solo hecho de configurar deadlines.
