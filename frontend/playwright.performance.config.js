import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests/e2e',testMatch:'rendimiento.spec.js',retries:0,workers:1,
  use:{baseURL:'http://localhost:4174',trace:'off',video:'off',screenshot:'off'},
  // API8044 se prepara antes siguiendo la guía; nunca usar un servidor operativo.
  webServer:{command:'npm run build && npm run preview -- --host 127.0.0.1 --port 4174 --strictPort',
    env:{NAP_BACKEND_PROXY:'http://127.0.0.1:8044'},url:'http://localhost:4174',reuseExistingServer:false},
});
