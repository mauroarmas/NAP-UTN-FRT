import {test,expect} from './fixtures';

const inc={id:'inc',nombre:'Draw.io',compatibilidad:'adaptador_disponible',revision:1};
async function portal(page){
  await page.route('**/api/v1/auth/me',r=>r.fulfill({json:{estado:'operativo',usuario:{id:1,nombre:'Admin',rol:'admin'}}}));
  await page.route('**/api/v1/auth/csrf',r=>r.fulfill({json:{csrf_token:'test-csrf'}}));
  await page.route('**/api/v1/templates/?incluir_retiradas=true',r=>r.fulfill({json:[]}));
  await page.route('**/api/v1/definiciones**',r=>r.fulfill({json:[]}));
}
async function open(page){
  await page.goto('/catalogo');await page.getByRole('button',{name:'Agregar servicio',exact:true}).click();
  await page.getByRole('button',{name:'Buscar en la biblioteca'}).click();
  await page.getByRole('button',{name:'Draw.io · borrador'}).click();
  await page.getByRole('button',{name:'Continuar con Draw.io'}).click();
}

test('recupera la preparación y la elimina sin campos técnicos ni vencimiento',async({page})=>{
  await portal(page);
  let state={estado:'preparando',preparacion_id:'trial',puede_preparar:false,mensaje:'',recursos:[]};
  await page.route('**/api/v1/biblioteca/**',r=>{
    const url=r.request().url();
    if(url.endsWith('/preparacion'))return r.fulfill({json:state});
    if(url.endsWith('/eliminar')){state={...state,estado:'eliminada',puede_preparar:true};return r.fulfill({json:state});}
    return r.fulfill({json:{items:[inc]}});
  });
  await open(page);await expect(page.getByText('Preparando aplicación…')).toBeVisible();
  await expect(page.getByLabel('Entorno de prueba configurado')).toHaveCount(0);
  await expect(page.getByLabel('Plazo de ensayo (horas)')).toHaveCount(0);
  await page.reload();await page.getByRole('button',{name:'Agregar servicio',exact:true}).click();
  await page.getByRole('button',{name:'Buscar en la biblioteca'}).click();
  await page.getByRole('button',{name:'Draw.io · borrador'}).click();await page.getByRole('button',{name:'Continuar con Draw.io'}).click();
  await expect(page.getByText('Preparando aplicación…')).toBeVisible();
  await page.getByRole('button',{name:'Eliminar preparación'}).click();
  await expect(page.getByText('Preparación eliminada.')).toBeVisible();
});

test('preparar, confirmar funcionamiento y publicar requiere sólo datos del servicio',async({page})=>{
  await portal(page);
  let state={estado:'sin_preparar',preparacion_id:null,puede_preparar:true,mensaje:'',recursos:[]};let offer=[];
  await page.route('**/api/v1/templates/?incluir_retiradas=true',r=>r.fulfill({json:offer}));
  await page.route('**/api/v1/biblioteca/**',r=>{
    const request=r.request(),url=request.url();
    if(url.endsWith('/preparacion'))return r.fulfill({json:state});
    if(url.endsWith('/preparar')){
      expect(request.postDataJSON()).toEqual({nombre:'Diagramas',descripcion:'',tamano:'small'});expect(request.headers()['idempotency-key']).toBeTruthy();
      state={...state,estado:'lista_para_probar',preparacion_id:'trial',recursos:[{id:'resource'}]};return r.fulfill({status:202,json:state});
    }
    if(url.endsWith('/confirmar-funcionamiento')){
      expect(request.postDataJSON()).toEqual({funciona:true});state={...state,estado:'lista_para_publicar',minimum_resources:{vcpus:1,ram_mb:512,disk_gb:4}};return r.fulfill({status:202,json:state});
    }
    if(url.endsWith('/publicar')){
      expect(request.postDataJSON()).toEqual({nombre:'Diagramas',descripcion:'',tamano:'small'});
      offer=[{id:5,nombre:'Diagramas',tipo:'lxc',modelo_servicio:'saas',activo:true,oferta_disponible:true,tamanos_permitidos:['small','medium']}];state={...state,estado:'publicada'};return r.fulfill({status:201,json:state});
    }
    return r.fulfill({json:{items:[inc]}});
  });
  await open(page);await page.getByLabel('Nombre del servicio').fill('Diagramas');
  await page.getByRole('button',{name:'Preparar aplicación',exact:true}).click();
  await expect(page.getByText('Ya podés probarla')).toBeVisible();
  await page.getByRole('button',{name:'Funciona correctamente'}).click();
  await expect(page.locator('[aria-current="step"]')).toContainText('Publicar');
  await page.getByRole('button',{name:'Publicar servicio'}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Diagramas',exact:true})).toBeVisible();
});
