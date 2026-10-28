import { test, expect } from './fixtures';

/**
 * Pruebas E2E de despliegue de aplicaciones y consola operativa (US4 - T086).
 *
 * Los casos de esta suite utilizan backend simulado mediante intercepción
 * de rutas de Playwright (`page.route`), garantizando reproducibilidad sin
 * depender de conectividad real a Proxmox ni del nodo en este nivel.
 */

const opId = '44444444-4444-4444-8444-444444444444';

const baseConsolaResponse = {
  operation_id: opId,
  operacion_raiz_id: opId,
  estado: 'en_curso',
  fase: 'instalacion',
  intento_efectivo: 1,
  items: [
    {
      seq: 1,
      intento: 1,
      captured_at: '2026-10-27T10:00:00Z',
      fase: 'creacion',
      stream: 'sistema',
      texto_depurado: 'Creando recurso de aplicación.',
    },
    {
      seq: 2,
      intento: 1,
      captured_at: '2026-10-27T10:00:01Z',
      fase: 'instalacion',
      stream: 'stdout',
      texto_depurado: '<script>alert("xss")</script> \\033[31mcolores\\033[0m',
    },
  ],
  next_cursor: 2,
  previous_cursor: 1,
  has_more: false,
  first_retained_seq: 1,
  last_seq: 2,
  truncated: false,
  expired: false,
  dropped_messages: 0,
  last_captured_at: '2026-10-27T10:00:01Z',
  last_ingested_at: '2026-10-27T10:00:02Z',
  resultado_final: null,
};

test('admin puede abrir la consola de despliegue desde Pedidos y ver texto literal seguro', async ({ page }) => {
  // Backend simulado
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      json: {
        estado: 'operativo',
        usuario: { id: 1, nombre: 'Admin', rol: 'admin' },
      },
    })
  );

  const pedido = {
    id: 42,
    tipo: 'alta',
    catedra_id: 1,
    template_id: 10,
    modelo_servicio: 'saas',
    estado: 'en_despliegue',
    operation_id: opId,
    servicio_id: null,
    descripcion_requerimientos: 'Laboratorio de pruebas.',
    historial: [],
  };

  await page.route('**/api/v1/pedidos/**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/42') ? pedido : [pedido],
    })
  );

  await page.route('**/api/v1/templates/**', (route) =>
    route.fulfill({
      json: [{ id: 10, nombre: 'Docker App', tipo: 'lxc', modelo_servicio: 'saas' }],
    })
  );

  await page.route('**/api/v1/catedras/**', (route) =>
    route.fulfill({
      json: [{ id: 1, nombre: 'Sistemas Operativos' }],
    })
  );

  await page.route(`**/api/v1/operaciones/${opId}/consola*`, (route) =>
    route.fulfill({
      json: baseConsolaResponse,
      headers: { 'Cache-Control': 'no-store' },
    })
  );

  await page.route(`**/api/v1/operaciones/${opId}`, (route) =>
    route.fulfill({
      json: {
        operation_id: opId,
        pedido_id: 42,
        tipo: 'desplegar',
        estado: 'en_curso',
        fase: 'instalacion',
      },
    })
  );

  await page.goto('/pedidos');

  // Abrir detalle del pedido
  await page.getByRole('button', { name: 'Ver detalle', exact: true }).click();
  const detalleDialog = page.getByRole('dialog');
  await expect(detalleDialog).toBeVisible();

  // Botón "Ver consola" visible para admin
  const btnConsola = detalleDialog.getByRole('button', { name: 'Ver consola' });
  await expect(btnConsola).toBeVisible();
  await btnConsola.click();

  // La consola se abre en diálogo dedicado
  const consolaDialog = page.getByRole('dialog', { name: 'Consola de operación' });
  await expect(consolaDialog).toBeVisible();

  // Comprobar contenido literal seguro (sin ejecución de script)
  await expect(consolaDialog.getByText('Creando recurso de aplicación.')).toBeVisible();
  await expect(
    consolaDialog.getByText('<script>alert("xss")</script>')
  ).toBeVisible();

  // Cerrar consola y comprobar que no altera el estado del pedido
  await consolaDialog.getByRole('button', { name: 'Cerrar consola' }).click();
  await expect(consolaDialog).not.toBeVisible();
  await expect(detalleDialog).toBeVisible();
});

test('la consola maneja pérdida de autorización (403) limpiando el buffer', async ({ page }) => {
  // Backend simulado
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      json: {
        estado: 'operativo',
        usuario: { id: 1, nombre: 'Admin', rol: 'admin' },
      },
    })
  );

  const pedido = {
    id: 43,
    tipo: 'alta',
    catedra_id: 1,
    template_id: 10,
    modelo_servicio: 'saas',
    estado: 'en_despliegue',
    operation_id: opId,
    servicio_id: null,
    descripcion_requerimientos: 'Prueba de permisos.',
    historial: [],
  };

  await page.route('**/api/v1/pedidos/**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/43') ? pedido : [pedido],
    })
  );
  await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/catedras/**', (route) =>
    route.fulfill({ json: [{ id: 1, nombre: 'Cátedra 1' }] })
  );

  let primeraConsulta = true;
  await page.route(`**/api/v1/operaciones/${opId}/consola*`, (route) => {
    if (primeraConsulta) {
      primeraConsulta = false;
      return route.fulfill({ json: baseConsolaResponse, headers: { 'Cache-Control': 'no-store' } });
    }
    // Revocación de permisos en la siguiente consulta
    return route.fulfill({
      status: 403,
      json: { detail: { codigo: 'acceso_denegado', mensaje: 'Acceso denegado' } },
    });
  });

  await page.route(`**/api/v1/operaciones/${opId}`, (route) =>
    route.fulfill({
      json: { operation_id: opId, pedido_id: 43, tipo: 'desplegar', estado: 'en_curso', fase: 'instalacion' },
    })
  );

  await page.goto('/pedidos');
  await page.getByRole('button', { name: 'Ver detalle', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Ver consola' }).click();

  const consolaDialog = page.getByRole('dialog', { name: 'Consola de operación' });
  await expect(consolaDialog).toBeVisible();

  // Al revocar permisos, el buffer se limpia y aparece el mensaje de error
  await expect(consolaDialog.getByText(/Acceso revocado/i)).toBeVisible({ timeout: 5000 });
  await expect(consolaDialog.getByText('Creando recurso de aplicación.')).toHaveCount(0);
});

