# US3 — ofertas y entrega simulada

Fecha: 2026-10-25. Se usaron ofertas/evidencias sintéticas sólo en fixtures de prueba.

`backend/tests/test_biblioteca_pedidos_010.py`: **2 passed**. Conserva versión solicitada 1.0.0, evalúa/aprueba vigente 2.0.0, registra aviso transaccional deduplicado y conserva el snapshot autorizado tras publicar 3.0.0. Una selección técnica anterior devuelve 409 para reevaluación. Repetir la aprobación con la misma clave devuelve la misma decisión.

`backend/tests/postgres/test_biblioteca_aprobacion_010.py`: publicación y aprobación con sesiones independientes comparten lock: publicación primero invalida token; aprobación primero congela su versión y reserva. Incluida en la regresión de **108 pruebas PostgreSQL**. Las pruebas existentes de renovaciones y «Otro» siguen pasando en la regresión backend.

`backend/tests/test_drawio_entrega_010.py`: prueba dos cátedras/instancias con UUID y credenciales diferentes, consulta cruzada denegada, acceso HTTPS administrativo y ningún llamado a Community Scripts. Bootstrap local no activa el pedido sin la verificación externa existente. Se ejecutó junto a contratos/worker/limpieza: **7 passed**; forma parte también de la regresión general.

Frontend verifica versión ofrecida, catálogo preseleccionado sin hardware y comparación solicitada/efectiva al aprobar. Playwright recorre Catálogo y Pedidos: ante cambio 409 conserva propósito, fechas y justificación, recarga versión y cambia la clave sólo cuando cambia el contenido de la intención. Reenvío conserva también los campos; un error sin cambio de selección mantiene la clave.

Suites completas: [regresion.md](regresion.md). **T067 continúa pendiente**: no hubo dos entregas reales ni un pedido real durante bloqueo de Community Scripts. Los tests prueban ausencia de llamadas a la fuente; no acreditan tráfico, certificados ni edición del navegador en staging.
