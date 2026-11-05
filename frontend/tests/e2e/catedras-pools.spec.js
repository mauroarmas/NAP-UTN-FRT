import { test, expect } from './fixtures';

test('cátedras muestra ID primero y verifica el pool sin efectos, conservando el fallo visible', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/usuarios/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/', (route) => route.fulfill({ json: [
    { id: 91, nombre: 'Bases de Datos', activa: true, titular: { nombre: 'Docente' } },
  ] }));
  let reads = 0;
  await page.route('**/api/v1/catedras/91/infraestructura', (route) => {
    expect(route.request().method()).toBe('GET');
    reads += 1;
    if (reads > 1) return route.fulfill({ status: 502, json: {} });
    return route.fulfill({ json: { pool: 'catedra-91', estado: 'preparada', mensaje: 'Pool y permisos comprobados.' } });
  });
  await page.goto('/catedras');
  await expect(page.locator('thead th').first()).toHaveText('ID');
  await expect(page.locator('tbody tr').first().locator('td').first()).toHaveText('91');
  await expect(page.getByText('Sin verificar', { exact: true })).toBeVisible();
  expect(reads).toBe(0);
  const trigger = page.getByRole('button', { name: 'Verificar infraestructura de Bases de Datos', exact: true });
  await trigger.focus(); await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Infraestructura de Bases de Datos' });
  await expect(dialog.getByText('Pool y permisos comprobados.')).toBeVisible();
  await expect(dialog.getByText(/Esta consulta no crea pools/)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(page.locator('tbody').getByText('Preparada', { exact: true })).toBeVisible();
  await trigger.click();
  await expect(dialog.getByRole('alert')).toHaveText(/No se pudo verificar/);
  await expect(page.locator('tbody').getByText('Requiere atención', { exact: true })).toBeAttached();
  await expect(page.locator('tbody').getByText('Preparada', { exact: true })).toHaveCount(0);
});
