import { test, expect } from './fixtures';

async function auth(page, admin = false) {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: {
    id: 1, nombre: 'Operador de prueba', rol: admin ? 'admin' : 'catedra_admin', catedras: [] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
}

test('gráficas diferidas, tabla exacta y actualización fallida sin perder el último dato', async ({ page }) => {
  await auth(page);
  const scripts = [];
  page.on('request', (request) => { if (request.resourceType() === 'script') scripts.push(request.url()); });
  const now = Date.now();
  const points = [1,2,3].map((id) => ({ id, servicio_id: 1,
    timestamp: new Date(now - (4-id) * 60000).toISOString(), intervalo_at: new Date(now-(4-id)*60000).toISOString(),
    calidad: 'confirmada', estado_observado: 'running', cpu_usage_percent: 20 + id * 5,
    ram_usage_mb: 64 * id, ram_max_mb: 1024, disk_usage_gb: 1, disk_max_bytes: 8 * 1024**3,
    net_in_delta: id === 1 ? null : id === 2 ? 'raw-int-placeholder' : 0,
    net_in_delta_exacto: id === 1 ? null : id === 2 ? '9007199254740993' : '0',
    net_out_delta: id === 1 ? null : 100, duracion_observada_s: id === 1 ? 0 : 60 }));
  let reads = 0, captures = 0;
  await page.route('**/api/v1/metricas/resumen', (route) => {
    reads += 1;
    return reads > 1 ? route.fulfill({ status: 503, json: { detail: { mensaje: 'No se pudo consultar el resumen.' } } })
      : route.fulfill({ json: [{ servicio_id: 1, nombre: 'Base del curso', estado: 'running', estado_observado: 'running',
        observacion_reciente: true, ram_max_mb: 1024, disk_max_gb: 8, ultimo_snapshot: points[2] }] });
  });
  await page.route('**/api/v1/metricas/1/historial?**', (route) => route.fulfill({
    contentType: 'application/json', body: JSON.stringify(points).replace('"raw-int-placeholder"', '9007199254740993') }));
  await page.route('**/api/v1/metricas/capturar**', (route) => { captures += 1; return route.abort(); });
  await page.goto('/metricas');
  await expect(page.getByRole('heading', { name: 'Base del curso', exact: true })).toBeVisible();
  expect(scripts.some((url) => url.includes('GraficasMetricas-'))).toBe(false);
  await page.getByRole('button', { name: 'Ver historial de Base del curso' }).click();
  await expect(page.getByLabel('Resumen textual del historial')).toContainText('3 puntos seleccionados');
  await expect(page.getByLabel('Gráficas de observaciones').locator('svg').first()).toBeVisible();
  expect(scripts.some((url) => url.includes('GraficasMetricas-'))).toBe(true);
  await page.getByText('Consultar tabla de observaciones', { exact: true }).click();
  await expect(page.getByRole('table').getByText('9.007.199.254.740.993 bytes')).toBeVisible();
  await page.getByRole('button', { name: 'Actualizar', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Conservamos los datos anteriores');
  await expect(page.getByRole('heading', { name: 'Base del curso', exact: true })).toBeVisible();
  expect(captures).toBe(0);
  await page.screenshot({ path: '/tmp/nap009-metricas-ui.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel('Resumen textual del historial')).toBeVisible();
  await page.screenshot({ path: '/tmp/nap009-metricas-mobile.png', fullPage: true });
});

test('formularios administrativos tienen etiquetas y guardan una vez con Enter', async ({ page }) => {
  await auth(page, true);
  let users = 0, categories = 0;
  await page.route('**/api/v1/usuarios/**', (route) => {
    if (route.request().method() === 'POST') {
      users += 1;
      expect(route.request().postDataJSON().username).toBe('teclado');
      return route.fulfill({ status: 201, json: { id: 2 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.route('**/api/v1/catedras/**', (route) => {
    if (route.request().method() === 'POST') {
      categories += 1;
      expect(route.request().postDataJSON().nombre).toBe('Cátedra de teclado');
      return route.fulfill({ status: 201, json: { id: 2 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto('/usuarios');
  await page.getByRole('button', { name: 'Nuevo usuario', exact: true }).click();
  const userDialog = page.getByRole('dialog', { name: 'Nuevo usuario' });
  await userDialog.getByLabel('Username', { exact: true }).fill('teclado');
  await userDialog.getByLabel('Nombre completo', { exact: true }).fill('Operador de teclado');
  await userDialog.getByLabel(/Email/).fill('teclado@example.org');
  await userDialog.getByLabel('Rol', { exact: true }).selectOption('admin');
  await userDialog.getByLabel(/Email/).press('Enter');
  await expect(userDialog).not.toBeVisible();
  expect(users).toBe(1);
  await page.goto('/catedras');
  await page.getByRole('button', { name: 'Nueva cátedra', exact: true }).click();
  const categoryDialog = page.getByRole('dialog', { name: 'Nueva cátedra' });
  await categoryDialog.getByLabel('Nombre', { exact: true }).fill('Cátedra de teclado');
  await categoryDialog.getByLabel('Nombre', { exact: true }).press('Enter');
  await expect(categoryDialog).not.toBeVisible();
  expect(categories).toBe(1);
});


test('fallo de un módulo deja un mensaje y permite navegar a otra vista', async ({ page }) => {
  await auth(page, true);
  await page.route('**/assets/Catedras-*.js', (route) => route.abort('blockedbyclient'));
  await page.route('**/api/v1/metricas/resumen', (route) => route.fulfill({ json: [] }));
  await page.goto('/catedras');
  await expect(page.getByRole('alert')).toContainText('No se pudo cargar esta vista');
  await page.getByRole('link', { name: 'Métricas', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Métricas', exact: true })).toBeVisible();
  await expect(page.getByText('No hay servicios con métricas disponibles.')).toBeVisible();
});
