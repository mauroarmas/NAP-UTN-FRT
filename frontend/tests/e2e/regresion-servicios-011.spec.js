import { test, expect } from './fixtures';

/**
 * Pruebas E2E de regresión transversal para feature 011 (T099).
 *
 * Verifica que los recorridos de usuario, cátedra, pedidos, IaaS, Draw.io
 * y renovaciones se mantengan funcionales e intactos tras incorporar el
 * nuevo motor OCI y catálogo unificado.
 */

test.describe('Regresión transversal de servicios (011)', () => {
  test('catálogo muestra IaaS y aplicaciones sin exigir datos técnicos ni UUID', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        json: {
          estado: 'operativo',
          usuario: { id: 1, nombre: 'Admin', rol: 'admin' },
        },
      })
    );
    await page.route('**/api/v1/auth/csrf', (route) =>
      route.fulfill({ json: { csrf_token: 'test-csrf' } })
    );

    const templates = [
      {
        id: 1,
        nombre: 'Ubuntu 24.04',
        descripcion: 'Sistema operativo Linux Ubuntu para cátedras.',
        tipo: 'lxc',
        modelo_servicio: 'iaas',
        activo: true,
        oferta_disponible: true,
        tamanos_permitidos: ['small', 'medium'],
        tamano_recomendado: 'small',
      },
      {
        id: 2,
        nombre: 'Debian 13',
        descripcion: 'Sistema operativo Linux Debian para prácticas.',
        tipo: 'lxc',
        modelo_servicio: 'iaas',
        activo: true,
        oferta_disponible: true,
        tamanos_permitidos: ['small', 'medium'],
        tamano_recomendado: 'small',
      },
      {
        id: 3,
        nombre: 'Draw.io',
        descripcion: 'Diagramas de arquitectura y flujo.',
        tipo: 'lxc',
        modelo_servicio: 'saas',
        activo: true,
        oferta_disponible: true,
        tamanos_permitidos: ['medium'],
        tamano_recomendado: 'medium',
      },
    ];

    await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: templates }));
    await page.route('**/api/v1/catedras/**', (route) =>
      route.fulfill({ json: [{ id: 1, nombre: 'Sistemas Operativos' }] })
    );
    await page.route('**/api/v1/definiciones**', (route) => route.fulfill({ json: [] }));

    await page.goto('/admin/servicios');
    await expect(page.getByRole('heading', { name: 'Catálogo de servicios' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ubuntu 24.04', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Debian 13', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Draw.io', exact: true })).toBeVisible();

    // No debe haber UUIDs ni tecnicismos crudos visibles en el catálogo
    const content = await page.textContent('body');
    expect(content).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  });

  test('ver acceso en Draw.io abre gateway NAP sin exponer credenciales no autorizadas', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        json: {
          estado: 'operativo',
          usuario: {
            id: 2,
            nombre: 'Docente Redes',
            rol: 'catedra_admin',
            catedras: [{ id: 1, nombre: 'Redes y Comunicaciones' }],
          },
        },
      })
    );
    await page.route('**/api/v1/auth/csrf', (route) =>
      route.fulfill({ json: { csrf_token: 'test-csrf' } })
    );

    const servicioDrawio = {
      id: 10,
      catedra_id: 1,
      template_id: 3,
      nombre_snapshot: 'Draw.io - Redes',
      modelo_servicio: 'saas',
      estado: 'running',
      cobertura_actual: true,
      estado_cobertura: 'con_cobertura',
      disponibilidad_aplicacion: 'utilizable',
      acciones_habilitadas: [],
      vcpus_asignados: 2,
      ram_asignada_mb: 1024,
      disk_asignado_gb: 8,
    };

    await page.route((url) => url.pathname === '/api/v1/servicios/', (route) =>
      route.fulfill({ json: [servicioDrawio] })
    );
    await page.route('**/api/v1/catedras/**', (route) =>
      route.fulfill({ json: [{ id: 1, nombre: 'Redes y Comunicaciones' }] })
    );
    await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/operaciones?**', (route) =>
      route.fulfill({ json: { items: [], next_cursor: null } })
    );

    await page.route('**/api/v1/servicios/10/acceso**', (route) => {
      return route.fulfill({
        json: {
          servicio_id: 10,
          producto: 'drawio',
          metodo: 'https',
          estado_entrega: 'entregado',
          disponibilidad: 'utilizable',
          direccion: 'https://app-10.nap-apps.test:8443',
          puede_revelar_credenciales: false,
          instrucciones: 'Accedé mediante el gateway seguro HTTPS de NAP.',
        },
      });
    });

    await page.goto('/servicios');
    const accessBtn = page.getByRole('button', { name: 'Ver acceso', exact: true });
    await expect(accessBtn).toBeVisible();
    await accessBtn.click();

    // Modal de acceso seguro
    await expect(page.getByText('Accedé mediante el gateway seguro HTTPS de NAP.')).toBeVisible();
    await expect(page.getByText('https://app-10.nap-apps.test:8443')).toBeVisible();
  });

  test('servicio IaaS en running ofrece consulta de consola Proxmox independiente de operaciones', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        json: {
          estado: 'operativo',
          usuario: { id: 1, nombre: 'Admin', rol: 'admin' },
        },
      })
    );
    await page.route('**/api/v1/auth/csrf', (route) =>
      route.fulfill({ json: { csrf_token: 'test-csrf' } })
    );

    const servicioIaaS = {
      id: 20,
      catedra_id: 1,
      template_id: 1,
      nombre_snapshot: 'Ubuntu Servidor Prácticas',
      modelo_servicio: 'iaas',
      estado: 'running',
      cobertura_actual: true,
      estado_cobertura: 'con_cobertura',
      disponibilidad_aplicacion: 'utilizable',
      acciones_habilitadas: [],
      vcpus_asignados: 1,
      ram_asignada_mb: 512,
      disk_asignado_gb: 4,
      proxmox_vmid: 300,
      proxmox_node: 'pve1',
    };

    await page.route((url) => url.pathname === '/api/v1/servicios/', (route) =>
      route.fulfill({ json: [servicioIaaS] })
    );
    await page.route('**/api/v1/catedras/**', (route) =>
      route.fulfill({ json: [{ id: 1, nombre: 'Sistemas Operativos' }] })
    );
    await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/operaciones?**', (route) =>
      route.fulfill({ json: { items: [], next_cursor: null } })
    );

    await page.route('**/api/v1/servicios/20/acceso**', (route) =>
      route.fulfill({
        json: {
          servicio_id: 20,
          producto: 'linux',
          metodo: 'consola',
          estado_entrega: 'entregado',
          disponibilidad: 'utilizable',
          instrucciones: 'El acceso se realiza mediante la consola administrativa de Proxmox.',
        },
      })
    );

    await page.route('**/api/v1/servicios/20/consola', (route) =>
      route.fulfill({
        json: {
          url: 'https://pve1.example.edu:8006/?console=lxc&xtermjs=1&vmid=300&node=pve1',
          servicio_id: 20,
          vmid: 300,
          node: 'pve1',
        },
      })
    );

    await page.goto('/servicios');
    await expect(page.getByText('Ubuntu Servidor Prácticas')).toBeVisible();

    // Ver acceso
    const accessBtn = page.getByRole('button', { name: 'Ver acceso', exact: true });
    await expect(accessBtn).toBeVisible();
    await accessBtn.click();

    // En el modal de acceso, consultar consola
    const consultarConsolaBtn = page.getByRole('button', { name: 'Consultar consola' });
    await expect(consultarConsolaBtn).toBeVisible();
    await consultarConsolaBtn.click();

    // Aparece el enlace seguro para abrir la consola de la instancia en Proxmox
    const openConsoleLink = page.getByRole('link', { name: 'Abrir consola de esta instancia' });
    await expect(openConsoleLink).toBeVisible();
    await expect(openConsoleLink).toHaveAttribute(
      'href',
      'https://pve1.example.edu:8006/?console=lxc&xtermjs=1&vmid=300&node=pve1'
    );
  });

  test('solicitud de renovación conserva servicio y modal explica retención de datos', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        json: {
          estado: 'operativo',
          usuario: {
            id: 2,
            nombre: 'Docente SO',
            rol: 'catedra_admin',
            catedras: [{ id: 1, nombre: 'Sistemas Operativos' }],
          },
        },
      })
    );
    await page.route('**/api/v1/auth/csrf', (route) =>
      route.fulfill({ json: { csrf_token: 'test-csrf' } })
    );

    const servicioVenciendo = {
      id: 30,
      catedra_id: 1,
      template_id: 1,
      nombre_snapshot: 'Ubuntu Laboratorio',
      modelo_servicio: 'iaas',
      estado: 'running',
      cobertura_actual: true,
      estado_cobertura: 'con_cobertura',
      vence_at: '2026-11-05T00:00:00Z',
      acciones_habilitadas: ['renovar'],
      vcpus_asignados: 1,
      ram_asignada_mb: 512,
      disk_asignado_gb: 4,
    };

    await page.route((url) => url.pathname === '/api/v1/servicios/', (route) =>
      route.fulfill({ json: [servicioVenciendo] })
    );
    await page.route('**/api/v1/catedras/**', (route) =>
      route.fulfill({ json: [{ id: 1, nombre: 'Sistemas Operativos' }] })
    );
    await page.route('**/api/v1/templates/**', (route) => route.fulfill({ json: [] }));
    await page.route('**/api/v1/operaciones?**', (route) =>
      route.fulfill({ json: { items: [], next_cursor: null } })
    );

    await page.goto('/servicios');
    await page.getByRole('button', { name: 'Opciones del servicio' }).click();

    const renovarBtn = page.getByRole('button', { name: 'Solicitar renovación' });
    await expect(renovarBtn).toBeVisible();
    await renovarBtn.click();

    // Modal de renovación
    const modal = page.getByRole('dialog', { name: 'Solicitar renovación' });
    await expect(modal).toBeVisible();
    await expect(
      modal.getByText('La solicitud requiere aprobación. Conserva el contenedor y sus datos')
    ).toBeVisible();

    // Cerrar modal
    await modal.getByRole('button', { name: 'Cerrar', exact: true }).first().click();
    await expect(modal).toHaveCount(0);
    // El servicio continúa intacto en pantalla
    await expect(page.getByText('Ubuntu Laboratorio')).toBeVisible();
  });
});
