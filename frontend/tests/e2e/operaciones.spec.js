import { test, expect } from './fixtures';

test('detalle sigue etapas reales y conserva acceso pendiente tras recargar', async ({ page }) => {
  const id = '33333333-3333-4333-8333-333333333333';
  let phase = 'tarea';
  let confirmed = false;
  const request = () => ({ id: 33, tipo: 'alta', catedra_id: 1, template_id: 18, modelo_servicio: 'saas',
    estado: 'en_despliegue', operation_id: confirmed ? null : id, servicio_id: confirmed ? 18 : null,
    descripcion_requerimientos: 'Diagramas para las prácticas.', historial: [] });
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/pedidos/**', route => route.fulfill({ json: new URL(route.request().url()).pathname.endsWith('/33') ? request() : [request()] }));
  await page.route('**/api/v1/templates/**', route => route.fulfill({ json: [{ id: 18, nombre: 'Draw.io', tipo: 'lxc', modelo_servicio: 'saas' }] }));
  await page.route('**/api/v1/catedras/**', route => route.fulfill({ json: [{ id: 1, nombre: 'Ingeniería de Software' }] }));
  await page.route(`**/api/v1/operaciones/${id}`, route => route.fulfill({ json: { operation_id: id, pedido_id: 33, tipo: 'desplegar', estado: confirmed ? 'confirmada' : 'en_curso', fase: phase } }));
  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Ver detalle', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
  phase = 'bootstrap';
  await expect(dialog.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');
  confirmed = true;
  await expect(dialog.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
  await expect(dialog.getByText('Servicio iniciado · acceso pendiente')).toBeVisible();
  await dialog.screenshot({ path: test.info().outputPath('avance-despliegue.png') });
  await expect(dialog.getByText('Servicio disponible', { exact: true })).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: 'Ver detalle', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
});

test('la campana abre directamente el pedido del aviso', async ({ page }) => {
  const request = { id: 33, tipo: 'alta', catedra_id: 1, template_id: 18, modelo_servicio: 'saas', estado: 'en_despliegue', servicio_id: 18, historial: [] };
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/alertas/avisos*', route => route.fulfill({ json: [{ id: 'aviso-33', pedido_id: 33,
    asunto: 'Pedido #33: servicio iniciado', texto: 'Falta comprobar el acceso.', created_at: '2026-10-26T15:00:00Z' }] }));
  await page.route('**/api/v1/pedidos/**', route => route.fulfill({ json: new URL(route.request().url()).pathname.endsWith('/33') ? request : [request] }));
  await page.route('**/api/v1/templates/**', route => route.fulfill({ json: [{ id: 18, nombre: 'Draw.io', tipo: 'lxc', modelo_servicio: 'saas' }] }));
  await page.route('**/api/v1/catedras/**', route => route.fulfill({ json: [{ id: 1, nombre: 'Ingeniería de Software' }] }));
  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Notificaciones (1 nuevas)' }).click();
  await page.getByRole('button', { name: /Pedido #33: servicio iniciado/ }).click();
  await expect(page).toHaveURL(/pedido=33/);
  await expect(page.getByRole('dialog')).toHaveAccessibleName('Pedido #33 — Draw.io');
  await expect(page.getByRole('dialog').getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
});

test('una operación incierta se consulta al recargar sin anunciar finalización', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 1, catedra_id: 1, template_id: 1, nombre_snapshot: 'Instancia', hostname: 'instancia', estado: 'stopped', modelo_servicio: 'iaas', operation_id: '11111111-1111-4111-8111-111111111111', disponibilidad_aplicacion: 'no_verificada' }] }));
  await page.route('**/api/v1/operaciones/11111111-1111-4111-8111-111111111111', (route) => route.fulfill({ json: { operation_id: '11111111-1111-4111-8111-111111111111', estado: 'incierta', tipo: 'iniciar', servicio_id: 1, fase: 'reconciliacion', error_detalle_seguro: 'Todavía no se confirmó el resultado' } }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.goto('/servicios');
  await expect(page.getByText(/Resultado incierto/).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Resultado incierto/).first()).toBeVisible();
  await expect(page.getByText('Servicio iniciado correctamente')).toHaveCount(0);
});


test('202 mantiene pendiente y bloquea otra orden hasta confirmación', async ({ page }) => {
  const operationId = '22222222-2222-4222-8222-222222222222';
  let admitted = false;
  let confirmed = false;
  let orders = 0;
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Docente', rol: 'catedra_admin', catedras: [{ id: 1, nombre: 'Propia' }] } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'test-csrf' } }));
  await page.route('**/api/v1/servicios/', (route) => route.fulfill({ json: [{ id: 1, catedra_id: 1, template_id: 1,
    hostname: 'instancia', estado: confirmed ? 'running' : 'stopped', modelo_servicio: 'iaas',
    operation_id: admitted && !confirmed ? operationId : null, disponibilidad_aplicacion: 'no_verificada',
    acciones_habilitadas: admitted && !confirmed ? [] : confirmed ? ['stop', 'restart', 'renovar'] : ['start', 'renovar'] }] }));
  await page.route('**/api/v1/operaciones?**', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route(`**/api/v1/operaciones/${operationId}`, (route) => route.fulfill({ json: {
    operation_id: operationId, tipo: 'iniciar', servicio_id: 1, estado: confirmed ? 'confirmada' : 'en_curso', fase: 'tarea' } }));
  await page.route('**/api/v1/servicios/1/start', async (route) => {
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    orders += 1;
    admitted = true;
    await route.fulfill({ status: 202, json: { operation_id: operationId, tipo: 'iniciar', servicio_id: 1, estado: 'pendiente' } });
  });
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Propia' }] }));
  await page.goto('/servicios');
  await page.getByRole('button', { name: 'Iniciar servicio', exact: true }).click();
  await expect(page.getByText(/Operación en curso/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Iniciar servicio', exact: true })).toBeDisabled();
  expect(orders).toBe(1);
  confirmed = true;
  await expect(page.getByText(/Efecto de infraestructura confirmado/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pausar / Detener servicio', exact: true })).toBeEnabled();
  expect(orders).toBe(1);
});

test('Draw.io abre en otro origen por POST sin mostrar otro login ni BookStack', async ({ page, context }) => {
  await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{estado:'operativo',usuario:{id:7,nombre:'Docente',rol:'catedra_admin'}}}));
  await page.route('**/api/v1/auth/csrf',route=>route.fulfill({json:{csrf_token:'test-csrf'}}));
  await page.route('**/api/v1/servicios/',route=>route.fulfill({json:[{id:18,catedra_id:1,nombre_snapshot:'Draw.io',hostname:'diagramas',estado:'running',modelo_servicio:'saas',acciones_habilitadas:[]}]}));
  await page.route('**/api/v1/templates/**',route=>route.fulfill({json:[]}));
  await page.route('**/api/v1/catedras/**',route=>route.fulfill({json:[{id:1,nombre:'Propia'}]}));
  await page.route('**/api/v1/servicios/18/acceso',route=>route.fulfill({json:{producto:'drawio',acceso_con_nap:true,puede_abrir_con_nap:true,instrucciones:'Abrí Draw.io con tu sesión de NAP.'}}));
  await page.route('**/api/v1/servicios/18/abrir-aplicacion',route=>route.fulfill({json:{destino:'https://app-18.apps.example.edu/_nap/entrar',codigo:'one-use-test-code'}}));
  let submissions=0;
  await context.route('https://app-18.apps.example.edu/**',route=>{
    expect(route.request().method()).toBe('POST');
    expect(route.request().postData()).toBe('codigo=one-use-test-code');
    expect(route.request().headers().origin).toBe('http://127.0.0.1:4173');
    submissions++;
    return route.fulfill({contentType:'text/html',body:'<!doctype html><title>Draw.io de prueba</title><h1>Editor simulado</h1>'});
  });
  await page.goto('/servicios');
  await page.getByRole('button',{name:'Ver acceso',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByText(/BookStack/)).toHaveCount(0);
  const opening=page.waitForEvent('popup');
  await dialog.getByRole('button',{name:'Abrir aplicación',exact:true}).click();
  const app=await opening;
  await expect(app.getByRole('heading',{name:'Editor simulado'})).toBeVisible();
  await expect(app).toHaveURL('https://app-18.apps.example.edu/_nap/entrar');
  expect(await app.evaluate(()=>window.opener===null)).toBe(true);
  expect(submissions).toBe(1);
});
