// Prueba optativa real. No usar fixtures.js: las consultas no se sustituyen.
import { test, expect } from '@playwright/test';
import { runPerformance } from '../../scripts/validar_rendimiento.mjs';

test('SC-008: diez contextos, PostgreSQL completo y despliegue pendiente', async ({browser}) => {
  test.setTimeout(600_000);
  test.skip(!process.env.NAP_PERFORMANCE_CONFIG,'Requiere laboratorio aislado explícito');
  const result=await runPerformance(browser,{
    configPath:process.env.NAP_PERFORMANCE_CONFIG,
    outputPath:process.env.NAP_PERFORMANCE_OUTPUT || '../docs/evidencia/009/rendimiento-navegador.json',
  });
  expect(result.fatal_error).toBeNull();
  expect(result.passed).toBe(true);
});
