import { test, expect } from './fixtures';

test('administración corrige otro año sin sobrescribir una revisión perdida', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  let changes = 0;
  const data = { anio: 2028, zona_horaria: 'America/Argentina/Tucuman', revision: 1,
    periodos: [{ tipo: 'primer_cuatrimestre', desde: '2028-03-01', hasta: '2028-06-30' }], faltantes: ['anual', 'segundo_cuatrimestre'] };
  await page.route('**/api/v1/calendarios/*', async (route) => {
    if (route.request().method() === 'PUT') {
      changes += 1;
      expect(route.request().postDataJSON().revision_esperada).toBe(1);
      return route.fulfill({ status: 409, json: { detail: { codigo: 'calendario_desactualizado', mensaje: 'El calendario cambió. Recargá antes de guardar.' } } });
    }
    return route.fulfill({ json: data });
  });
  await page.goto('/calendario');
  const year = page.getByLabel('Año lectivo');
  await year.fill('2028');
  await page.getByRole('button', { name: 'Consultar año' }).click();
  await expect(page.getByLabel('Fin del primer cuatrimestre')).toHaveValue('2028-06-30');
  await page.getByLabel('Fin del primer cuatrimestre').fill('2028-06-20');
  await page.getByRole('button', { name: 'Guardar calendario' }).click();
  await expect(page.getByText(/calendario cambió/)).toBeVisible();
  await expect(page.getByLabel('Fin del primer cuatrimestre')).toHaveValue('2028-06-20');
  expect(changes).toBe(1);
});

test('docente consulta ajustes sin cancelar ni reenviar su pedido', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 2, nombre: 'Docente', rol: 'catedra_admin' } } }));
  const pedido = { id: 10, catedra_id: 1, template_id: 1, estado: 'requiere_ajuste', modelo_servicio: 'iaas', observaciones_ajuste: 'Revisar las fechas con administración', historial: [] };
  await page.route('**/api/v1/pedidos/**', (route) => route.fulfill({ json: route.request().url().endsWith('/10') ? pedido : [pedido] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Linux', tipo: 'lxc' }] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Ver detalle' }).click();
  await expect(page.getByText('Revisar las fechas con administración')).toBeVisible();
  await expect(page.getByRole('button', { name: /reenviar|Cancelar solicitud/i })).toHaveCount(0);
});

test('receso conserva períodos y permite solicitar fechas sin encender', async ({ page }) => {
  await page.clock.install({ time: new Date('2027-07-15T12:00:00-03:00') });
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 2, nombre: 'Docente', rol: 'catedra_admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  const service = { id: 1, catedra_id: 1, template_id: 1, nombre_snapshot: 'Linux de la cátedra', estado: 'stopped',
    modelo_servicio: 'iaas', estado_cobertura: 'receso', cobertura_actual: false, proximo_inicio: '2027-08-01T03:00:00Z',
    acciones_habilitadas: ['renovar'], motivo_bloqueo: 'No hay cobertura en esta fecha',
    periodos_autorizados: [{ id: '11111111-1111-4111-8111-111111111111', desde: '2027-08-01', hasta: '2027-11-30', zona_horaria: 'America/Argentina/Tucuman' }] };
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [service] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.route('**/api/v1/calendarios/*', (route) => route.fulfill({ json: { anio: 2027, periodos: [] } }));
  let body;
  let starts = 0;
  await page.route('**/api/v1/servicios/1/start', (route) => { starts += 1; return route.fulfill({ status: 409, json: {} }); });
  await page.route('**/api/v1/servicios/1/renovar', (route) => {
    body = route.request().postDataJSON();
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    return route.fulfill({ status: 201, json: { pedido_id: 11, estado: 'solicitado' } });
  });
  await page.goto('/servicios');
  await expect(page.getByText(/En receso/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Iniciar servicio', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Opciones del servicio' }).click();
  await page.getByRole('button', { name: 'Solicitar renovación' }).click();
  await page.getByRole('button', { name: 'Rango Personalizado' }).click();
  await page.getByLabel('Fecha desde').fill('2028-03-01');
  await page.getByLabel('Fecha hasta').fill('2028-06-30');
  await page.getByRole('button', { name: 'Enviar solicitud de renovación' }).click();
  await expect(page.getByRole('status').filter({ hasText: /Solicitud de renovación/ })).toBeVisible();
  expect(body).toEqual({ vigencia: { tipo: 'personalizado', desde: '2028-03-01', hasta: '2028-06-30' } });
  expect(starts).toBe(0);
});

test('administración evalúa la selección explícita y conserva datos ante 409', async ({ page }) => {
  const dates = { tipo: 'personalizado', desde: '2027-03-01', hasta: '2027-06-30' };
  const request = { id: 12, catedra_id: 1, template_id: 1, modelo_servicio: 'iaas', estado: 'solicitado', vigencia: dates, historial: [] };
  const templates = [{ id: 1, nombre: 'Linux', tipo: 'lxc', modelo_servicio: 'iaas', activo: true, default_vcpus: 1, default_ram_mb: 512, default_disk_gb: 4 }];
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  await page.route('**/api/v1/pedidos/**', (route) => route.fulfill({ json: route.request().url().endsWith('/12') ? request : [request] }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: templates }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.route('**/api/v1/capacidad/', (route) => route.fulfill({ json: { destinos: [] } }));
  let evaluations = 0;
  await page.route('**/api/v1/pedidos/12/evaluacion', (route) => {
    evaluations += 1;
    const selection = route.request().postDataJSON();
    return route.fulfill({ json: { seleccion: selection, capacidad_token: 'token-' + evaluations,
      costo_incremental: selection.asignacion, justificacion_requerida: true, restricciones_fisicas: [] } });
  });
  await page.route('**/api/v1/pedidos/12/aprobar', (route) => {
    const body = route.request().postDataJSON();
    expect(body.asignacion.ram_mb).toBe(1024);
    expect(body.justificacion_capacidad).toBe('Justificación de la práctica');
    return route.fulfill({ status: 409, json: { detail: { codigo: 'token_desactualizado', mensaje: 'La capacidad cambió. Evaluá nuevamente.' } } });
  });
  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Ver detalle' }).click();
  expect(evaluations).toBe(0);
  await page.getByRole('button', { name: 'Revisar y aprobar…' }).click();
  await expect(page.locator('.dialog')).toHaveCount(1);
  await page.getByLabel('RAM (MiB)').fill('1024');
  await page.getByRole('button', { name: 'Evaluar asignación' }).click();
  await page.getByLabel('Justificación de sobreasignación').fill('Justificación de la práctica');
  await page.getByRole('button', { name: 'Aprobar asignación' }).click();
  await expect(page.getByRole('alert')).toContainText('La capacidad cambió');
  await expect(page.getByLabel('RAM (MiB)')).toHaveValue('1024');
  await expect(page.getByLabel('Fecha hasta')).toHaveValue('2027-06-30');
  await expect(page.getByRole('button', { name: 'Aprobar asignación' })).toBeDisabled();
  await page.getByRole('button', { name: 'Evaluar asignación' }).click();
  await expect(page.getByLabel('Justificación de sobreasignación')).toHaveValue('Justificación de la práctica');
  expect(evaluations).toBe(2);
});
