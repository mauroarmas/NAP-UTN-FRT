import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, ExternalLink, LoaderCircle, Rocket, Trash2, Wrench } from 'lucide-react';
import { consultarPreparacion, prepararAplicacion, confirmarFuncionamiento, publicarAplicacion, eliminarPreparacion, revelarAccesoEnsayo } from '../services/api';
import { mensajeError } from '../utils/errors';
import SelectorTamano from './SelectorTamano';
import { tamanosCompatibles } from '../utils/tamanos';
import useTamanos from '../hooks/useTamanos';

export default function EnsayoPreparacion({ incorporacion, onPublished, onBusyChange, onStepChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [access, setAccess] = useState(null);
  const [form, setForm] = useState({ nombre: incorporacion.nombre, descripcion: incorporacion.descripcion || '', tamano: 'small' });
  const alive = useRef(true);
  const running = useRef(false);
  const keys = useRef({});
  const restored = useRef(false);
  const { sizes, error: sizesError, loading: loadingSizes } = useTamanos();
  const refresh = useCallback(async () => {
    try { const { data: current } = await consultarPreparacion(incorporacion.id); if (alive.current) { setData(current); setError(''); if (!restored.current) { if (current.datos_servicio) setForm(current.datos_servicio); restored.current = true; } } }
    catch (err) { if (alive.current) setError(mensajeError(err, 'No se pudo consultar la preparación.')); }
    finally { if (alive.current) setLoading(false); }
  }, [incorporacion.id]);
  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; }; }, [refresh]);
  useEffect(() => {
    if (!['preparando', 'eliminando'].includes(data?.estado)) return;
    const poll = () => { if (document.visibilityState !== 'hidden' && !running.current) refresh(); };
    const timer = setInterval(poll, 3000); document.addEventListener('visibilitychange', poll);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', poll); };
  }, [data?.estado, refresh]);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => { onStepChange?.(data?.estado === 'lista_para_publicar' ? 2 : 1); }, [data?.estado, onStepChange]);
  useEffect(() => { if (data?.estado !== 'lista_para_probar') setAccess(null); }, [data?.estado]);
  const act = async (action, payload, callback) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError('');
    const fingerprint = JSON.stringify([action, data?.preparacion_id, payload]);
    try {
      const response = await callback(keys.current[fingerprint] ||= crypto.randomUUID());
      if (alive.current) {
        setData(response.data);
        if (response.data.estado === 'publicada') onPublished?.();
      }
    } catch (err) { if (alive.current) setError(mensajeError(err, 'No se confirmó la acción. Podés volver a intentarlo.')); }
    finally { running.current = false; if (alive.current) setBusy(false); }
  };
  const allowed = data?.minimum_resources ? tamanosCompatibles(sizes, data.minimum_resources) : sizes;
  const chosen = allowed.find((size) => size.id === form.tamano) || allowed[0];
  const state = data?.estado;
  const canStart = ['sin_preparar', 'eliminada'].includes(state);
  const reveal = async () => {
    if (running.current || !data.recursos?.[0]) return;
    running.current = true; setBusy(true); setError('');
    try { const { data: result } = await revelarAccesoEnsayo(data.preparacion_id, data.recursos[0].id); if (alive.current) setAccess(result); }
    catch (err) { setError(mensajeError(err, 'No se pudo obtener el acceso a la aplicación.')); }
    finally { running.current = false; if (alive.current) setBusy(false); }
  };
  return <section className="simple-preparation" aria-label="Preparación de la aplicación">
    {(loading || loadingSizes) && <p role="status">Cargando aplicación…</p>}
    {(error || sizesError) && <div role="alert" className="callout bad">{error || sizesError}{!data && <button className="btn btn-secondary" onClick={refresh}>Volver a consultar</button>}</div>}
    {data && <>
      {data.mensaje && <p className="callout warn" role={canStart ? 'status' : 'alert'}>{data.mensaje}</p>}
      {['preparando', 'eliminando'].includes(state) && <div className="simple-preparation-status" role="status"><LoaderCircle className="library-spinner" size={30}/><h3>{state === 'eliminando' ? 'Eliminando preparación…' : 'Preparando aplicación…'}</h3><p>Podés cerrar esta ventana. NAP continuará en segundo plano.</p></div>}
      {state === 'lista_para_probar' && <div className="simple-preparation-status is-ready">
        <CheckCircle2 size={30}/><h3>Ya podés probarla</h3><p>Abrí la aplicación y comprobá que funcione para tus clases.</p>
        {!access && <button className="btn btn-primary" disabled={busy} onClick={reveal}>Ver acceso</button>}
        {access && <div className="simple-application-access"><p>Usuario: <code>{access.acceso.username}</code></p><p>Contraseña: <code>{access.credenciales.access_password}</code></p><a className="btn btn-primary" href={access.acceso.endpoint} target="_blank" rel="noreferrer">Abrir aplicación<ExternalLink size={15}/></a></div>}
        <div className="row wrap gap-2"><button className="btn btn-primary" disabled={busy} onClick={() => act('confirmar', true, key => confirmarFuncionamiento(incorporacion.id, true, key))}>Funciona correctamente<CheckCircle2 size={16}/></button>
          <button className="btn btn-secondary" disabled={busy} onClick={() => act('confirmar', false, key => confirmarFuncionamiento(incorporacion.id, false, key))}>No funciona, eliminar</button></div>
      </div>}
      {(canStart || state === 'lista_para_publicar') && <form className="col gap-3" onSubmit={event => {
        event.preventDefault();
        if (!chosen || busy || sizesError) return;
        const body = { nombre: form.nombre, descripcion: form.descripcion, tamano: chosen.id };
        if (canStart) act('preparar', body, key => prepararAplicacion(incorporacion.id, body, key));
        else act('publicar', body, key => publicarAplicacion(incorporacion.id, body, key));
      }}>
        {state === 'eliminada' && <p role="status" className="callout">Preparación eliminada.</p>}
        {state === 'lista_para_publicar' && <p className="library-success"><CheckCircle2 size={18}/>Todo listo para publicarla.</p>}
        <div className="field"><label htmlFor="simple-service-name">Nombre del servicio</label><input id="simple-service-name" className="input" required maxLength={100} disabled={busy} value={form.nombre} onChange={event => setForm({ ...form, nombre: event.target.value })}/></div>
        <div className="field"><label htmlFor="simple-service-description">Descripción</label><input id="simple-service-description" className="input" maxLength={2000} disabled={busy} placeholder="¿Para qué sirve? (opcional)" value={form.descripcion} onChange={event => setForm({ ...form, descripcion: event.target.value })}/></div>
        <SelectorTamano sizes={sizes} value={chosen?.id || ''} onChange={tamano => setForm({ ...form, tamano })} allowed={allowed.map(size => size.id)} disabled={busy} legend="Tamaño recomendado"/>
        {!loadingSizes && !allowed.length && <p className="callout warn">Esta aplicación necesita más recursos que Small y Medium.</p>}
        <button className="btn btn-primary" disabled={busy || loadingSizes || !chosen || Boolean(sizesError) || (canStart && !data.puede_preparar)}>{busy ? 'Guardando…' : state === 'lista_para_publicar' ? <><Rocket size={17}/>Publicar servicio</> : <><Wrench size={17}/>Preparar aplicación</>}</button>
      </form>}
      {state === 'publicada' && <div className="simple-preparation-status is-ready"><CheckCircle2 size={30}/><h3>Servicio publicado</h3><button className="btn btn-primary" onClick={onPublished}>Volver al catálogo</button></div>}
      {data.preparacion_id && !['publicada', 'eliminada', 'eliminando'].includes(state) && <button className="btn btn-ghost simple-preparation-delete" disabled={busy} onClick={() => act('eliminar', {}, key => eliminarPreparacion(incorporacion.id, key))}><Trash2 size={15}/>Eliminar preparación</button>}
    </>}
  </section>;
}
