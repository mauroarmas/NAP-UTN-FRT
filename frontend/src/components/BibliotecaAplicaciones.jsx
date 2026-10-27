import { useEffect, useRef, useState } from 'react';
import { buscarAplicaciones, getCategoriasAplicaciones, listarIncorporaciones, incorporarAplicacion } from '../services/api';
import { mensajeError } from '../utils/errors';
import { Search, Workflow, Box, ArrowRight, CheckCircle2, LoaderCircle, ExternalLink, Info } from 'lucide-react';

const compatible = (row) => row.compatibilidad === 'adaptador_disponible';

export default function BibliotecaAplicaciones({ onSelected, onContinue, onBusyChange }) {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState([]);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [categoryError, setCategoryError] = useState('');
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [next, setNext] = useState(null);
  const [target, setTarget] = useState(null);
  const keys = useRef({});
  const running = useRef(false);
  const errorRef = useRef(null);
  const selectionRef = useRef(null);
  const incorporations = useRef([]);
  const active = useRef(true);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  const loadCategories = async () => {
    setCategoriesLoading(true); setCategoryError('');
    try {
      const { data } = await getCategoriasAplicaciones();
      if (!active.current) return;
      setCategories(data.items);
      if (data.fuente.metadatos_estado === 'no_disponible') setCategoryError('No se pudieron actualizar todas las categorías. Podés buscar por nombre.');
    } catch { if (active.current) setCategoryError('No se pudieron cargar las categorías. Podés buscar por nombre.'); }
    finally { if (active.current) setCategoriesLoading(false); }
  };
  useEffect(() => {
    active.current = true;
    loadCategories();
    // Las incorporaciones previas sólo sirven para retomar una misma alta.
    listarIncorporaciones().then(({ data }) => { if (active.current) incorporations.current = data.items; }).catch(() => {});
    return () => { active.current = false; };
  }, []);
  useEffect(() => { if (error) { errorRef.current?.scrollIntoView?.({ block: 'nearest' }); errorRef.current?.focus({ preventScroll: true }); } }, [error]);
  useEffect(() => { if (selected) { selectionRef.current?.scrollIntoView?.({ block: 'nearest' }); selectionRef.current?.focus({ preventScroll: true }); } }, [selected]);
  const act = async (callback, actionTarget = null) => {
    if (running.current) return;
    running.current = true; setBusy(true); setTarget(actionTarget); setError(''); setStatus('');
    try { await callback(); }
    catch (err) { if (active.current) setError(mensajeError(err, 'No se confirmó la acción. Podés volver a intentar.')); }
    finally { running.current = false; if (active.current) setBusy(false); }
  };
  const pick = (row) => { setSelected(row); onSelected?.(row); };
  const search = (cursor) => act(async () => {
    const { data } = await buscarAplicaciones({ ...(q.trim() ? { q: q.trim() } : {}), ...(category ? { categoria: category } : {}), ...(cursor ? { cursor } : {}) });
    if (!active.current) return;
    setItems(data.items); setNext(data.next_cursor); setSelected(null);
    setStatus(data.fuente.estado === 'desactualizada' ? 'Fuente inaccesible: mostramos la última copia disponible.' : data.items.length ? '' : 'Sin coincidencias. Probá otro nombre o categoría.');
  });
  const choose = (row) => {
    if (!compatible(row)) { setError(''); setStatus(''); setTarget(null); pick(row); return; }
    act(async () => {
      const saved = incorporations.current.find(d => d.identidad_externa === row.identidad_externa && d.revision_fuente === row.revision_fuente);
      let data = saved;
      if (!data) {
        const body = { identidad_externa: row.identidad_externa, revision_fuente: row.revision_fuente };
        const fingerprint = JSON.stringify(body);
        ({ data } = await incorporarAplicacion(body, keys.current[fingerprint] ||= crypto.randomUUID()));
        incorporations.current = [data, ...incorporations.current.filter(d => d.id !== data.id)];
      }
      if (!active.current) return;
      // La capacidad de instalación corresponde a la búsqueda actual, no a una ficha antigua.
      data = { ...data, compatibilidad: row.compatibilidad };
      pick(data); setStatus(`${data.nombre}: listo para agregar.`); onContinue?.(data);
    }, row.identidad_externa);
  };
  const showSelection = selected && (!compatible(selected) || !onContinue);
  return <section className="app-library" aria-labelledby="biblioteca-title">
    <form className="library-search" onSubmit={event => { event.preventDefault(); search(); }}>
      <div className="field library-search-main"><label htmlFor="biblioteca-q">Nombre de aplicación</label><div className="library-search-input"><Search size={19}/><input id="biblioteca-q" className="input" placeholder="Ej.: Draw.io, PostgreSQL…" value={q} maxLength={100} onChange={event => { setQ(event.target.value); setNext(null); }}/></div></div>
      <div className="field library-search-category"><label htmlFor="biblioteca-category">Categoría de aplicación</label><select id="biblioteca-category" className="input" value={category} disabled={categoriesLoading || busy} onChange={event => { setCategory(event.target.value); setNext(null); }}><option value="">{categoriesLoading ? 'Cargando categorías…' : 'Todas las categorías'}</option>{categories.map(name => <option value={name} key={name}>{name}</option>)}</select></div>
      <button className="btn btn-primary library-search-button" aria-label="Buscar aplicaciones" disabled={busy || (!q.trim() && !category)}><Search size={17}/>Buscar</button>
    </form>
    {categoryError && <p className="library-notice" role="status">{categoryError}<button className="btn btn-ghost" type="button" disabled={categoriesLoading} onClick={loadCategories}>Reintentar</button></p>}
    {error && !target && <p role="alert" tabIndex={-1} ref={errorRef} className="callout bad">{error}</p>}
    {busy && !target && <p role="status" className="library-notice"><LoaderCircle size={16} className="library-spinner"/>Buscando aplicaciones…</p>}
    {status && <p role="status" className="library-notice">{status}</p>}
    <div className={`library-workspace ${showSelection ? 'has-selection' : ''}`}>
      <div className="library-discovery">
        <h2 id="biblioteca-title">{items.length ? 'Resultados' : 'Biblioteca de aplicaciones'}{items.length > 0 && <span className="library-count">{items.length}</span>}</h2>
        {!items.length && !status && !busy && <div className="library-empty"><Search size={32}/><p>Buscá una aplicación para empezar.</p></div>}
        <div className="library-results">{items.map(row => {
          const canInstall = compatible(row);
          const Icon = row.identidad_externa === 'ct/drawio.sh' ? Workflow : Box;
          return <article className={`library-app ${canInstall ? 'is-diagram' : ''} ${selected?.identidad_externa === row.identidad_externa ? 'is-selected' : ''}`} key={row.identidad_externa}>
            <div className="library-app-heading"><span className="library-app-icon"><Icon size={28}/></span><div><h3>{row.nombre}</h3><span className={`library-app-status ${canInstall ? 'is-ready' : 'is-unavailable'}`}>{canInstall ? 'Instalación automática' : 'Sin instalación en NAP'}</span></div></div>
            {row.descripcion && <p className="library-app-description">{row.descripcion}</p>}
            <button type="button" className={`btn ${canInstall ? 'btn-primary' : 'btn-secondary'} library-app-action`} disabled={busy} aria-label={busy && target === row.identidad_externa ? 'Cargando servicio…' : canInstall ? `Agregar ${row.nombre}` : `Ver disponibilidad de ${row.nombre}`} onClick={() => choose(row)}>{busy && target === row.identidad_externa ? <><LoaderCircle size={16} className="library-spinner"/>Cargando…</> : <>{canInstall ? 'Agregar servicio' : 'Ver disponibilidad'}<ArrowRight size={16}/></>}</button>
            {error && target === row.identidad_externa && <p role="alert" ref={errorRef} tabIndex={-1} className="callout bad biblioteca-feedback">No se pudo seleccionar {row.nombre}. {error}</p>}
          </article>;
        })}</div>
        {next && <button className="btn btn-secondary" disabled={busy} onClick={() => search(next)}>Más resultados</button>}
      </div>
      {showSelection && <section className={`biblioteca-selection library-selection ${!compatible(selected) ? 'is-unavailable' : ''}`} aria-label="Disponibilidad de la aplicación">
        <span className="library-selection-icon">{compatible(selected) ? <CheckCircle2 size={25}/> : <Info size={25}/>}</span>
        <h3 ref={selectionRef} tabIndex={-1}>{selected.nombre}</h3>
        <p className="library-selection-caption">{compatible(selected) ? 'Lista para agregar al catálogo.' : 'Esta aplicación está en Community Scripts, pero NAP todavía no tiene su instalación automática.'}</p>
        {!compatible(selected) && <p className="card-meta">No se agregó al catálogo. Hace falta integrar su instalación una vez para poder ofrecerla a las cátedras.</p>}
        {selected.url_origen && <a href={selected.url_origen} target="_blank" rel="noopener noreferrer">Ver origen<ExternalLink size={13}/></a>}
      </section>}
    </div>
  </section>;
}
