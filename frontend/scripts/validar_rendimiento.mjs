import { writeFile, appendFile, open, readFile, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { cpus, totalmem, platform, release } from 'node:os';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from '@playwright/test';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const origin = 'http://localhost:4174';
const api = 'http://127.0.0.1:8044';
const timeout = 30_000;
const flows = ['pedidos', 'servicios', 'metricas'];
const executeFile = promisify(execFile);

async function provenance() {
  const root=resolve(frontend,'..'), hashes={};
  async function walk(directory) {
    for(const item of await readdir(resolve(root,directory),{withFileTypes:true})) {
      const name=directory+'/'+item.name;
      if(item.isDirectory() && item.name!=='__pycache__') await walk(name);
      else if(item.isFile() && /\.(py|jsx?|css)$/.test(item.name)) hashes[name]=createHash('sha256').update(await readFile(resolve(root,name))).digest('hex');
    }
  }
  for(const folder of ['backend/app','backend/alembic','frontend/src','frontend/scripts']) await walk(folder);
  for(const file of ['backend/requirements.lock','frontend/package-lock.json']) hashes[file]=createHash('sha256').update(await readFile(resolve(root,file))).digest('hex');
  const head=(await executeFile('git',['rev-parse','HEAD'],{cwd:root})).stdout.trim();
  const db=JSON.parse((await executeFile('docker',['inspect','nap009-rendimiento-db','--format',
    '{"image":{{json .Image}},"cpus_nano":{{.HostConfig.NanoCpus}},"memory_bytes":{{.HostConfig.Memory}},"shm_bytes":{{.HostConfig.ShmSize}},"pids":{{.HostConfig.PidsLimit}}}'])).stdout);
  return {source:{head,working_tree:'cambios sin commit; hashes por archivo',sha256:hashes},
    resources:{platform:platform()+' '+release(),logical_cpus:cpus().length,cpu:cpus()[0]?.model,
      memory_bytes:totalmem(),node:process.version,postgresql_container:db,
      api_worker_proxy_browser:'procesos del host sin cuotas adicionales; generador en el mismo equipo'}};
}

async function privateJSON(path) {
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const info = await handle.stat();
    if (!info.isFile() || (info.mode & 0o777) !== 0o600 || info.uid !== process.getuid() || info.size > 1_048_576) {
      throw new Error('Archivo privado inválido');
    }
    return JSON.parse(await handle.readFile('utf8'));
  } finally { await handle.close(); }
}

// nearest-rank, incluyendo errores/timeouts; no interpolación ni descarte.
export function summarize(samples) {
  return Object.fromEntries(flows.map((flow) => {
    const rows = samples.filter((row) => row.flow === flow && !row.warmup);
    const durations = rows.map((r) => r.duration_ms).sort((a,b) => a-b);
    const p95 = durations.length ? durations[Math.ceil(durations.length * .95)-1] : null;
    const validRatio = rows.filter((r) => r.valid && r.duration_ms <= 3000).length / (rows.length || 1);
    return [flow, { samples: rows.length, p95_ms: p95, valid_within_3s_ratio: validRatio,
      passed: rows.length >= 100 && p95 <= 3000 && validRatio >= .95 }];
  }));
}

