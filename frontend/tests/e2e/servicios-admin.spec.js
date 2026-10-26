import { test, expect } from './fixtures';
import { sizes } from '../fixtures/tamanos';

const definitions = [
  { id: 'linux-def', codigo: 'linux-aula', version: '1.0.0', estado: 'publicada', producto: 'linux', modelo_servicio: 'iaas', minimum_resources: { vcpus: 1, ram_mb: 512, disk_gb: 4 } },
  { id: 'pg-def', codigo: 'postgresql-aula', version: '1.0.0', estado: 'publicada', producto: 'postgresql', modelo_servicio: 'paas', minimum_resources: { vcpus: 2, ram_mb: 1024, disk_gb: 8 } },
];
const initial = [
  { id: 1, nombre: 'Linux para prácticas', descripcion: 'Un entorno de trabajo para aprender y experimentar con Linux.', tipo: 'lxc', modelo_servicio: 'iaas', activo: true, oferta_disponible: true, definicion_version_id: 'linux-def', tamanos_permitidos: ['small', 'medium'], tamano_recomendado: 'small' },
  { id: 2, nombre: 'PostgreSQL', descripcion: 'Una base de datos independiente para los ejercicios de la cátedra.', tipo: 'lxc', modelo_servicio: 'paas', activo: true, oferta_disponible: true, definicion_version_id: 'pg-def', tamanos_permitidos: ['medium'], tamano_recomendado: 'medium' },
];

async function mockAdmin(page) {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Administrador', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  await page.route('**/api/v1/definiciones**', (route) => route.fulfill({ json: definitions }));
  let offers = structuredClone(initial);
  await page.route('**/api/v1/templates/**', (route) => {
    const request = route.request();
    if (request.url().endsWith('/tamanos')) return route.fulfill({ json: sizes });
    if (request.method() === 'POST') {
      const body = request.postDataJSON();
      expect(body).toMatchObject({ tamano: 'medium', default_vcpus: 2, default_ram_mb: 1024, default_disk_gb: 8 });
      const row = { ...body, id: 3, activo: true, oferta_disponible: true, tamanos_permitidos: ['medium'], tamano_recomendado: 'medium' };
      offers.push(row);
      return route.fulfill({ status: 201, json: row });
    }
    if (request.method() === 'DELETE') {
      const id = Number(new URL(request.url()).pathname.split('/').pop());
      offers = offers.map((row) => row.id === id ? { ...row, activo: false, oferta_disponible: false } : row);
      return route.fulfill({ json: offers.find((row) => row.id === id) });
    }
    return route.fulfill({ json: offers });
  });
}

for (const layout of ['oscuro', 'claro', 'movil']) {
  test(`servicios y tamaños son legibles en ${layout}`, async ({ page }) => {
    if (layout === 'movil') await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript((theme) => localStorage.setItem('theme', theme), layout === 'claro' ? 'light' : 'dark');
    await mockAdmin(page);
    await page.goto('/admin/servicios');
    await expect(page.getByRole('heading', { name: 'Catálogo de servicios' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'PostgreSQL', exact: true })).toBeVisible();
    await expect(page.getByLabel('Tamaños compartidos')).toContainText('512 MB RAM');
    await expect(page.getByLabel('Tamaños compartidos')).toContainText('1024 MB RAM');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (layout === 'movil') {
      await page.getByRole('button', { name: 'Abrir navegación' }).click();
      await page.getByRole('button', { name: 'Administración', exact: true }).click();
      await expect(page.getByRole('link', { name: 'Servicios del catálogo' })).toHaveCount(0);
      await expect(page.getByRole('link', { name: 'Calendario', exact: true })).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('button', { name: 'Abrir navegación' })).toBeFocused();
    }
    const tops = await page.getByRole('article').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().top));
    if (layout !== 'movil') expect(tops[0]).toBe(tops[1]);
    await page.screenshot({ path: `/tmp/nap-servicios-${layout}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Agregar servicio', exact: true }).click();
    await page.getByLabel('Aplicación preparada').selectOption('pg-def');
    await expect(page.getByRole('radio', { name: /^Small/ })).toBeDisabled();
    await expect(page.getByRole('radio', { name: /^Medium/ })).toBeChecked();
    await expect(page.getByRole('spinbutton')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/nap-servicio-editor-${layout}.png`, fullPage: true });
    await page.getByLabel('Nombre del servicio').fill('Base de datos para prácticas');
    await page.getByLabel('Descripción para la cátedra').fill('Consultas SQL y ejercicios de modelado.');
    await page.getByRole('button', { name: 'Agregar servicio', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Base de datos para prácticas' })).toBeVisible();
    const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Base de datos para prácticas' }) });
    await card.getByRole('button', { name: 'Retirar', exact: true }).click();
    await page.getByRole('button', { name: 'Retirar del catálogo' }).click();
    await expect(page.getByRole('heading', { name: 'Base de datos para prácticas' })).toHaveCount(0);
    await page.getByLabel('Mostrar retirados').check();
    await expect(page.getByRole('heading', { name: 'Base de datos para prácticas' })).toBeVisible();
  });
}

test('las direcciones anteriores llevan a una única administración', async ({ page }) => {
  await mockAdmin(page);
  await page.goto('/templates');
  await expect(page).toHaveURL('/catalogo');
  await page.getByRole('button', { name: 'Administración', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Servicios del catálogo' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Catálogo', exact: true })).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'Perfiles', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Definiciones', exact: true })).toHaveCount(0);
});


test('el administrador solicita desde el mismo catálogo que administra', async ({ page }) => {
  await mockAdmin(page);
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Cátedra de prácticas' }] }));
  await page.route('**/api/v1/calendarios/*', (route) => route.fulfill({ json: { anio: 2027, periodos: [] } }));
  await page.goto('/catalogo');
  await expect(page.getByRole('button', { name: 'Agregar servicio', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Solicitar PostgreSQL', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expect(page.getByLabel('Servicio', { exact: true })).toHaveValue('2');
  await expect(page.getByLabel('Cátedra', { exact: true })).toHaveValue('1');
});

test('la cátedra conserva el catálogo de solicitudes sin administración', async ({ page }) => {
    const role = 'catedra_admin';
    await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 2, nombre: 'Docente', rol: role } } }));
    await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: initial }));
    await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/servicios/**', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/pedidos/**', (route) => route.fulfill({ json: [] }));
    const adminReads = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.includes('/definiciones') || url.pathname.endsWith('/tamanos') || url.searchParams.get('incluir_retiradas') === 'true') adminReads.push(url.pathname);
    });
    await page.goto('/catalogo');
    await expect(page.getByRole('button', { name: 'Solicitar PostgreSQL', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Agregar servicio', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Editar servicio' })).toHaveCount(0);
    await expect(page.getByLabel('Mostrar retirados')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Administración', exact: true })).toHaveCount(0);
    await page.goto('/admin/servicios');
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('button', { name: 'Agregar servicio', exact: true })).toHaveCount(0);
    expect(adminReads).toEqual([]);
});
