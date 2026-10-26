# US1: validación local

- Backend API/fuente: 9 pruebas pasan.
- PostgreSQL 16 aislado: importación con dos sesiones/otras claves conserva una fila (1 prueba pasa).
- Vitest: biblioteca y regresión Definiciones (4 pruebas pasan).
- Playwright Chromium: incorporación por categoría y edición (1 prueba pasa).
- Lint: sin errores; advertencias anteriores en Servicios/Pedidos/ui.

Dobles de proveedor, sin instalaciones ni operaciones PVE. Medición humana SC-001 con proveedor real pendiente de T072; no acreditada por estas pruebas.
