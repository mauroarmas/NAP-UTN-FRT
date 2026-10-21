import { useEffect, useRef, useState } from 'react';
import { crearDefinicion, getDefiniciones, guardarManifest, publicarDefinicion, retirarDefinicion, validarDefinicion } from '../services/api';
import { PageHead } from '../components/ui';
import RegistroEvidencia from '../components/RegistroEvidencia';
import { mensajeError } from '../utils/errors';

const MODELS = { linux: 'iaas', postgresql: 'paas', bookstack: 'saas' };
const serialize = (row) => JSON.stringify(row?.manifest || {}, null, 2);

export default function Definiciones() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ codigo: '', version: '1.0.0', producto: 'linux' });
  const [manifest, setManifest] = useState('{}');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const keys = useRef({});
  useEffect(() => {
    let active = true;
    getDefiniciones(true).then(({ data }) => { if (active) setRows(data); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar las definiciones.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const pick = (row) => { setSelected(row); setManifest(serialize(row)); setReason(''); setError(''); setStatus(''); };
  const act = async (name, callback) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError(''); setStatus('');
    const fingerprint = JSON.stringify([name, selected?.id, name === 'create' ? form : name === 'save' ? manifest : reason]);
    const key = keys.current[fingerprint] ||= crypto.randomUUID();
    try {
      const { data } = await callback(key);
      setRows((current) => [data, ...current.filter((row) => row.id !== data.id)]);
      setSelected(data); setManifest(serialize(data)); setReason('');
      setStatus('Cambio registrado.');
      if (name === 'create') setForm({ codigo: '', version: '1.0.0', producto: 'linux' });
    } catch (err) { setError(mensajeError(err, 'No se confirmó el cambio. Conservamos los datos.')); }
    finally { running.current = false; setBusy(false); }
  };
  const dirty = selected && manifest !== serialize(selected);
  return <div className="fade-in">
    <PageHead kicker="Administración" title="Definiciones de servicio"
      subtitle="Prepará una versión, registrá sus ensayos y publicala para ofrecer perfiles de recursos." />
    {error && <p role="alert" className="callout bad">{error}</p>}
    {status && <p role="status">{status}</p>}
    <section className="card mb-4">
      <h2>Nueva versión</h2>
      <form className="col gap-3" onSubmit={(event) => { event.preventDefault(); act('create', (key) => crearDefinicion({ ...form, modelo_servicio: MODELS[form.producto] }, key)); }}>
        <div className="grid cols-3">
          <div className="field"><label htmlFor="definition-code">Código</label><input id="definition-code" className="input" required pattern="[a-z][a-z0-9-]{2,63}" value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} /></div>
          <div className="field"><label htmlFor="definition-version">Versión</label><input id="definition-version" className="input" required pattern="[1-9][0-9]*\.[0-9]+\.[0-9]+" value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></div>
          <div className="field"><label htmlFor="definition-product">Producto</label><select id="definition-product" className="input" value={form.producto} onChange={(e) => setForm({ ...form, producto: e.target.value })}>
            <option value="linux">Linux · IaaS</option><option value="postgresql">PostgreSQL · PaaS</option><option value="bookstack">BookStack · SaaS de referencia</option>
          </select></div>
        </div>
        <button className="btn btn-primary" disabled={busy}>Crear borrador</button>
      </form>
    </section>
    {loading && <p role="status">Cargando versiones…</p>}
    <nav aria-label="Versiones de definiciones" className="row wrap gap-2 mb-4">
      {rows.map((row) => <button type="button" className="btn btn-secondary" key={row.id} disabled={busy} aria-pressed={selected?.id === row.id} onClick={() => pick(row)}>{row.codigo} {row.version} · {row.estado}</button>)}
    </nav>
    {selected && <section className="card mb-4">
      <h2>Versión seleccionada: {selected.codigo} {selected.version}</h2>
      <p>Estado: {selected.estado}. Modelo: {selected.modelo_servicio?.toUpperCase()}.</p>
      {selected.manifest_sha256 && <p>SHA-256 del manifiesto: <code>{selected.manifest_sha256}</code></p>}
      <p>Usá el manifiesto emitido por el builder y completado con la referencia de evidencia. La validación comprueba archivos, perfiles y ensayos; publicar requiere otra acción.</p>
      <div className="field"><label htmlFor="definition-manifest">Manifiesto JSON</label><textarea id="definition-manifest" className="input" rows={16} readOnly={selected.estado !== 'borrador'} spellCheck={false} value={manifest} onChange={(e) => setManifest(e.target.value)} /></div>
      <div className="row wrap gap-2">
        {selected.estado === 'borrador' && <><button className="btn btn-secondary" disabled={busy || !dirty} onClick={() => act('save', (key) => guardarManifest(selected.id, manifest, key))}>Guardar manifiesto</button>
          <button className="btn btn-primary" disabled={busy || dirty} onClick={() => act('validate', (key) => validarDefinicion(selected.id, key))}>Validar versión</button></>}
        {selected.estado === 'validada' && <button className="btn btn-primary" disabled={busy} onClick={() => act('publish', (key) => publicarDefinicion(selected.id, key))}>Publicar versión</button>}
      </div>
      {['validada', 'publicada'].includes(selected.estado) && <form className="col gap-2 mt-4" onSubmit={(e) => { e.preventDefault(); act('retire', (key) => retirarDefinicion(selected.id, reason.trim(), key)); }}>
        <div className="field"><label htmlFor="definition-reason">Motivo del retiro</label><input id="definition-reason" className="input" required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        <p>El retiro impide nuevas solicitudes y conserva las aprobaciones y servicios existentes.</p>
        <button className="btn btn-danger" disabled={busy || !reason.trim()}>Retirar versión</button>
      </form>}
    </section>}
    <RegistroEvidencia onRegistered={() => setStatus('Evidencia registrada. Completá el manifiesto con su UUID y SHA-256 antes de validarlo.')} />
  </div>;
}