function instrument({ cutoff }) {
  window.__napRequests = [];
  window.__napResult = null;
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    const parsed = new URL(url, location.href);
    const relevant = /^\/api\/v1\/(pedidos\/$|servicios\/$|metricas\/)/.test(parsed.pathname);
    const start = performance.now();
    if (relevant) this.addEventListener('loadend', () => {
      let body;
      try { body = JSON.parse(this.responseText); } catch { body = null; }
      window.__napRequests.push({ url: parsed.pathname+parsed.search, start, duration_ms: performance.now()-start,
        status: this.status, timing: this.getResponseHeader('Server-Timing'), body });
    }, { once: true });
    return originalOpen.call(this, method, url, ...rest);
  };
  const visible = (element) => !!element && element.getClientRects().length > 0
    && getComputedStyle(element).visibility !== 'hidden';
  const inViewport = (element) => {
    if(!visible(element)) return false;
    const box=element.getBoundingClientRect();
    return box.bottom>0 && box.top<innerHeight && box.right>0 && box.left<innerWidth;
  };
  function capture(event) {
    const arm = window.__napArm;
    if (!arm || event.type !== arm.event || !event.target.closest(arm.selector)) return;
    window.__napArm = null; window.__napResult = null;
    const start = performance.now();
    window.__napStarted = start;
    let seenRequest = null;
    let expectedPoints = null;
    function frame() {
      const elapsed = performance.now()-start;
      const request = window.__napRequests.findLast((r) => r.start >= start &&
        (arm.flow === 'metricas' ? r.url.startsWith(`/api/v1/metricas/${arm.serviceId}/historial?`)
          : new URL(r.url, location.href).pathname === `/api/v1/${arm.flow}/`));
      let valid = false;
      let error = null;
      if (request) {
        const data = request.body;
        if (request.status !== 200 || !Array.isArray(data)) error = 'respuesta_http_invalida';
        else if (arm.flow === 'metricas') {
          const url = new URL(request.url, location.href);
          const since = Date.parse(url.searchParams.get('desde')), until = Date.parse(url.searchParams.get('hasta'));
          const hours = { hora:1, dia:24, trimestre:2160 }[arm.key];
          if (until-since !== hours*3600000) error = 'rango_solicitado_incorrecto';
          if (seenRequest !== request) {
            seenRequest = request;
            const last = Date.parse(cutoff), first = last-129599*60000;
            const step = Math.max(60, Math.ceil((until-since)/1000/500/60)*60)*1000;
            const buckets = new Map();
            for (let i=Math.max(0,Math.ceil((since-first)/60000)); i<129600; i++) {
              const timestamp=first+i*60000;
              if (timestamp>=until) break;
              buckets.set(Math.floor(timestamp/step),timestamp);
            }
            expectedPoints = [...buckets.values()].slice(-500);
          }
          if (!expectedPoints.length || data.length !== expectedPoints.length ||
            data.some((r,i) => r.servicio_id !== arm.serviceId || Date.parse(r.timestamp) !== expectedPoints[i]
              || r.calidad !== 'confirmada' || r.net_in_delta_exacto !== '1024')) error='muestras_no_coinciden_con_fixture';
          const section = document.querySelector('[aria-label="Historial de métricas"]');
          const text = section?.querySelector('[aria-label="Resumen textual del historial"]');
          const interval = section?.querySelector('[aria-label="Intervalo de observaciones"]');
          const graphs = section?.querySelector('[aria-label="Gráficas de observaciones"]');
          const paths = graphs?.querySelectorAll('.recharts-line path');
          const control = section?.querySelector('select');
          valid = !error && visible(section) && section.getAttribute('aria-busy') === 'false'
            && section.dataset.periodo === arm.key && section.dataset.servicioId === String(arm.serviceId)
            && inViewport(text) && text.textContent.includes(`${data.length} puntos seleccionados`)
            && inViewport(interval) && interval.textContent.includes(data[0].timestamp)
            && interval.textContent.includes(data[data.length-1].timestamp)
            && inViewport(graphs) && paths?.length >= 4 && [...paths].every((p) => p.getAttribute('d')?.length > 10)
            && control && !control.disabled && control.value === arm.key;
        } else {
          const key = arm.flow === 'pedidos' ? 'estado' : 'modelo_servicio';
          const url = new URL(request.url,location.href);
          const actual = data.map((r) => r.id).sort((a,b) => a-b);
          const expected = arm.ids;
          if (url.searchParams.get(key) !== arm.key || actual.length !== expected.length
            || actual.some((id,i) => id !== expected[i]) || !expected.length) error='filas_http_incorrectas';
          const section = document.querySelector(`[aria-label="Listado de ${arm.flow}"]`);
          const attribute = arm.flow === 'pedidos' ? 'data-pedido-id' : 'data-servicio-id';
          const rows = section ? [...section.querySelectorAll(`[${attribute}]`)] : [];
          const ids = rows.map((row) => Number(row.getAttribute(attribute))).sort((a,b) => a-b);
          valid = !error && visible(section) && section.getAttribute('aria-busy') === 'false'
            && rows.every(visible) && ids.length === expected.length && ids.every((id,i) => id === expected[i])
            && !document.querySelector(arm.selector)?.disabled;
        }
      }
      const finish = (ok, reason) => {
        // La segunda rAF ocurre después de que el frame anterior se pinte.
        requestAnimationFrame(() => { window.__napResult = { start_ms:start, duration_ms:performance.now()-start,
          valid:ok, error:reason, timeout:!ok && !reason, query_key:arm.key,
          http:request ? { url:request.url,status:request.status,duration_ms:request.duration_ms,server_timing:request.timing } : null }; });
      };
      if (error) finish(false,error);
      else if (valid) finish(true,null);
      else if (elapsed>=30000) finish(false,null);
      else requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  document.addEventListener('click',capture,true);
  document.addEventListener('change',capture,true);
}

export async function runPerformance(browser, { configPath, outputPath }) {
  const config = await privateJSON(configPath);
  const directory = dirname(resolve(configPath));
  const fixture = await privateJSON(resolve(directory,'fixture.json'));
  const control = await privateJSON(resolve(directory,'control.json'));
  const journalName=`muestras-${Date.now()}.jsonl`;
  const journal=resolve(directory,journalName);
  await writeFile(journal,'',{mode:0o600,flag:'wx'});
  if (fixture.environment !== 'simulado' || fixture.samples !== 12_960_000 || fixture.origin !== origin
      || config.users.length !== 10 || config.users.filter((u) => u.role === 'admin').length !== 5) {
    throw new Error('Se requiere el fixture completo aislado y cinco usuarios por rol');
  }
  const controlCall = async (name,method='GET') => {
    const response=await fetch(`${api}/__performance/${name}`, { method,headers:{'x-performance-control':control.token} });
    if (!response.ok) throw new Error(`Control ${name}: HTTP ${response.status}`);
    return response.json();
  };
  const result = { schema_version:1, started_at:new Date().toISOString(), protocol:'quickstart SC-008',
    journal:journalName,
    ...await provenance(),
    fixture:{ samples:fixture.samples,services:fixture.services.length,cutoff:fixture.cutoff,diagnostic:fixture.diagnostic,source:fixture.source },
    environment:{ browser:browser.version(), viewport:{width:1440,height:1000},origin, network:'loopback sin throttling',
      data_cache:'Cache-Control: no-store; claves de consulta alternadas',static_cache:'normal, cinco calentamientos por contexto/recorrido',
      api_worker:'un proceso ASGI, worker real cooperativo y pool I/O de cuatro threads; sólo PVE/runner simulados',
      generator:'Playwright Chromium en el mismo equipo', timeout_ms:timeout, warmup_per_context_flow:5,
      contexts:10,role_distribution:{admin:5,catedra_admin:5} },
    samples:[],fatal_error:null,slow_operation:null,closing_operation:null };
  const clients=[];
  let monitor=null;
  let operation=null;
  let starting=false;
  let invalidWarmup=false;
  try {
    // Autenticación real fuera de las muestras. Sin storageState ni secretos en artefactos.
    await Promise.all(config.users.map(async (credential,i) => {
      const context=await browser.newContext({ viewport:result.environment.viewport,serviceWorkers:'block',locale:'es-AR' });
      await context.addInitScript(instrument,{ cutoff:fixture.cutoff });
      const page=await context.newPage(); page.setDefaultTimeout(timeout);
      await page.goto(origin+'/pedidos');
      await page.getByLabel('Usuario o Correo').fill(credential.username);
      await page.getByLabel('Contraseña',{exact:true}).fill(credential.password);
      await page.getByRole('button',{name:'Ingresar',exact:true}).click();
      await page.getByRole('button',{name:'Cuenta',exact:true}).waitFor();
      const user=fixture.users.find((u) => u.username === credential.username);
      const owned=fixture.services.filter((s) => user.role === 'admin' || s.teacher_id === user.id);
      clients.push({context,page,id:i,role:user.role,owned,operations:[]});
    }));
    clients.sort((a,b) => a.id-b.id);
    const measure = async (client,flow,index,warmup) => {
      const {page}=client;
      const key=flow==='pedidos' ? index%2?'suspendido':'activo' : flow==='servicios' ? index%2?'paas':'iaas' : index%2?'trimestre':'hora';
      const selector=flow==='pedidos'?'[aria-label="Filtrar pedidos por estado"]':flow==='servicios'?'[aria-label="Filtrar por tipo de servicio"]':'#periodo-metricas';
      const ids=client.owned.filter((s) => flow==='pedidos'? s.pedido_estado===key:s.model===key)
        .map((s) => flow==='pedidos'?s.pedido_id:s.id).sort((a,b) => a-b);
      const arm={flow,key,ids,selector,event:'change',serviceId:client.owned[0].id};
      await page.evaluate((value) => { window.__napArm=value; window.__napResult=null; window.__napStarted=null; },arm);
      let sample;
      try {
        await page.locator(selector).selectOption(key);
        await page.waitForFunction(() => window.__napResult !== null,{},{timeout:timeout+2000});
        sample=await page.evaluate(() => window.__napResult);
      } catch {
        sample=await page.evaluate(() => ({start_ms:window.__napStarted,duration_ms:window.__napStarted===null?30000:Math.max(30000,performance.now()-window.__napStarted),valid:false,timeout:true,error:'interaccion_o_resultado_no_disponible',http:null}));
      }
      const recorded={...sample,flow,context:client.id,role:client.role,warmup,query_key:key,
        slow_operation_open:warmup?null:client.operations.at(-1)?.estado==='en_curso',
        operation_id:operation?.operation_id || null};
      result.samples.push(recorded);
      await appendFile(journal,JSON.stringify(recorded)+'\n');
      if(warmup && !recorded.valid) invalidWarmup=true;
    };
    const prepareFlow=async (client,flow) => {
      await client.page.goto(`${origin}/${flow}`);
      if (flow==='metricas') {
        await client.page.locator(`article[data-servicio-id="${client.owned[0].id}"] button`).click();
        await client.page.getByLabel('Resumen textual del historial').waitFor();
      } else await client.page.locator(flow==='pedidos'?'[aria-label="Filtrar pedidos por estado"]':'[aria-label="Filtrar por tipo de servicio"]').waitFor();
    };
    // Calentar todos los recorridos antes de admitir la tarea con plazo real180s.
    for (const flow of flows) {
      await Promise.all(clients.map(async (client) => {
        await prepareFlow(client,flow);
        for(let i=0;i<5 && !invalidWarmup;i++) await measure(client,flow,i,true);
      }));
      if(invalidWarmup) throw new Error('Falló calentamiento; revisar diario de muestras antes de medir');
    }
    starting=true;
    operation=await controlCall('start','POST'); result.slow_operation=operation;
    if(operation.accepted_status!==202) throw new Error('El despliegue no devolvió 202 real');
    // Verificar UPID/fase de espera antes de iniciar las muestras medidas.
    const until=Date.now()+30_000;
    while(Date.now()<until) {
      const state=await controlCall('state');
      if(state.estado==='en_curso' && state.fase==='tarea') break;
      if(['fallida','incierta','confirmada'].includes(state.estado)) throw new Error('El despliegue no permanece pendiente');
      await delay(200);
    }
    operation=await controlCall('state');
    if(operation.estado!=='en_curso' || operation.fase!=='tarea') throw new Error('No se observó tarea pendiente');
    const operationChecks=[{...operation,checked_at:new Date().toISOString()}];
    let checking=false;
    monitor=setInterval(async () => {
      if(checking) return; checking=true;
      try {
        const state=await controlCall('state'); operationChecks.push({...state,checked_at:new Date().toISOString()});
        for(const client of clients) client.operations.push(state);
      } catch { result.fatal_error='No se pudo observar la operación durante las muestras'; }
      finally { checking=false; }
    },500);
    for(const client of clients) client.operations.push(operation);
    // Diez contextos activos; treinta muestras medidas por contexto, escalonadas.
    await Promise.all(clients.map(async (client) => {
      await delay(client.id*35);
      for(const flow of flows) {
        await prepareFlow(client,flow);
        for(let i=0;i<10;i++) await measure(client,flow,i+5,false);
      }
    }));
    const last=await controlCall('state'); operationChecks.push({...last,checked_at:new Date().toISOString()});
    if(monitor) { clearInterval(monitor); monitor=null; }
    result.operation_checks=operationChecks;
    if(operationChecks.some((s) => s.estado!=='en_curso' || s.fase!=='tarea' || s.released)) result.fatal_error='La operación no permaneció pendiente durante toda la medición';
    if(last.pending_seconds<30) await delay((30-last.pending_seconds)*1000+100);
    result.closing_operation=await controlCall('finish','POST');
    if(result.closing_operation.estado!=='confirmada') result.fatal_error='La operación no confirmó al terminar';
  } catch(error) {
    result.fatal_error=/^(Control |Falló calentamiento)/.test(error.message) ? error.message : error.name;
  } finally {
    if(monitor) clearInterval(monitor);
    // Un fallo del navegador también libera y confirma el doble, nunca PVE real.
    if(starting && !result.closing_operation) {
      try {
        const state=await controlCall('state');
        if(state.pending_seconds<30) await delay((30-state.pending_seconds)*1000+100);
        result.closing_operation=await controlCall('finish','POST');
      } catch { result.cleanup_error='La operación simulada requiere revisar el estado aislado'; }
    }
    await Promise.all(clients.map((c) => c.context.close()));
    result.finished_at=new Date().toISOString(); result.summary=summarize(result.samples);
    result.passed=!result.fatal_error && Object.values(result.summary).every((s) => s.passed);
    await writeFile(outputPath,JSON.stringify(result,null,2)+'\n');
  }
  return result;
}

async function command(command,args,options={}) {
  const child=spawn(command,args,{cwd:frontend,stdio:'ignore',...options});
  await new Promise((resolve,reject) => { child.on('error',reject); child.on('exit',(code) => code===0?resolve():reject(new Error('Subproceso de compilación falló'))); });
}

async function main() {
  const args=process.argv.slice(2);
  const configIndex=args.indexOf('--config');
  if(configIndex<0 || !args.includes('--execute')) throw new Error('Usar --config /ruta/privada/configuracion.json --execute; API aislada8044 ya iniciada');
  const configPath=resolve(args[configIndex+1]);
  await privateJSON(configPath);
  const outputIndex=args.indexOf('--output');
  const outputPath=outputIndex<0?resolve(frontend,'../docs/evidencia/009/rendimiento-navegador.json'):resolve(args[outputIndex+1]);
  await command('npm',['run','build']);
  const preview=spawn('npm',['run','preview','--','--host','127.0.0.1','--port','4174','--strictPort'],{
    cwd:frontend,stdio:'ignore',detached:true,env:{...process.env,NAP_BACKEND_PROXY:api}});
  let browser;
  try {
    let ready=false;
    for(let i=0;i<100;i++) {
      if(preview.exitCode!==null) throw new Error('Puerto4174 ocupado o preview falló');
      try { ready=(await fetch(origin)).ok; } catch {}
      if(ready) break; await delay(100);
    }
    if(!ready) throw new Error('Preview no disponible');
    browser=await chromium.launch({headless:true});
    const result=await runPerformance(browser,{configPath,outputPath});
    console.log(JSON.stringify({passed:result.passed,summary:result.summary,fatal_error:result.fatal_error}));
    if(!result.passed) process.exitCode=1;
  } finally {
    await browser?.close();
    try { process.kill(-preview.pid,'SIGTERM'); } catch {}
  }
}

if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode=1; });
}
