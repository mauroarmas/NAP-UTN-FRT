import {test,expect} from './fixtures';

for(const entry of ['catalogo','pedidos'])test(`Draw.io desde ${entry} conserva formulario cuando cambia la oferta`,async({page})=>{
  await page.route('**/api/v1/auth/me',r=>r.fulfill({json:{estado:'operativo',usuario:{id:2,nombre:'Docente',rol:'catedra_admin'}}}));
  await page.route('**/api/v1/auth/csrf',r=>r.fulfill({json:{csrf_token:'test-csrf'}}));
  let profile={id:2,nombre:'Draw.io',tipo:'lxc',modelo_servicio:'saas',activo:true,oferta_disponible:true,origen_biblioteca:true,version_ofrecida:'1.0.0',revision:1};
  await page.route('**/api/v1/templates/**',r=>r.fulfill({json:[profile]}));
  await page.route('**/api/v1/catedras/**',r=>r.fulfill({json:[{id:1,nombre:'Cátedra propia'}]}));
  await page.route('**/api/v1/calendarios/*',r=>r.fulfill({json:{anio:2027,periodos:[]}}));
  await page.route('**/api/v1/pedidos/**',r=>{
    if(r.request().method()==='GET')return r.fulfill({json:[]});
    expect(r.request().postDataJSON().oferta_revision).toBe(1);
    profile={...profile,version_ofrecida:'2.0.0',revision:2};
    return r.fulfill({status:409,json:{detail:{codigo:'oferta_desactualizada',mensaje:'La oferta cambió; revisá la versión vigente.'}}});
  });
  await page.goto('/'+entry);
  if(entry==='catalogo')await page.getByRole('button',{name:'Solicitar Draw.io'}).click();
  else {await page.getByRole('button',{name:/Nuevo pedido|Nueva Solicitud/}).first().click();await page.getByRole('button',{name:/Software/}).click();}
  await expect(page.getByLabel('Servicio',{exact:true})).toHaveValue('2');
  await expect(page.getByLabel('vCPU',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Rango Personalizado'}).click();
  await page.getByLabel('Fecha desde').fill('2027-03-01');await page.getByLabel('Fecha hasta').fill('2027-06-30');
  await page.getByLabel('Nombre de la solicitud').fill('Diagramas para prácticas');
  await page.getByLabel('Justificación pedagógica',{exact:true}).fill('Modelar sistemas de la cátedra');
  await page.getByRole('button',{name:'Enviar solicitud',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText(/La oferta cambió/);
  await expect(page.getByLabel('Justificación pedagógica',{exact:true})).toHaveValue('Modelar sistemas de la cátedra');
  await expect(page.getByLabel('Servicio',{exact:true}).locator('option:checked')).toHaveText(/2.0.0/);
});
