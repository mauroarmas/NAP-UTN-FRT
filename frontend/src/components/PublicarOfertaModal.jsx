import { useEffect, useState } from 'react';
import { getTemplates } from '../services/api';
import useTamanos from '../hooks/useTamanos';
import SelectorTamano from './SelectorTamano';
import { tamanosCompatibles } from '../utils/tamanos';
import { mensajeError } from '../utils/errors';

export default function PublicarOfertaModal({ trial, busy, onPublish }) {
  const [form, setForm] = useState({ nombre: 'Draw.io', descripcion: 'Creación de diagramas para las prácticas de la cátedra', tamano: '', target: '' });
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const { sizes, loading: loadingSizes, error: sizesError, retry } = useTamanos();
  const allowed = tamanosCompatibles(sizes, trial.definicion?.minimum_resources);
  const chosen = allowed.find((size) => size.id === form.tamano) || allowed[0];
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    getTemplates(true).then(({ data }) => { if (active) setOffers(data.filter((row) => row.codigo_definicion === trial.definicion.codigo)); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron consultar los servicios existentes.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [trial.definicion.codigo, attempt]);
  const target = offers.find((row) => String(row.id) === form.target);
  return <form className="col gap-3 service-publish" onSubmit={(event) => {
    event.preventDefault();
    if (!chosen || loading || loadingSizes || busy || error || sizesError || (form.target && !target)) return;
    onPublish({ revision_esperada: trial.definicion.revision, ensayo_id: trial.id, perfil: {
      nombre: form.nombre.trim(), descripcion: form.descripcion.trim(), tamano: chosen.id,
      default_vcpus: chosen.vcpus, default_ram_mb: chosen.ram_mb, default_disk_gb: chosen.disk_gb,
      ...(target ? { template_id: target.id, revision_esperada: target.revision } : {}),
    } });
  }}>
    <h3>Publicar en el catálogo</h3>
    <p>La cátedra verá el nombre y la descripción. El tamaño será una recomendación para quien apruebe el pedido.</p>
    {(loading || loadingSizes) && <p role="status">Cargando opciones de publicación…</p>}
    {(error || sizesError) && <div role="alert" className="callout bad">{error || sizesError}<button type="button" className="btn btn-secondary" onClick={() => { setAttempt((value) => value + 1); retry(); }}>Reintentar carga</button></div>}
    {offers.length > 0 && <div className="field"><label htmlFor="offer-target">Servicio del catálogo</label><select id="offer-target" className="input" value={form.target} disabled={busy} onChange={(event) => {
      const offer = offers.find((row) => String(row.id) === event.target.value);
      setForm({ ...form, target: event.target.value, nombre: offer?.nombre || form.nombre, descripcion: offer?.descripcion || form.descripcion, tamano: offer?.tamano_recomendado || '' });
    }}><option value="">Crear un servicio nuevo</option>{offers.map((row) => <option key={row.id} value={String(row.id)}>Actualizar {row.nombre} · {row.version_ofrecida}</option>)}</select></div>}
    <div className="field"><label htmlFor="offer-name">Nombre en el catálogo</label><input id="offer-name" className="input" required maxLength={100} disabled={busy} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></div>
    <div className="field"><label htmlFor="offer-description">Descripción en el catálogo</label><textarea id="offer-description" className="input" rows={3} maxLength={4000} disabled={busy} value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} /></div>
    <SelectorTamano sizes={sizes} value={chosen?.id || ''} onChange={(tamano) => setForm({ ...form, tamano })} allowed={allowed.map((size) => size.id)} disabled={busy} name="publication-size" legend="Tamaño recomendado" />
    {!loadingSizes && !allowed.length && <p className="callout warn" role="alert">La preparación comprobada supera Small y Medium, o todavía no informa sus mínimos. Se necesita una preparación compatible antes de publicarla con estos tamaños.</p>}
    <button className="btn btn-primary" disabled={busy || loading || loadingSizes || Boolean(error || sizesError) || !chosen}>Publicar oferta</button>
  </form>;
}
