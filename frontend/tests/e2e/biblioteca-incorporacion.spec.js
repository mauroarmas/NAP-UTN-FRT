import { test, expect } from './fixtures';

test('admin incorpora por categoría sin instalar y conserva edición', async ({page})=>{
  await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{estado:'operativo',usuario:{id:1,nombre:'Admin',rol:'admin'}}}));
  await page.route('**/api/v1/auth/csrf',route=>route.fulfill({json:{csrf_token:'test-csrf'}}));
  await page.route('**/api/v1/definiciones**',route=>route.fulfill({json:[]}));
  const item={identidad_externa:'ct/drawio.sh',nombre:'Draw.io',revision_fuente:'a'.repeat(40),comando_origen:'Comando informativo del proveedor',url_origen:'https://community-scripts.org/scripts/drawio',compatibilidad:'adaptador_disponible',faltantes:['version'],revision:1};
  let draft;
  const attempts=[];
  await page.route('**/api/v1/biblioteca/**',route=>{
    const request=route.request();
    if(request.url().endsWith('/preparacion'))return route.fulfill({json:{estado:'sin_preparar',puede_preparar:false,mensaje:'Falta completar la conexión con Proxmox.',recursos:[]}});
    if(request.url().includes('/aplicaciones'))return route.fulfill({json:{items:[item],fuente:{estado:'disponible'}}});
    if(request.method()==='POST'){
      expect(request.headers()['idempotency-key']).toBeTruthy();
      attempts.push(request.headers()['idempotency-key']);
      if(attempts.length===1)return route.fulfill({status:500,json:{detail:{mensaje:'No se pudo guardar la ficha.'}}});
      draft ||= {...item,id:'11111111-1111-4111-8111-111111111111'};
      return route.fulfill({status:201,json:draft});
    }
    if(request.method()==='PATCH'){
      draft={...draft,...request.postDataJSON(),revision:2};
      return route.fulfill({json:draft});
    }
    if (draft && request.url().endsWith('/'+draft.id)) return route.fulfill({json:{...draft,definiciones:[]}});
    return route.fulfill({json:{items:draft?[draft]:[]}});
  });
  await page.route('**/api/v1/templates/?incluir_retiradas=true',r=>r.fulfill({json:[]}));
  await page.goto('/admin/servicios');
  await page.getByRole('button',{name:'Agregar servicio',exact:true}).click();
  await page.getByRole('button',{name:'Buscar en la biblioteca'}).click();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await page.getByLabel('Categoría de aplicación').fill('diagramas');
  await page.getByRole('button',{name:'Buscar aplicaciones'}).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button',{name:'Incorporar Draw.io'}).click();
  await expect(page.getByRole('alert')).toContainText('No se pudo incorporar Draw.io');
  await expect(page.getByRole('alert')).toBeInViewport();
  await expect(page.getByRole('alert')).toBeFocused();
  await page.getByRole('button',{name:'Incorporar Draw.io'}).click();
  expect(attempts[0]).toBe(attempts[1]);
  await expect(page.getByRole('heading',{name:'Borrador de Draw.io'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Borrador de Draw.io'})).toBeFocused();
  await expect(page.getByRole('status')).toContainText('Draw.io se incorporó correctamente');
  await page.getByText('Editar descripción',{exact:true}).click();
  await page.getByLabel('Descripción de la aplicación').fill('Diagramas de laboratorio');
  await page.getByRole('button',{name:'Guardar ficha'}).click();
  await expect(page.getByRole('status')).toHaveText('Borrador guardado.');
  expect(draft.descripcion).toBe('Diagramas de laboratorio');
  await page.getByText('Editar descripción',{exact:true}).click();
  expect((await page.getByRole('dialog').boundingBox()).width).toBeGreaterThan(1000);
  await page.screenshot({path:'/tmp/nap-biblioteca-visual-oscuro.png',fullPage:true});
  await page.evaluate(()=>document.documentElement.setAttribute('data-theme','light'));
  await page.screenshot({path:'/tmp/nap-biblioteca-visual-claro.png',fullPage:true});
  await page.evaluate(()=>document.documentElement.setAttribute('data-theme','dark'));
  await page.setViewportSize({width:390,height:844});
  expect(await page.getByRole('dialog').evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
  await page.screenshot({path:'/tmp/nap-biblioteca-visual-movil.png',fullPage:true});
  await page.getByRole('button',{name:'Continuar con Draw.io'}).click();
  await expect(page.getByRole('heading',{name:'Preparar y publicar Draw.io'})).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
});
