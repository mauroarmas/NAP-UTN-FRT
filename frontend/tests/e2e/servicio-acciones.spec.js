import { test, expect } from './fixtures';

async function preparar(page, overrides = {}) {
  const service = { id: 7, catedra_id: 1, nombre_snapshot: 'Servicio de prueba', tipo: 'lxc',
    modelo_servicio: null, estado: 'stopped', estado_cobertura: 'sin_regularizar',
    regularizacion_pendiente: true, regularizacion_legacy: true, acciones_habilitadas: [],
    vcpus_asignados: 1, ram_asignada_mb: 256, disk_asignado_gb: 4, ...overrides };
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    estado: 'operativo', usuario: { id: 2, nombre: 'Docente', rol: 'catedra_admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
  await page.route((url) => url.pathname === '/api/v1/servicios/', (route) => route.fulfill({ json: [service] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Bases de Datos' }] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.goto('/servicios');
  return service;
}

async function opciones(page) {
  await page.getByRole('button', { name: 'Opciones del servicio' }).click();
}

test('un registro pendiente explica el bloqueo y no envía órdenes', async ({ page }) => {
  let orders = 0;
  await page.route('**/api/v1/servicios/7/start', (route) => { orders += 1; return route.fulfill({ json: {} }); });
  await preparar(page);
  await expect(page.getByRole('button', { name: 'Iniciar servicio', exact: true })).toBeDisabled();
  const reviewButton = page.getByRole('button', { name: 'Pendiente de Revisión', exact: true });
  await reviewButton.focus();
  await page.keyboard.press('Enter');
  const reviewDialog = page.getByRole('dialog', { name: 'Pendiente de Revisión', exact: true });
  await expect(reviewDialog.getByText('Pedile al administrador del portal que revise este servicio.')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(reviewDialog).toHaveCount(0);
  await expect(reviewButton).toBeFocused();
  await opciones(page);
  await expect(page.getByText('Algunas acciones requieren que administración revise los datos del servicio.')).toBeVisible();
  for (const name of ['Reiniciar', 'Solicitar renovación']) {
    const button = page.getByRole('button', { name, exact: true });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute('title', /Administración debe revisar/);
    await expect(button).toHaveCSS('cursor', 'not-allowed');
  }
  await expect(page.getByRole('button', { name: 'Marcar siempre activo' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Consultar estado' })).toBeEnabled();
  expect(orders).toBe(0);
});

test('siempre activo confirma el cambio junto al servicio y muestra los fallos', async ({ page }) => {
  const service = await preparar(page);
  let writes = 0;
  await page.route('**/api/v1/servicios/7', (route) => {
    writes += 1;
    if (writes > 1) return route.fulfill({ status: 409, json: { detail: { mensaje: 'No se pudo guardar la preferencia.' } } });
    expect(route.request().postDataJSON()).toEqual({ exento_pausado: true });
    service.exento_pausado = true;
    return route.fulfill({ json: service });
  });
  page.once('dialog', (dialog) => dialog.dismiss());
  await opciones(page);
  await page.getByRole('button', { name: 'Marcar siempre activo' }).click();
  expect(writes).toBe(0);
  page.once('dialog', (dialog) => dialog.accept());
  await opciones(page);
  await page.getByRole('button', { name: 'Marcar siempre activo' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Siempre activo habilitado' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Iniciar servicio', exact: true })).toBeDisabled();
  await opciones(page);
  await page.getByRole('button', { name: 'Quitar siempre activo' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'No se pudo guardar la preferencia.' })).toBeVisible();
  expect(writes).toBe(2);
});

test('consultar estado muestra espera, error y reintento sin detalles técnicos al docente', async ({ page }) => {
  await preparar(page);
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  let reads = 0;
  await page.route('**/api/v1/servicios/7/status', async (route) => {
    reads += 1;
    if (reads === 1) {
      await pending;
      return route.fulfill({ status: 502, json: { detail: 'Error técnico interno no destinado al usuario' } });
    }
    return route.fulfill({ json: { estado: 'stopped', proxmox_status: { status: 'stopped', secret_detail: 'interno' } } });
  });
  await opciones(page);
  await page.getByRole('button', { name: 'Consultar estado' }).click();
  const dialog = page.getByRole('dialog', { name: 'Estado del servicio' });
  await expect(dialog.getByRole('status')).toHaveText(/Consultando el estado/);
  finish();
  await expect(dialog.getByRole('alert')).toHaveText(/No se pudo consultar el estado/);
  await expect(dialog.getByText('Error técnico interno no destinado al usuario')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Reintentar consulta' }).click();
  await expect(dialog.getByText('Estado consultado:', { exact: false })).toHaveText('Estado consultado: Detenido.');
  await expect(dialog.getByText('Detalles técnicos')).toHaveCount(0);
  expect(reads).toBe(2);
});

test('cerrar la consulta pendiente impide que la respuesta vuelva a abrir el diálogo', async ({ page }) => {
  await preparar(page);
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  await page.route('**/api/v1/servicios/7/status', async (route) => {
    await pending;
    return route.fulfill({ json: { estado: 'running', proxmox_status: { status: 'running' } } });
  });
  await opciones(page);
  await page.getByRole('button', { name: 'Consultar estado' }).click();
  await expect(page.getByRole('dialog', { name: 'Estado del servicio' }).getByRole('status')).toBeVisible();
  await page.keyboard.press('Escape');
  const response = page.waitForResponse('**/api/v1/servicios/7/status');
  finish();
  await response;
  await expect(page.getByRole('dialog', { name: 'Estado del servicio' })).toHaveCount(0);
});

test('reiniciar un servicio habilitado envía una sola orden y espera confirmación', async ({ page }) => {
  const operationId = '33333333-3333-4333-8333-333333333333';
  const service = await preparar(page, { estado: 'running', modelo_servicio: 'iaas', regularizacion_pendiente: false,
    estado_cobertura: 'con_cobertura', acciones_habilitadas: ['stop', 'restart', 'renovar'] });
  let orders = 0;
  await page.route('**/api/v1/servicios/7/restart', (route) => {
    orders += 1;
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    service.operation_id = operationId;
    service.acciones_habilitadas = [];
    return route.fulfill({ status: 202, json: { operation_id: operationId } });
  });
  await page.route(`**/api/v1/operaciones/${operationId}`, (route) => route.fulfill({ json: {
    operation_id: operationId, servicio_id: 7, tipo: 'reiniciar', estado: 'en_curso', fase: 'tarea' } }));
  page.once('dialog', (dialog) => dialog.accept());
  await opciones(page);
  await page.getByRole('button', { name: 'Reiniciar', exact: true }).click();
  await expect(page.getByText(/Operación en curso/).first()).toBeVisible();
  await opciones(page);
  await expect(page.getByRole('button', { name: 'Reiniciar', exact: true })).toBeDisabled();
  expect(orders).toBe(1);
});
