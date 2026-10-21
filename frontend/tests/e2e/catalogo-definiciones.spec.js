import { test, expect } from './fixtures';

test('administración publica y retira una versión sin alterar su manifiesto', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  let row = { id: '11111111-1111-4111-8111-111111111111', codigo: 'linux-curso', version: '1.0.0',
    producto: 'linux', modelo_servicio: 'iaas', estado: 'validada', manifest: { definition_key: 'linux-curso' } };
  let mutations = 0;
  await page.route('**/api/v1/definiciones**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [row] });
    mutations += 1;
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    if (route.request().url().endsWith('/publicar')) row = { ...row, estado: 'publicada' };
    else {
      expect(route.request().postDataJSON()).toEqual({ motivo: 'Sustituida por otra versión validada' });
      row = { ...row, estado: 'retirada' };
    }
    return route.fulfill({ json: row });
  });
  await page.goto('/definiciones');
  await page.getByRole('button', { name: /linux-curso 1.0.0/ }).click();
  await expect(page.getByLabel('Manifiesto JSON')).toHaveJSProperty('readOnly', true);
  expect(mutations).toBe(0);
  await page.getByRole('button', { name: 'Publicar versión' }).click();
  await expect(page.getByText('Estado: publicada.', { exact: false })).toBeVisible();
  await page.getByLabel('Motivo del retiro').fill('Sustituida por otra versión validada');
  await page.getByRole('button', { name: 'Retirar versión', exact: true }).click();
  await expect(page.getByText('Estado: retirada.', { exact: false })).toBeVisible();
  expect(mutations).toBe(2);
});

test('el catálogo docente solicita una vigencia desde un perfil publicado sin campos PVE', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 2, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  const profile = { id: 2, nombre: 'Base de laboratorio', modelo_servicio: 'paas', tipo: 'lxc', activo: true,
    oferta_disponible: true, default_vcpus: 1, default_ram_mb: 1024, default_disk_gb: 8, os_template: 'image-internal-only' };
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [profile,
    { ...profile, id: 3, nombre: 'No publicada', oferta_disponible: false }, { ...profile, id: 4, nombre: 'QEMU histórico', tipo: 'qemu' }] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.route('**/api/v1/calendarios/*', (route) => route.fulfill({ json: { anio: 2027, periodos: [] } }));
  let submitted;
  await page.route('**/api/v1/pedidos/', (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: { id: 20, estado: 'solicitado' } });
  });
  await page.goto('/catalogo');
  await page.getByRole('button', { name: 'Solicitar Base de laboratorio' }).click();
  await expect(page.getByLabel('Plantilla')).toHaveValue('2');
  await expect(page.getByText('image-internal-only')).toHaveCount(0);
  await expect(page.getByText('No publicada', { exact: true })).toHaveCount(0);
  await expect(page.getByText('QEMU histórico', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Rango Personalizado' }).click();
  await page.getByLabel('Fecha desde').fill('2027-03-01');
  await page.getByLabel('Fecha hasta').fill('2027-06-30');
  await page.getByRole('button', { name: 'Enviar solicitud' }).click();
  await expect(page.getByRole('status')).toHaveText(/Solicitud #20 registrada/);
  expect(submitted).toEqual({ modelo_servicio: 'paas', template_id: 2, catedra_id: 1, descripcion_requerimientos: null,
    vigencia: { tipo: 'personalizado', desde: '2027-03-01', hasta: '2027-06-30' } });
});

test('el editor envía el sobre manifest y conserva duplicados para rechazo del servidor', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  const row = { id: '11111111-1111-4111-8111-111111111111', codigo: 'linux-curso', version: '1.0.0',
    producto: 'linux', modelo_servicio: 'iaas', estado: 'borrador', manifest: {} };
  let sent = false;
  await page.route('**/api/v1/definiciones**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [row] });
    const raw = route.request().postData();
    expect(raw.startsWith('{"manifest":')).toBe(true);
    expect((raw.match(/"definition_key"/g) || []).length).toBe(2);
    sent = true;
    return route.fulfill({ status: 422, json: { detail: { mensaje: 'El manifiesto contiene claves duplicadas.' } } });
  });
  await page.goto('/definiciones');
  await page.getByRole('button', { name: /linux-curso 1.0.0/ }).click();
  const raw = '{"definition_key":"linux-curso","definition_key":"otra-version"}';
  await page.getByLabel('Manifiesto JSON').fill(raw);
  await page.getByRole('button', { name: 'Guardar manifiesto' }).click();
  await expect(page.getByRole('alert')).toHaveText('El manifiesto contiene claves duplicadas.');
  await expect(page.getByLabel('Manifiesto JSON')).toHaveValue(raw);
  expect(sent).toBe(true);
});
