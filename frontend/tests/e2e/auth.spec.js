import { test, expect } from './fixtures';

test('recargar onboarding no expone la navegación ni el portal', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'onboarding', usuario: { id: 1, nombre: 'Docente', debe_cambiar_password: true, totp_habilitado: false } } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Cambiar contraseña inicial' })).toBeVisible();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Cambiar contraseña inicial' })).toBeVisible();
});

test('cuenta sin MFA opera y salir confirma la petición de cierre', async ({ page }) => {
  let active = true;
  let closed = false;
  await page.route('**/api/v1/auth/me', (route) => route.fulfill(active ? { json: { estado: 'operativo', usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [], totp_habilitado: false } } } : { status: 401, json: {} }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
  await page.route('**/api/v1/auth/logout', (route) => {
    closed = true; active = false;
    expect(route.request().headers()['x-csrf-token']).toBe('fixture-csrf');
    return route.fulfill({ status: 204 });
  });
  await page.goto('/seguridad');
  await expect(page.getByRole('heading', { name: 'Seguridad de la cuenta' })).toBeVisible();
  await expect(page.getByText(/Estado actual: desactivado/)).toBeVisible();
  await page.getByRole('button', { name: 'Cuenta', exact: true }).click();
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ingresar', exact: true })).toBeVisible();
  expect(closed).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Usuario o Correo')).toBeVisible();
});
