import { test, expect } from './fixtures';

test('una operación incierta se consulta al recargar sin anunciar finalización', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 1, catedra_id: 1, template_id: 1, nombre_snapshot: 'Instancia', hostname: 'instancia', estado: 'stopped', modelo_servicio: 'iaas', operation_id: '11111111-1111-4111-8111-111111111111', disponibilidad_aplicacion: 'no_verificada' }] }));
  await page.route('**/api/v1/operaciones/11111111-1111-4111-8111-111111111111', (route) => route.fulfill({ json: { operation_id: '11111111-1111-4111-8111-111111111111', estado: 'incierta', tipo: 'iniciar', servicio_id: 1, fase: 'reconciliacion', error_detalle_seguro: 'Todavía no se confirmó el resultado' } }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.goto('/servicios');
  await expect(page.getByText(/Resultado incierto/).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Resultado incierto/).first()).toBeVisible();
  await expect(page.getByText('Servicio iniciado correctamente')).toHaveCount(0);
});


test('202 mantiene pendiente y bloquea otra orden hasta confirmación', async ({ page }) => {
  const operationId = '22222222-2222-4222-8222-222222222222';
  let admitted = false;
  let confirmed = false;
  let orders = 0;
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 1, catedra_id: 1, template_id: 1,
    hostname: 'instancia', estado: confirmed ? 'running' : 'stopped', modelo_servicio: 'iaas',
    operation_id: admitted && !confirmed ? operationId : null, disponibilidad_aplicacion: 'no_verificada',
    acciones_habilitadas: admitted && !confirmed ? [] : confirmed ? ['stop', 'restart', 'renovar'] : ['start', 'renovar'] }] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route(`**/api/v1/operaciones/${operationId}`, (route) => route.fulfill({ json: {
    operation_id: operationId, tipo: 'iniciar', servicio_id: 1, estado: confirmed ? 'confirmada' : 'en_curso', fase: 'tarea' } }));
  await page.route('**/api/v1/servicios/1/start', async (route) => {
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    orders += 1;
    admitted = true;
    await route.fulfill({ status: 202, json: { operation_id: operationId, tipo: 'iniciar', servicio_id: 1, estado: 'pendiente' } });
  });
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.goto('/servicios');
  await page.getByRole('button', { name: 'Iniciar servicio', exact: true }).click();
  await expect(page.getByText(/Operación en curso/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Iniciar servicio', exact: true })).toBeDisabled();
  expect(orders).toBe(1);
  confirmed = true;
  await expect(page.getByText(/Efecto de infraestructura confirmado/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pausar / Detener servicio', exact: true })).toBeEnabled();
  expect(orders).toBe(1);
});
