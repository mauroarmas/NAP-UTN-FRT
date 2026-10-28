import { useCallback, useEffect, useRef, useState } from 'react';
import { Layers, Package, Pencil, Plus, RefreshCw, Search } from 'lucide-react';
import { cambiarConfiguracionAplicacion, getTemplates, reactivarTemplate, retirarTemplate, sincronizarIaas } from '../services/api';
import { Dialog, Empty, PageHead, StatusPill } from '../components/ui';
import AgregarServicioModal from '../components/AgregarServicioModal';
import TemplatesAdmin from '../components/TemplatesAdmin';
import NuevoPedidoModal from '../components/NuevoPedidoModal';
import { Link } from 'react-router-dom';
import { resumenRecursos } from '../utils/tamanos';
import useTamanos from '../hooks/useTamanos';
import { mensajeError } from '../utils/errors';
import { MODELOS_SERVICIO } from '../utils/catalogo';

const MODELS = Object.fromEntries(MODELOS_SERVICIO);

export default function Definiciones({ user }) {
  const [addition, setAddition] = useState(() => new URLSearchParams(window.location.search).get('vista') === 'preparacion' ? 'biblioteca' : null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [syncError, setSyncError] = useState('');
  const [search, setSearch] = useState('');
  const [model, setModel] = useState('todos');
  const [requested, setRequested] = useState(null);
  const [created, setCreated] = useState(null);
  const [showRetired, setShowRetired] = useState(false);
  const [editor, setEditor] = useState(null);
  const [retiring, setRetiring] = useState(null);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const running = useRef(false);
  const { sizes, loading: loadingSizes, error: sizesError, retry } = useTamanos();
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    setSyncError('');
    try { await sincronizarIaas(); }
    catch (err) { if (alive.current) setSyncError(mensajeError(err, 'No se pudo actualizar IaaS desde Proxmox. Se conserva el catálogo anterior.')); }
    try { const { data } = await getTemplates(true); if (alive.current) setRows(data); }
    catch (err) { if (alive.current) setError(mensajeError(err, 'No se pudieron cargar los servicios.')); }
    finally { if (alive.current) setLoading(false); }
  }, []);
  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; }; }, [refresh]);
  useEffect(() => {
    // Un alta continúa aunque se cierre el diálogo: ofrecerla sin exigir recargar la página.
    const poll = async () => {
      if (document.visibilityState === 'hidden' || running.current) return;
      try { const { data } = await getTemplates(true); if (alive.current) setRows(data); }
      catch { /* La consulta explícita ofrece el diagnóstico; conservar el catálogo visible. */ }
    };
    const timer = setInterval(poll, 10000);
    document.addEventListener('visibilitychange', poll);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', poll); };
  }, []);
  const changeAvailability = async (row) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError('');
    try {
      await (row.activo ? retirarTemplate(row.id) : reactivarTemplate(row.id));
      setRetiring(null); setNotice(row.activo ? `${row.nombre} se retiró del catálogo. Los pedidos aprobados y servicios existentes se conservan.` : `${row.nombre} volvió al catálogo.`);
      await refresh();
    } catch (err) { setError(mensajeError(err, 'No se pudo cambiar la disponibilidad del servicio.')); }
    finally { running.current = false; setBusy(false); }
  };
  const updateProfileConfiguration = async (row) => {
    if (running.current || !row.configuracion_actualizacion) return;
    running.current = true; setBusy(true); setError('');
    try {
      await cambiarConfiguracionAplicacion(row.id, { ...row.configuracion_actualizacion, revision_esperada: row.revision });
      setNotice(`${row.nombre} se actualizó al perfil actual de infraestructura y ya está disponible para solicitar.`);
      await refresh();
    } catch (err) { setError(mensajeError(err, 'No se pudo actualizar la configuración de la aplicación.')); }
    finally { running.current = false; setBusy(false); }
  };
  const visible = rows.filter((row) => (showRetired || row.activo) && (model === 'todos' || row.modelo_servicio === model) &&
    `${row.nombre} ${row.descripcion || ''}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  return <div className="fade-in service-admin">
    <PageHead kicker="Administración" title="Catálogo de servicios"
      subtitle="Elegí los servicios que pueden solicitar las cátedras. Cada pedido aprobado tendrá su propia instancia." />
    <section className="service-sizes" aria-label="Tamaños compartidos">
      <div className="service-sizes__intro"><Layers size={20} /><div><strong>Dos tamaños para los servicios</strong>
        <p>Contenedores LXC. El administrador elige el tamaño al aprobar.</p></div></div>
      {loadingSizes && <p role="status">Cargando tamaños…</p>}
      {sizes.map((size) => <div className="service-sizes__item" key={size.id}><strong>{size.nombre}</strong><span>{resumenRecursos(size)}</span></div>)}
      {sizesError && <div role="alert">{sizesError} <button className="btn btn-secondary" onClick={retry}>Reintentar</button></div>}
    </section>
    {error && <div role="alert" className="callout bad">{error}<button className="btn btn-secondary" onClick={refresh}>Volver a cargar servicios</button></div>}
    {syncError && <div role="alert" className="callout warn">{syncError}<button className="btn btn-secondary" onClick={refresh}>Actualizar catálogo</button></div>}
    {notice && <p role="status" className="callout">{notice}</p>}
    {created && <p role="status" className="callout">Solicitud #{created.id} registrada. <Link to="/pedidos">Ver seguimiento</Link></p>}
    <section aria-labelledby="available-services-title">
      <div className="service-list-heading"><div><h2 id="available-services-title">Servicios disponibles</h2><p>Administrá las aplicaciones que pueden solicitar las cátedras.</p></div>
        <div className="row gap-2"><button className="btn btn-secondary" disabled={loading} onClick={refresh}>Actualizar catálogo</button>
        <button className="btn btn-primary" onClick={() => setAddition('biblioteca')}><Plus size={17} /> Agregar servicio</button></div>
      </div>
      <div className="service-toolbar">
        <label className="service-search"><Search size={16} /><input className="input" aria-label="Buscar servicio" type="search" placeholder="Buscar servicio…" value={search} onChange={(e) => setSearch(e.target.value)} /></label>
        <select className="input service-model-filter" aria-label="Tipo de servicio" value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="todos">Todos los tipos</option>{MODELOS_SERVICIO.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <label className="row gap-2"><input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} /> Mostrar retirados</label>
      </div>
      {loading ? <p role="status">Cargando servicios…</p> : !visible.length ? <Empty icon={<Package size={24} />} hint={search || showRetired ? 'Probá otra búsqueda o revisá los filtros.' : 'Agregá una aplicación preparada o buscá una nueva en la biblioteca.'}>No hay servicios para mostrar.</Empty> :
        <div className="service-card-grid">{visible.map((row) => <article className="card service-card" key={row.id}>
          <div className="row between gap-2"><span className="service-card__category">{MODELS[row.modelo_servicio] || 'Servicio'}</span>
            <StatusPill kind={!row.activo ? 'off' : row.oferta_disponible ? 'ok' : 'warn'}>{!row.activo ? 'Retirado' : row.oferta_disponible ? 'Disponible' : row.requiere_actualizar_perfil ? 'Requiere actualizar' : 'Revisar conexión'}</StatusPill></div>
          <h2>{row.nombre}</h2><p className="service-card__description">{row.descripcion || 'Agregá una descripción para ayudar a las cátedras a elegir.'}</p>
          {row.version_ofrecida && <span className="card-meta">Versión {row.version_ofrecida}</span>}
          <div className="service-card__sizes"><span className="card-meta">Tamaños compatibles</span><div className="row wrap gap-2">
            {(row.tamanos_permitidos || []).map((id) => <span className="service-size-badge" key={id}>{id === 'small' ? 'Small' : 'Medium'}{id === row.tamano_recomendado ? ' · recomendado' : ''}</span>)}
            {!row.tamanos_permitidos?.length && <span className="card-meta">Sin tamaño compatible con la preparación actual</span>}
          </div></div>
          <div className="service-card__actions">
            {row.activo && row.oferta_disponible && row.tipo === 'lxc' && <button className="btn btn-primary" onClick={() => setRequested(row)}>Solicitar {row.nombre}</button>}
            {row.activo && row.requiere_actualizar_perfil && row.configuracion_actualizacion && <button className="btn btn-primary" disabled={busy} onClick={() => updateProfileConfiguration(row)}><RefreshCw size={15} /> Actualizar aplicación</button>}
            <button className="btn btn-secondary" onClick={() => setEditor(row)}><Pencil size={15} /> Editar servicio</button>
            <button className="btn btn-ghost" disabled={busy} onClick={() => row.activo ? setRetiring(row) : changeAvailability(row)}>{row.activo ? 'Retirar' : 'Volver a ofrecer'}</button></div>
        </article>)}</div>}
      <p className="card-meta mt-4">Los recursos se reservan al aprobar cada pedido. Las bases Linux de Proxmox aparecen automáticamente.</p>
    </section>
    {addition && <AgregarServicioModal initialLibrary={addition === 'biblioteca'} onClose={() => setAddition(null)} onChanged={refresh}
      onGuardado={() => { refresh(); setNotice('Servicio guardado. Ya podés consultarlo en Servicios disponibles.'); }} />}
    <TemplatesAdmin open={Boolean(editor)} template={editor} onClose={() => setEditor(null)} onGuardado={() => { refresh(); setNotice('Servicio guardado. Las asignaciones ya aprobadas conservan sus recursos.'); }} />
    <NuevoPedidoModal open={Boolean(requested)} initialTemplate={requested} user={user} onClose={() => setRequested(null)} onCreated={setCreated} />
    {retiring && <Dialog title={`Retirar ${retiring.nombre}`} onClose={() => { if (!busy) setRetiring(null); }} closeDisabled={busy}>
      <p>Dejará de ofrecerse en pedidos nuevos. Los pedidos aprobados, el historial y las instancias existentes se conservan.</p>
      {error && <p role="alert" className="callout bad">{error}</p>}
      <div className="dialog-form-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => setRetiring(null)}>Cancelar</button><button className="btn btn-danger" disabled={busy} onClick={() => changeAvailability(retiring)}>{busy ? 'Retirando…' : 'Retirar del catálogo'}</button></div>
    </Dialog>}
  </div>;
}
