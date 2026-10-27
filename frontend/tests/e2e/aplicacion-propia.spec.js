import { test, expect } from './fixtures';

async function portal(page, rol = 'admin') {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Responsable', rol } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  await page.route('**/api/v1/templates/sincronizar-iaas', (route) => route.fulfill({ json: { disponibles: 2 } }));
  await page.route('**/api/v1/biblioteca/**', (route) => route.fulfill({ json: { items: [], fuente: { estado: 'disponible' } } }));
}

test('agrega una imagen desde el mismo diálogo y conserva datos tras un error', async ({ page }) => {
  await portal(page);
  let offers = [];
  await page.route('**/api/v1/templates/?incluir_retiradas=true', (route) => route.fulfill({ json: offers }));
  let attempts = 0;
  await page.route('**/api/v1/templates/aplicaciones', (route) => {
    attempts += 1;
    const data = route.request().postDataJSON();
    expect(data.nombre).toBe('Campus de prácticas'); expect(data.imagen).toBe('universidad/campus:curso');
    expect(data.puerto).toBe(8080); expect(data).not.toHaveProperty('vmid');
    expect(route.request().headers()['idempotency-key']).toBeTruthy();
    if (attempts === 1) return route.fulfill({ status: 502, json: { detail: { mensaje: 'El registro no respondió. Volvé a intentarlo.' } } });
    offers = [{ id: 8, nombre: data.nombre, tipo: 'lxc', modelo_servicio: 'saas', activo: true, oferta_disponible: true,
      configuracion_despliegue_id: 'fixture-config', tamanos_permitidos: ['medium'], tamano_recomendado: 'medium' }];
    return route.fulfill({ status: 201, json: offers[0] });
  });
  await page.goto('/catalogo');
  await page.getByRole('button', { name: 'Agregar servicio', exact: true }).click();
  await page.getByRole('button', { name: 'Imagen Docker', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Nombre del servicio').fill('Campus de prácticas');
  await dialog.getByLabel('Imagen Docker').fill('universidad/campus:curso');
  await dialog.getByLabel('Puerto de la aplicación').fill('8080');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.screenshot({ path: '/tmp/nap011-own-form-dark.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(dialog.getByLabel('Imagen Docker')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '/tmp/nap011-own-form-mobile.png' });
  await dialog.getByRole('button', { name: 'Agregar al catálogo' }).click();
  await expect(dialog.getByRole('alert')).toContainText('El registro no respondió');
  await expect(dialog.getByLabel('Imagen Docker')).toHaveValue('universidad/campus:curso');
  await dialog.getByRole('button', { name: 'Agregar al catálogo' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Campus de prácticas', exact: true })).toBeVisible();
});

test('la cátedra no ve las entradas de administración del catálogo', async ({ page }) => {
  await portal(page, 'catedra_admin');
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.goto('/catalogo');
  await expect(page.getByRole('heading', { name: 'Catálogo de servicios', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Agregar servicio', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Imagen Docker', exact: true })).toHaveCount(0);
});
