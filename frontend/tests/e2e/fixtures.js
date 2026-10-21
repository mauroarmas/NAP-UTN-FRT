import { test as base, expect } from '@playwright/test';

// Las rutas de cada escenario se registran después y tienen prioridad.
// Todo endpoint no simulado y toda origin externa quedan bloqueados.
export const test = base.extend({
  page: async ({ page, baseURL }, provide) => {
    if (process.env.NAP_E2E_INTEGRATION !== '1') {
      const origin = new URL(baseURL).origin;
      await page.route('**/*', async (route) => {
        const url = new URL(route.request().url());
        if (url.origin !== origin || url.pathname.startsWith('/api/')) {
          return route.abort('blockedbyclient');
        }
        return route.continue();
      });
    }
    if (process.env.NAP_E2E_INTEGRATION !== '1') {
      // Estado normal explícito de los avisos para recorridos de otras funciones.
      // Los escenarios de alertas pueden sobrescribirlo después.
      await page.route('**/api/v1/alertas**', (route) => route.fulfill({ json: [] }));
    }
    await provide(page);
  },
});
export { expect };
