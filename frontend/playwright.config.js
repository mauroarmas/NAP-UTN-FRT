import { defineConfig, devices } from '@playwright/test';

const externalURL = process.env.NAP_E2E_BASE_URL;
if (externalURL && process.env.NAP_E2E_INTEGRATION !== '1') {
  throw new Error('NAP_E2E_BASE_URL requiere NAP_E2E_INTEGRATION=1 y un destino aislado de prueba');
}

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: '**/rendimiento.spec.js',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: externalURL || 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: externalURL ? undefined : {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
