import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { consultarPreparacion, agregarAplicacion, eliminarPreparacion } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function EnsayoPreparacion({ incorporacion, onPublished, onBusyChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ nombre: incorporacion.nombre, descripcion: incorporacion.descripcion || '', tamano: 'small' });
  const alive = useRef(true);
  const running = useRef(false);
  const restored = useRef(false);
  const keys = useRef({});
  const completed = useRef(false);
  const refresh = useCallback(async () => {
    try {
      const { data: current } = await consultarPreparacion(incorporacion.id);
      if (!alive.current) return;
      setData(current); setError('');
      if (!restored.current && current.datos_servicio) setForm(current.datos_servicio);
      restored.current = true;
    } catch (err) { if (alive.current) setError(mensajeError(err, 'No se pudo consultar el servicio.')); }
  }, [incorporacion.id]);
  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; }; }, [refresh]);
  const working = data?.alta_automatica && !['publicada', 'fallida', 'eliminada'].includes(data.estado);
  useEffect(() => {
    if (!working && data?.estado !== 'eliminando') return;
    const poll = () => { if (document.visibilityState !== 'hidden' && !running.current) refresh(); };
    const timer = setInterval(poll, 3000);
    document.addEventListener('visibilitychange', poll);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', poll); };
  }, [working, data?.estado, refresh]);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => {
    if (data?.estado === 'publicada' && onPublished && !completed.current) {
      completed.current = true;
      onPublished();
    }
  }, [data?.estado, onPublished]);
  const act = async (action) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError('');
    const key = JSON.stringify([action, data?.preparacion_id, data?.revision, form]);
    try {
      const response = action === 'eliminar'
        ? await eliminarPreparacion(incorporacion.id, keys.current[key] ||= crypto.randomUUID())
        : await agregarAplicacion(incorporacion.id, form, keys.current[key] ||= crypto.randomUUID());
      if (alive.current) setData(response.data);
    } catch (err) { if (alive.current) setError(mensajeError(err, 'No se pudo completar la acción. Conservamos tus datos.')); }
    finally { running.current = false; if (alive.current) setBusy(false); }
  };
  const canAdd = data && !working && !['publicada', 'eliminando'].includes(data.estado);
  return <section className="simple-preparation" aria-label="Agregar aplicación al catálogo">
    {!data && !error && <p role="status">Cargando servicio…</p>}
    {error && <div className="callout bad" role="alert">{error}<button className="btn btn-secondary" onClick={refresh}>Volver a consultar</button></div>}
    {data?.mensaje && <p className="callout warn" role="alert">{data.mensaje}</p>}
    {(working || data?.estado === 'eliminando') && <div className="simple-preparation-status" role="status">
      <LoaderCircle className="library-spinner" size={30}/><h3>{data.estado === 'eliminando' ? 'Eliminando…' : 'Agregando servicio…'}</h3>
      <p>{data.progreso || 'NAP está completando la instalación y las comprobaciones.'}</p><p>Podés cerrar esta ventana.</p>
    </div>}
    {canAdd && <form className="col gap-3" onSubmit={event => { event.preventDefault(); act('agregar'); }}>
      <div className="field"><label htmlFor="simple-service-name">Nombre del servicio</label><input id="simple-service-name" className="input" required maxLength={100} disabled={busy} value={form.nombre} onChange={event => setForm({ ...form, nombre: event.target.value })}/></div>
      <div className="field"><label htmlFor="simple-service-description">Descripción</label><input id="simple-service-description" className="input" maxLength={2000} disabled={busy} placeholder="¿Para qué sirve? (opcional)" value={form.descripcion} onChange={event => setForm({ ...form, descripcion: event.target.value })}/></div>
      <button className="btn btn-primary" disabled={busy || (!data.puede_preparar && !data.preparacion_id)}><Plus size={17}/>{busy ? 'Agregando…' : data.estado === 'fallida' ? 'Reintentar alta' : 'Agregar al catálogo'}</button>
    </form>}
    {data?.estado === 'publicada' && <div className="simple-preparation-status is-ready"><CheckCircle2 size={30}/><h3>Servicio disponible</h3><p>Las cátedras ya pueden solicitarlo.</p><button className="btn btn-primary" onClick={onPublished}>Volver al catálogo</button></div>}
    {data?.preparacion_id && !['publicada', 'eliminada', 'eliminando'].includes(data.estado) && <button className="btn btn-ghost simple-preparation-delete" disabled={busy} onClick={() => act('eliminar')}><Trash2 size={15}/>Cancelar alta</button>}
  </section>;
}
