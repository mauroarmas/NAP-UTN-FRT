import { test, expect } from './fixtures';

async function prepare(page, rol = 'admin') {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Prueba', rol } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
  await page.route((url) => url.pathname === '/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 7, catedra_id: 1,
    nombre_snapshot: 'Recurso histórico', tipo: 'lxc', modelo_servicio: 'iaas', estado: 'paused', vcpus_asignados: 2,
    ram_asignada_mb: 1024, disk_asignado_gb: 20, regularizacion_pendiente: true, regularizacion_legacy: true, acciones_habilitadas: [] }] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Prueba' }] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/pedidos/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route('**/api/v1/servicios/7/regularizacion/evaluar', (route) => route.fulfill({ json: { servicio_id: 7,
    fuente_sha256: 'a'.repeat(64), puede_regularizar: true, motivos: [], nombre: 'Recurso histórico', modelo_servicio: 'iaas',
    desde: null, hasta: null, zona_horaria: 'America/Argentina/Tucuman', conflictos: [],
    asignacion_observada: { vcpus: 2, ram_mb: 1024, disk_gb: 20 }, estado_observado: 'stopped' } }));
  await page.goto('/servicios');
}

test('regularización respeta teclado, doble Enter, bloqueo al guardar y retorno de foco', async ({ page }) => {
  await prepare(page);
  const trigger = page.getByRole('button', { name: 'Regularizar registro', exact: true });
  await trigger.focus(); await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Regularizar registro histórico' });
  await expect(dialog.getByText(/Configuración comprobada/)).toBeVisible();
  await expect(dialog.getByLabel('Fecha inicial respaldada')).toHaveValue('');
  await expect(dialog.getByLabel('Fecha final respaldada')).toHaveValue('');
  await dialog.getByLabel('Fecha inicial respaldada').fill('2026-10-21');
  await dialog.getByLabel('Fecha final respaldada').fill('2026-11-21');
  await dialog.getByLabel('Referencia del respaldo').fill('ACTA-PRUEBA');
  await dialog.getByLabel('Motivo de la decisión').fill('Fechas corroboradas');
  let finish; let calls = 0;
  const pending = new Promise((resolve) => { finish = resolve; });
  await page.route('**/api/v1/servicios/7/regularizacion', async (route) => {
    calls += 1; await pending;
    await route.fulfill({ json: { servicio_id: 7, disponibilidad_aplicacion: 'no_verificada' } });
  });
  const save = dialog.getByRole('button', { name: 'Confirmar regularización' });
  await save.focus(); await page.keyboard.press('Enter'); await page.keyboard.press('Enter');
  await expect.poll(() => calls).toBe(1);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Fecha inicial respaldada')).toBeDisabled();
  const closeButtons = dialog.getByRole('button', { name: 'Cerrar', exact: true });
  await expect(closeButtons).toHaveCount(2);
  for (const closeButton of await closeButtons.all()) await expect(closeButton).toBeDisabled();
  finish();
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.getByRole('status').filter({ hasText: 'El acceso sigue sin verificar' })).toBeVisible();
  expect(calls).toBe(1);
});

test('el responsable de cátedra no recibe la gestión administrativa del legado', async ({ page }) => {
  await prepare(page, 'catedra_admin');
  await expect(page.getByText('Recurso histórico', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Regularizar registro' })).toHaveCount(0);
});
