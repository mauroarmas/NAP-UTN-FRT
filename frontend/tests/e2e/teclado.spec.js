import { test, expect } from './fixtures';

async function prepare(page) {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo',
    usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
  await page.route((url) => url.pathname === '/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 1, catedra_id: 1,
    nombre_snapshot: 'Libro de teclado', modelo_servicio: 'saas', estado: 'running',
    vcpus_asignados: 1, ram_asignada_mb: 1024, disk_asignado_gb: 8, acciones_habilitadas: [] }] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route('**/api/v1/servicios/1/acceso', (route) => route.fulfill({ json: {
    puede_revelar_credenciales: true, estado_entrega: 'entregado', instrucciones: 'Acceso de prueba', metodo: 'https' } }));
  await page.route('**/api/v1/servicios/1/acceso/revelar', (route) => route.fulfill({ json: {
    metodo: 'https', credenciales: { usuario: 'fixture@example.org', password: 'fixture-only' } } }));
  await page.goto('/servicios');
}

test('teclado abre, confina foco, bloquea fondo y devuelve foco al cerrar', async ({ page }) => {
  await prepare(page);
  const trigger = page.getByRole('button', { name: 'Ver acceso' });
  await trigger.focus();
  const backgroundTrigger = await trigger.elementHandle();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Acceso: Libro de teclado' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-modal', 'true');
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  // El fondo debe quedar inerte en el navegador, no solo cubierto visualmente.
  expect(await backgroundTrigger.evaluate((el) => Boolean(el.closest('[inert]')))).toBe(true);
  await expect(trigger).toHaveCount(0);
  const buttons = dialog.getByRole('button');
  await buttons.last().focus();
  await page.keyboard.press('Tab');
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await buttons.first().focus();
  await page.keyboard.press('Shift+Tab');
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  expect(await trigger.evaluate((el) => Boolean(el.closest('[inert]')))).toBe(false);
});

test('filtro por modelo se opera con teclado y Clipboard denegado muestra fallo', async ({ page }) => {
  await prepare(page);
  const filter = page.getByRole('combobox', { name: 'Filtrar por tipo de servicio' });
  await filter.focus();
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await expect(filter).toHaveValue('saas');
  await expect(page.getByText('Libro de teclado', { exact: true })).toBeVisible();
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async () => { throw new DOMException('Denied', 'NotAllowedError'); } } }));
  await page.getByRole('button', { name: 'Ver acceso' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Revelar acceso inicial' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Copiar contraseña' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByText(/Contraseña copiada/)).toHaveCount(0);
});
