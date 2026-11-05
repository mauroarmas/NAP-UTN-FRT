import { test, expect } from './fixtures';

// 45 pedidos, del más reciente (id 45) al más antiguo (id 1), servidos de a `limit` con cursor, como la API real.
const TODOS = Array.from({ length: 45 }, (_, i) => ({
  id: 45 - i, tipo: 'alta', catedra_id: 1, template_id: 10, modelo_servicio: 'saas', estado: 'aprobado',
  servicio_id: null, descripcion_requerimientos: `Pedido de prueba ${45 - i}`, historial: [],
}));

async function preparar(page) {
  const consultas = [];
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { estado: 'operativo', usuario: { id: 1, nombre: 'Admin', rol: 'admin' } } }));
  await page.route('**/api/v1/auth/csrf', (route) => route.fulfill({ json: { csrf_token: 'fixture-csrf' } }));
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [{ id: 10, nombre: 'Docker App', tipo: 'lxc', modelo_servicio: 'saas' }] }));
  await page.route('**/api/v1/catedras/**', (route) => route.fulfill({ json: [{ id: 1, nombre: 'Cátedra 1' }] }));
  await page.route('**/api/v1/pedidos/**', (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.endsWith('/pedidos/')) return route.fulfill({ json: TODOS[0] });
    const q = (url.searchParams.get('q') || '').toLowerCase();
    const limit = Number(url.searchParams.get('limit') || 20);
    const desde = Number(url.searchParams.get('cursor') || 0);
    const filtrados = TODOS.filter((p) => !q || `#${p.id} ${p.descripcion_requerimientos}`.toLowerCase().includes(q));
    const items = filtrados.slice(desde, desde + limit);
    consultas.push({ q, limit, cursor: url.searchParams.get('cursor') });
    return route.fulfill({ json: { items, next_cursor: desde + limit < filtrados.length ? String(desde + limit) : null } });
  });
  await page.goto('/pedidos');
  return consultas;
}

test('el listado trae 20 pedidos y «Cargar más» agrega los siguientes hasta el final', async ({ page }) => {
  const consultas = await preparar(page);
  const lista = page.getByLabel('Listado de pedidos');
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(20);
  await expect(page.getByText('20+ pedidos')).toBeVisible();
  expect(consultas[0]).toMatchObject({ limit: 20, cursor: null });

  const mas = page.getByRole('button', { name: 'Cargar más pedidos' });
  await mas.click();
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(40);
  await mas.click();
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(45);
  await expect(mas).toHaveCount(0);
  await expect(page.getByText('45 pedidos')).toBeVisible();
  // el orden se conserva: del más reciente al más antiguo, sin repetidos
  const ids = await lista.locator('[data-pedido-id]').evaluateAll((nodos) => nodos.map((n) => Number(n.dataset.pedidoId)));
  expect(ids).toEqual(Array.from({ length: 45 }, (_, i) => 45 - i));
});

test('la búsqueda se hace en el servidor y reinicia la paginación', async ({ page }) => {
  const consultas = await preparar(page);
  const lista = page.getByLabel('Listado de pedidos');
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(20);
  await page.getByRole('button', { name: 'Cargar más pedidos' }).click();
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(40);

  // «Pedido de prueba 1» también coincide con 10..19, 21, 31, 41: se busca algo que sólo está en un pedido viejo
  await page.getByPlaceholder('Buscar por Nº, cátedra, servicio…').fill('prueba 3');
  await expect(lista.locator('[data-pedido-id]')).toHaveCount(11);       // 3, 30..39
  expect(consultas.at(-1)).toMatchObject({ q: 'prueba 3', cursor: null });  // pidió desde la primera página, con el texto
  await expect(page.getByRole('button', { name: 'Cargar más pedidos' })).toHaveCount(0);

  await page.getByPlaceholder('Buscar por Nº, cátedra, servicio…').fill('no existe');
  await expect(page.getByText('Ningún pedido coincide con la búsqueda.')).toBeVisible();
});
