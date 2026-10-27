import { test, expect } from './fixtures';

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
  await expect(page.getByLabel('Servicio', { exact: true })).toHaveValue('2');
  await expect(page.getByText('image-internal-only')).toHaveCount(0);
  await expect(page.getByText('No publicada', { exact: true })).toHaveCount(0);
  await expect(page.getByText('QEMU histórico', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Rango Personalizado' }).click();
  await page.getByLabel('Fecha desde').fill('2027-03-01');
  await page.getByLabel('Fecha hasta').fill('2027-06-30');
  await page.getByLabel('Nombre de la solicitud').fill('Prácticas de consultas');
  await page.getByLabel('Justificación pedagógica').fill('Ejercicios de consultas para estudiantes de la cátedra.');
  await page.getByRole('button', { name: 'Enviar solicitud' }).click();
  await expect(page.getByRole('status')).toHaveText(/Solicitud #20 registrada/);
  expect(submitted).toEqual({ modelo_servicio: 'paas', template_id: 2, catedra_id: 1,
    descripcion_requerimientos: 'Ejercicios de consultas para estudiantes de la cátedra.',
    parametros_extra: { titulo: 'Prácticas de consultas', software_solicitado: null },
    vigencia: { tipo: 'personalizado', desde: '2027-03-01', hasta: '2027-06-30' } });
});
