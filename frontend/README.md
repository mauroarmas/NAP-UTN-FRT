# React + Vite

## Pruebas del portal

La imagen frontend fija Node 22.23.3 mediante el digest oficial
`sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402`,
comprobado con imagetools y ejecutando node --version el 2026-10-20.
Se exige Node de rama 22 >=22.12 para reproducir CI. Las herramientas de prueba
se fijan por versión exacta y package-lock.json registra sus integridades.

Desde frontend:

```bash
npm ci
npm test -- --run
npx playwright install chromium
npm run test:e2e
npm run lint
npm run build
```

Vitest usa jsdom/Testing Library y bloquea fetch/XHR sin simular. Las pruebas
Playwright importan test/expect de tests/e2e/fixtures.js: solo se permiten recursos
estáticos de la SPA local y endpoints simulados por el caso. La suite compila la
SPA y arranca preview en 127.0.0.1:4173, sin reutilizar servidores ajenos.

En un entorno con permisos de escritura restringidos se puede instalar el browser
en /tmp con PLAYWRIGHT_BROWSERS_PATH=/tmp/nap009-playwright, usando esa misma
variable al ejecutar test:e2e. La apertura del puerto local/browser puede requerir
ejecución fuera del sandbox. CI instala también las dependencias de sistema.

Una integración real necesita NAP_E2E_INTEGRATION=1 y NAP_E2E_BASE_URL explícita
hacia un destino aislado; nunca ejecutar pruebas de escritura contra el portal de
uso real. El ensayo de rendimiento en navegador se implementa en T118 y no se
acredita con este smoke test ni con npm build.

### Sesiones de la feature 009

El cliente consulta `/api/v1/auth/me` al cargar y no interpreta perfiles ni JWT
heredados de Web Storage. Opera con cookie HttpOnly y CSRF en la misma origin;
configurar `NAP_BACKEND_PROXY` en Vite para desarrollo. En operación, el reverse
proxy sirve `/api` junto a la SPA. No se usa `VITE_API_URL` para un backend externo.

Las etapas de cambio inicial, TOTP y recuperación reemplazan al portal hasta
completar los requisitos. La página Seguridad permite elegir 2FA, reemplazarlo,
regenerar códigos o desactivarlo con pruebas nuevas. Los códigos se muestran en
memoria una vez para guardarlos fuera del portal; nunca se persisten localmente.
Un 403 de CSRF conserva el formulario y solicita reenvío con el token vigente;
no se repiten mutaciones automáticamente.

## Medición de rendimiento

`npm run test:performance -- --config /ruta/privada/configuracion.json --execute`
compila y mide la SPA contra el laboratorio aislado. Requiere API8044 y el
fixture completo, siguiendo [la guía](../docs/evidencia/009/rendimiento-laboratorio.md).
No utiliza respuestas API simuladas. El test optativo equivalente usa
`playwright.performance.config.js`; está excluido de la suite funcional normal.
