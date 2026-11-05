import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium, defineConfig, devices } from '@playwright/test';

const externalURL = process.env.NAP_E2E_BASE_URL;
if (externalURL && process.env.NAP_E2E_INTEGRATION !== '1') {
  throw new Error('NAP_E2E_BASE_URL requiere NAP_E2E_INTEGRATION=1 y un destino aislado de prueba');
}

function resolveChromiumExecutable() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  try {
    const defaultPath = chromium.executablePath();
    if (defaultPath && existsSync(defaultPath)) return undefined;
  } catch {}
  try {
    const cacheDir = join(homedir(), '.cache', 'ms-playwright');
    const dirs = readdirSync(cacheDir)
      .filter((d) => d.startsWith('chromium_headless_shell-'))
      .sort()
      .reverse();
    for (const dir of dirs) {
      const candidate = join(cacheDir, dir, 'chrome-headless-shell-linux64', 'chrome-headless-shell');
      if (existsSync(candidate)) return candidate;
    }
  } catch {}
  return undefined;
}

const executablePath = resolveChromiumExecutable();

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
  projects: [{
    name: 'chromium',
    use: {
      ...devices['Desktop Chrome'],
      ...(executablePath ? { launchOptions: { executablePath } } : {}),
    },
  }],
  webServer: externalURL ? undefined : {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
