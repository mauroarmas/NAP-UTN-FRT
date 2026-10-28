import { test, expect } from './fixtures';

/**
 * Medición de apertura de consola y rendimiento visual (US4 - T087 / SC-004).
 * Backend simulado para reproducibilidad y aislamiento.
 */

test('apertura de consola con 200 mensajes en menos de 3 segundos', async ({ page }) => {
  const opId = '55555555-5555-5555-8555-555555555555';

  const items = Array.from({ length: 200 }, (_, i) => ({
    seq: i + 1,
    intento: 1,
    captured_at: new Date(Date.now() - (200 - i) * 1000).toISOString(),
    fase: 'instalacion',
    stream: i % 10 === 0 ? 'sistema' : i % 5 === 0 ? 'stderr' : 'stdout',
    texto_depurado: `Mensaje de consola número ${i + 1} para prueba de rendimiento de interfaz.`,
  }));

  const mockResponse = {
    operation_id: opId,
    operacion_raiz_id: opId,
    estado: 'en_curso',
    fase: 'instalacion',
    intento_efectivo: 1,
    items,
    next_cursor: 200,
    previous_cursor: 1,
    has_more: false,
    first_retained_seq: 1,
    last_seq: 200,
    truncated: false,
    expired: false,
    dropped_messages: 0,
    last_captured_at: new Date().toISOString(),
    last_ingested_at: new Date().toISOString(),
    resultado_final: null,
  };

  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } },
    })
  );

  const pedido = {
    id: 55,
    tipo: 'alta',
    catedra_id: 1,
    template_id: 10,
    modelo_servicio: 'saas',
    estado: 'en_despliegue',
    operation_id: opId,
    servicio_id: null,
    descripcion_requerimientos: 'Prueba de rendimiento.',
    historial: [],
  };

  await page.route('**/api/v1/pedidos/**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/55') ? pedido : [pedido],
    })
  );
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) =>
    route.fulfill({ json: [{ id: 1, nombre: 'Cátedra 1' }] })
  );
  await page.route(`**/api/v1/operaciones/${opId}/consola*`, (route) =>
    route.fulfill({ json: mockResponse, headers: { 'Cache-Control': 'no-store' } })
  );
  await page.route(`**/api/v1/operaciones/${opId}`, (route) =>
    route.fulfill({
      json: { operation_id: opId, pedido_id: 55, tipo: 'desplegar', estado: 'en_curso', fase: 'instalacion' },
    })
  );

  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Ver detalle', exact: true }).click();

  const t0 = Date.now();
  await page.getByRole('button', { name: 'Ver consola' }).click();

  const dialog = page.getByRole('dialog', { name: 'Consola de operación' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Mensaje de consola número 200')).toBeVisible();

  const elapsed = (Date.now() - t0) / 1000;
  expect(elapsed).toBeLessThanOrEqual(3.0);
});

