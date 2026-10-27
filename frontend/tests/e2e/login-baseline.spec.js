import { test, expect } from './fixtures.js';

test('una visita sin sesión muestra el ingreso con los campos identificados', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ status: 401, json: {} }));
  await page.goto('/');
  await expect(page.getByLabel('Usuario o Correo')).toBeVisible();
  await expect(page.getByLabel('Contraseña')).toHaveAttribute('type', 'password');
  await expect(page.getByRole('button', { name: 'Ingresar', exact: true })).toBeEnabled();
});
