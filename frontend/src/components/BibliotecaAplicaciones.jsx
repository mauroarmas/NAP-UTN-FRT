import { useEffect, useRef, useState } from 'react';
import { buscarAplicaciones, listarIncorporaciones, incorporarAplicacion, editarIncorporacion } from '../services/api';
import { mensajeError } from '../utils/errors';
import { Search, Workflow, Box, ArrowRight, CheckCircle2, LoaderCircle, ExternalLink, Bookmark } from 'lucide-react';

export default function BibliotecaAplicaciones({ onSelected, onContinue, onBusyChange }) {
  const [q,setQ]=useState('');
  const [category,setCategory]=useState('');
  const [items,setItems]=useState([]);
  const [drafts,setDrafts]=useState([]);
  const [selected,setSelected]=useState(null);
  const [description,setDescription]=useState('');
  const [error,setError]=useState('');
  const [status,setStatus]=useState('');
  const [busy,setBusy]=useState(false);
  const [next,setNext]=useState(null);
  const [target,setTarget]=useState(null);
  const keys=useRef({});
  const running=useRef(false);
  const errorRef=useRef(null);
  const selectionRef=useRef(null);
  useEffect(()=>{onBusyChange?.(busy);return()=>onBusyChange?.(false);},[busy,onBusyChange]);
  useEffect(()=>{let active=true; listarIncorporaciones().then(({data})=>{if(active)setDrafts(data.items);}).catch(err=>{if(active)setError(mensajeError(err,'No se pudieron recuperar las fichas guardadas.'));}); return()=>{active=false;};},[]);
  useEffect(()=>{if(error){errorRef.current?.scrollIntoView?.({block:'nearest'});errorRef.current?.focus({preventScroll:true});}},[error]);
  useEffect(()=>{if(selected){selectionRef.current?.scrollIntoView?.({block:'nearest'});selectionRef.current?.focus({preventScroll:true});}},[selected]);
  const act=async(callback,actionTarget=null)=>{
    if(running.current)return;
    running.current=true;setBusy(true);setTarget(actionTarget);setError('');setStatus('');
    try{await callback();}catch(err){setError(mensajeError(err,'No se confirmó la acción. Conservamos los datos para reintentar.'));}
    finally{running.current=false;setBusy(false);}
  };
  const pick=(row)=>{setSelected(row);setDescription(row.descripcion||'');onSelected?.(row);};
  const showSaved=(row)=>{setError('');setTarget(null);setStatus('');pick(row);};
  const search=(cursor)=>act(async()=>{
    const {data}=await buscarAplicaciones({...(q.trim()?{q:q.trim()}:{}),...(category.trim()?{categoria:category.trim()}:{}),...(cursor?{cursor}:{} )});
    setItems(data.items);setNext(data.next_cursor);
    setStatus(data.fuente.estado==='desactualizada'?'Fuente inaccesible: mostramos una copia desactualizada. Podés reintentar.':data.items.length?'Resultados de la búsqueda.':'Sin coincidencias. Probá otro nombre o categoría.');
  });
  const incorporate=(row)=>act(async()=>{
    const body={identidad_externa:row.identidad_externa,revision_fuente:row.revision_fuente};
    const fingerprint=JSON.stringify(['incorporar',body]);
    const {data}=await incorporarAplicacion(body,keys.current[fingerprint] ||= crypto.randomUUID());
    setDrafts(current=>[data,...current.filter(r=>r.id!==data.id)]);pick(data);setStatus(`${data.nombre} se incorporó correctamente.`);
  },row.identidad_externa);
  const save=()=>act(async()=>{
    const body={revision_esperada:selected.revision,descripcion:description};
    const fingerprint=JSON.stringify(['editar',selected.id,body]);
    const {data}=await editarIncorporacion(selected.id,body,keys.current[fingerprint] ||= crypto.randomUUID());
    setDrafts(current=>current.map(r=>r.id===data.id?data:r));pick(data);setStatus('Borrador guardado.');
  });
  return <section className="app-library" aria-labelledby="biblioteca-title">
    <form className="library-search" onSubmit={e=>{e.preventDefault();search();}}>
      <div className="field library-search-main"><label htmlFor="biblioteca-q">Nombre de aplicación</label><div className="library-search-input"><Search size={19}/><input id="biblioteca-q" className="input" placeholder="Ej.: Draw.io, PostgreSQL…" value={q} maxLength={100} onChange={e=>{setQ(e.target.value);setNext(null);}} /></div></div>
      <div className="field library-search-category"><label htmlFor="biblioteca-category">Categoría de aplicación</label><input id="biblioteca-category" className="input" placeholder="Todas las categorías" value={category} maxLength={100} onChange={e=>{setCategory(e.target.value);setNext(null);}} /></div>
      <button className="btn btn-primary library-search-button" aria-label="Buscar aplicaciones" disabled={busy||(!q.trim()&&!category.trim())}><Search size={17}/>Buscar</button>
    </form>
    {error&&!target&&<p role="alert" tabIndex={-1} ref={errorRef} className="callout bad">{error}</p>}
    {busy&&!target&&<p role="status" className="library-notice"><LoaderCircle size={16} className="library-spinner"/>Consultando…</p>}
    {status&&!target&&<p role="status" className="library-notice">{status}</p>}
    <div className={`library-workspace ${selected?'has-selection':''}`}>
      <div className="library-discovery">
        {drafts.length>0&&<section className="library-saved" aria-label="Aplicaciones incorporadas"><h3><Bookmark size={16}/>Guardadas</h3><div>{drafts.map(row=><button type="button" className={`library-saved-item ${selected?.id===row.id?'is-selected':''}`} key={row.id} aria-label={`${row.nombre} · borrador`} onClick={()=>{setError('');setTarget(null);setStatus('');pick(row);}} disabled={busy}><CheckCircle2 size={16}/>{row.nombre}<ArrowRight size={15}/></button>)}</div></section>}
        <h2 id="biblioteca-title">{items.length?'Resultados':'Biblioteca de aplicaciones'}{items.length>0&&<span className="library-count">{items.length}</span>}</h2>
        {!items.length&&!status&&!busy&&<div className="library-empty"><Search size={32}/><p>Buscá una aplicación para empezar.</p></div>}
        <div className="library-results">{items.map(row=>{
          const isDrawio=row.identidad_externa?.includes('drawio');
          const saved=drafts.find(d=>d.identidad_externa===row.identidad_externa&&d.revision_fuente===row.revision_fuente);
          const Icon=isDrawio?Workflow:Box;
          return <article className={`library-app ${isDrawio?'is-diagram':''} ${selected?.id&&selected.id===saved?.id?'is-selected':''}`} key={row.identidad_externa}>
            <div className="library-app-heading"><span className="library-app-icon"><Icon size={28}/></span><div><h3>{row.nombre}</h3><span className={`library-app-status ${saved?'is-saved':''}`}>{saved?'Guardada':row.compatibilidad==='adaptador_disponible'?'Se puede preparar':'Requiere adaptación'}</span></div></div>
            {(row.descripcion||isDrawio)&&<p className="library-app-description">{row.descripcion||(isDrawio?'Diagramas y esquemas para tus clases.':'')}</p>}
            <details className="library-app-details"><summary>Información técnica de origen</summary><p>Faltantes: {(row.faltantes||[]).join(', ')||'ninguno'}</p><pre>{row.comando_origen}</pre><a href={row.url_origen} target="_blank" rel="noreferrer">Ver procedencia <ExternalLink size={12}/></a></details>
            <button type="button" className="btn btn-primary library-app-action" disabled={busy} aria-label={saved?`Ver ficha de ${row.nombre}`:busy&&target===row.identidad_externa?'Incorporando…':`Incorporar ${row.nombre}`} onClick={()=>saved?showSaved(saved):incorporate(row)}>{busy&&target===row.identidad_externa?<><LoaderCircle size={16} className="library-spinner"/>Incorporando…</>:<>{saved?'Ver ficha':'Incorporar'}<ArrowRight size={16}/></>}</button>
            {error&&target===row.identidad_externa&&<p role="alert" ref={errorRef} tabIndex={-1} className="callout bad biblioteca-feedback">No se pudo incorporar {row.nombre}. {error}</p>}
          </article>;
        })}</div>
        {next&&<button className="btn btn-secondary" disabled={busy} onClick={()=>search(next)}>Más resultados</button>}
      </div>
      {selected&&<form className="biblioteca-selection library-selection" onSubmit={e=>{e.preventDefault();save();}}>
        <span className="library-selection-icon"><CheckCircle2 size={25}/></span>
        <h3 ref={selectionRef} tabIndex={-1} aria-label={`Borrador de ${selected.nombre}`}>{selected.nombre}</h3>
        <p className="library-selection-caption">{selected.compatibilidad==='adaptador_disponible'?'Lista para preparar':'Guardada · requiere adaptación'}</p>
        {target&&!error&&!busy&&<p className="library-success" role="status">{selected.nombre} se incorporó correctamente.</p>}
        <div className="library-selection-actions">{onContinue&&<button type="button" className="btn btn-primary" disabled={busy} aria-label={`Continuar con ${selected.nombre}`} onClick={()=>onContinue(selected)}>Preparar aplicación<ArrowRight size={17}/></button>}</div>
        <details className="library-edit"><summary>Editar descripción</summary><div className="field"><label htmlFor="biblioteca-description">Descripción de la aplicación</label><textarea id="biblioteca-description" className="input" rows={3} placeholder="¿Para qué se usará? (opcional)" value={description} maxLength={4000} onChange={e=>setDescription(e.target.value)} /></div><button className="btn btn-secondary" disabled={busy}>Guardar ficha</button></details>
        <p className="library-selection-footnote">Aún no está instalada ni publicada.</p>
      </form>}
    </div>
  </section>;
}
