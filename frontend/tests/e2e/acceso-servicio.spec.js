import { test, expect } from './fixtures';

async function prepare(page, admin) {
  const counts = { reads: 0, reveals: 0, verifies: 0, imports: 0 };
  let delivered = false;
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: {
    id: 1, nombre: admin ? 'Admin' : 'Docente', rol: admin ? 'admin' : 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  const service = { id: 1, catedra_id: 1, template_id: 1, nombre_snapshot: 'Libro del curso', modelo_servicio: 'saas',
    estado: 'running', disponibilidad_aplicacion: 'no_verificada', vcpus_asignados: 1, ram_asignada_mb: 1024,
    disk_asignado_gb: 8, cobertura_actual: true, estado_cobertura: 'con_cobertura', acciones_habilitadas: [] };
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [service] }));
  await page.route('**/api/v1/pedidos/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route('**/api/v1/servicios/1/acceso**', (route) => {
    if (route.request().url().endsWith('/revelar')) {
      counts.reveals += 1;
      return route.fulfill({ json: { servicio_id: 1, estado_entrega: 'solo_validacion', metodo: 'https',
        direccion: 'https://libro.example.edu', credenciales: { usuario: 'docente@example.edu', password: 'test-only-initial-password',
          app_key: 'must-not-be-rendered', database_password: 'must-not-be-rendered-db' } } });
    }
    counts.reads += 1;
    return route.fulfill({ json: { servicio_id: 1, producto: 'bookstack', metodo: 'https',
      estado_entrega: delivered ? 'entregado' : admin ? 'solo_validacion' : 'pendiente_verificacion',
      disponibilidad: delivered ? 'utilizable' : 'no_verificada', direccion: 'https://libro.example.edu',
      puede_revelar_credenciales: admin || delivered,
      instrucciones: delivered ? 'Acceso inicial entregado.' : 'Falta comprobar acceso desde la red prevista.' } });
  });
  await page.route('**/api/v1/evidencias', (route) => {
    counts.imports += 1;
    expect(route.request().postDataJSON().tipo).toBe('acceso_instancia');
    return route.fulfill({ status: 201, json: { evidencia_ref: '11111111-1111-4111-8111-111111111111', sha256: 'test-sha' } });
  });
  await page.route('**/api/v1/servicios/1/verificar-acceso', (route) => {
    counts.verifies += 1; delivered = true;
    expect(route.request().postDataJSON()).toEqual({ evidencia_ref: '11111111-1111-4111-8111-111111111111',
      endpoint: 'https://libro.example.edu', observado_at: '2026-10-20T20:00:00Z' });
    return route.fulfill({ json: { disponibilidad: 'utilizable' } });
  });
  return counts;
}

test('el docente consulta acceso sin carga de secretos o entrega anticipada', async ({ page }) => {
  const counts = await prepare(page, false);
  await page.goto('/servicios');
  const access = page.getByRole('button', { name: 'Ver acceso', exact: true });
  await expect(access).toBeVisible();
  expect(counts.reads).toBe(0);
  await access.click();
  const region = page.getByRole('region', { name: 'Acceso al servicio', exact: true });
  await expect(region.getByText('Falta comprobar acceso desde la red prevista.')).toBeVisible();
  await expect(region.getByRole('button', { name: /Revelar/ })).toHaveCount(0);
  await expect(region.getByRole('link', { name: 'Abrir aplicación', exact: true })).toHaveCount(0);
  expect(counts.reveals).toBe(0);
});

test('administración revela sin copiar e importa antes de confirmar una entrega', async ({ page }) => {
  await page.addInitScript(() => {
    window.napClipboardWrites = 0;
    Object.defineProperty(navigator, 'clipboard', { configurable: true, get: () => ({
      writeText: async () => { window.napClipboardWrites += 1; },
    }) });
  });
  const counts = await prepare(page, true);
  await page.goto('/servicios');
  await page.getByRole('button', { name: 'Ver acceso', exact: true }).click();
  const region = page.getByRole('region', { name: 'Acceso al servicio', exact: true });
  await region.getByRole('button', { name: 'Revelar acceso inicial' }).click();
  await expect(region.getByText('test-only-initial-password', { exact: true })).toBeVisible();
  await expect(region.getByText('must-not-be-rendered', { exact: true })).toHaveCount(0);
  await expect(region.getByText('must-not-be-rendered-db', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.napClipboardWrites)).toBe(0);
  await region.getByLabel('Documento de evidencia').fill('{"tipo":"acceso_instancia","observado_at":"2026-10-20T20:00:00Z"}');
  await region.getByRole('button', { name: 'Registrar evidencia', exact: true }).click();
  await expect(region.getByLabel('Referencia UUID de evidencia registrada')).toHaveValue('11111111-1111-4111-8111-111111111111');
  expect(counts.verifies).toBe(0);
  await region.getByRole('button', { name: 'Confirmar verificación de acceso' }).click();
  await expect(region.getByText('Acceso verificado. La entrega quedó registrada.')).toBeVisible();
  await expect(region.getByText('test-only-initial-password', { exact: true })).toHaveCount(0);
  expect(counts.reveals).toBe(1); expect(counts.imports).toBe(1); expect(counts.verifies).toBe(1);
  await page.screenshot({ path: '/tmp/nap009-access-ui.png', fullPage: true });
});
