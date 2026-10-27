import { useEffect, useRef, useState } from 'react';
import { CalendarDays, CheckCircle2, ChevronDown, Info, Layers, LoaderCircle, Server, ShieldCheck } from 'lucide-react';
import { aprobarPedido, evaluarPedido, getCapacidad, getTemplates } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import PanelCapacidad from './PanelCapacidad';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';
import { Dialog } from './ui';
import SelectorTamano from './SelectorTamano';
import { recursosTamano, tamanosCompatibles, resumenRecursos } from '../utils/tamanos';
import useTamanos from '../hooks/useTamanos';
const EMPTY = [];
const fecha = (value) => value ? value.slice(0, 10).split('-').reverse().join('/') : '—';

export default function AprobarPedidoModal({ open, pedido, templates = EMPTY, onClose, onAprobado }) {
  const [profileOverrides, setProfileOverrides] = useState(null);
  const [templateId, setTemplateId] = useState('');
  const [sizeId, setSizeId] = useState('');
  const [resources, setResources] = useState({ vcpus: 1, ram_mb: 512, disk_gb: 4 });
  const [dates, setDates] = useState(vigenciaInicial);
  const [validDates, setValidDates] = useState(false);
  const [period, setPeriod] = useState(null);
  const [editDates, setEditDates] = useState(false);
  const [destination, setDestination] = useState('');
  const [destinations, setDestinations] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [justification, setJustification] = useState('');
  const [deployNow, setDeployNow] = useState(false);
  const [error, setError] = useState('');
  const [evaluating, setEvaluating] = useState(false);
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const request = useRef(null);
  const submitting = useRef(false);
  const key = useRef(crypto.randomUUID());
  const source = useRef({ pedido, templates });
  source.current = { pedido, templates };
  const pedidoId = pedido?.id;
  const renewal = pedido?.tipo === 'renovacion';
  const { sizes, loading: loadingSizes, error: sizesError, retry } = useTamanos(open && !renewal);
  const effectiveTemplates = profileOverrides || templates;
  const available = effectiveTemplates.filter((t) => renewal ? t.id === pedido?.template_id
    : t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === pedido?.modelo_servicio);
  useEffect(() => {
    if (!open || !pedidoId) return;
    let active = true;
    const { pedido: initial, templates: initialTemplates } = source.current;
    const template = initialTemplates.find((t) => t.id === initial.template_id);
    const snapshot = initial.asignacion_snapshot;
    sequence.current += 1; request.current?.abort();
    setProfileOverrides(null); setTemplateId(String(initial.template_id || '')); setSizeId('');
    setResources({ vcpus: snapshot?.vcpus ?? template?.default_vcpus ?? 1,
      ram_mb: snapshot?.ram_mb ?? template?.default_ram_mb ?? 512, disk_gb: snapshot?.disk_gb ?? template?.default_disk_gb ?? 4 });
    setDates(initial.vigencia ? { ...initial.vigencia } : vigenciaInicial()); setValidDates(false); setPeriod(null); setEditDates(false);
    setDestination(''); setDestinations([]); setEvaluation(null); setJustification(''); setDeployNow(false); setError('');
    setBusy(false); setEvaluating(false); submitting.current = false; key.current = crypto.randomUUID();
    getCapacidad().then(({ data }) => { if (active) setDestinations(data?.destinos || []); })
      .catch(() => { if (active) setDestinations([]); });
    return () => { active = false; sequence.current += 1; request.current?.abort(); };
  }, [open, pedidoId]);
  const selected = effectiveTemplates.find((t) => String(t.id) === templateId);
  const allowed = selected?.tamanos_permitidos ? sizes.filter((size) => selected.tamanos_permitidos.includes(size.id))
    : tamanosCompatibles(sizes, selected?.minimum_resources);
  const selectedSize = allowed.find((size) => size.id === sizeId) || allowed.find((size) => size.id === selected?.tamano_recomendado) || allowed[0];
  const definitionId = renewal ? pedido?.asignacion_snapshot?.definicion_version_id : selected?.definicion_version_id;
  const payload = { asignacion: { template_id: Number(templateId), ...(renewal ? resources : selectedSize ? recursosTamano(selectedSize) : {}),
    ...(!renewal && selectedSize ? { tamano: selectedSize.id } : {}), ...(definitionId ? { definicion_version_id: definitionId } : {}) }, vigencia: dates,
    ...(destination ? { destino: JSON.parse(destination) } : {}) };
  const payloadKey = JSON.stringify(payload);
  const canEvaluate = Boolean(open && pedidoId && templateId && validDates && (renewal || (selectedSize && !sizesError && !loadingSizes)));
  useEffect(() => {
    const current = ++sequence.current;
    const controller = new AbortController(); request.current = controller;
    setEvaluation(null);
    if (!canEvaluate) { setEvaluating(false); return () => controller.abort(); }
    setEvaluating(true);
    const timer = setTimeout(async () => {
      try {
        const { data } = await evaluarPedido(pedidoId, JSON.parse(payloadKey), controller.signal);
        if (sequence.current === current) { setEvaluation({ data, expires: Date.now() + 60000 }); key.current = crypto.randomUUID(); }
      } catch (err) { if (sequence.current === current && !controller.signal.aborted) setError(err); }
      finally { if (sequence.current === current) setEvaluating(false); }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); sequence.current += 1; };
  }, [canEvaluate, payloadKey, pedidoId, refresh]);
  const invalidate = () => {
    sequence.current += 1; request.current?.abort(); setEvaluation(null); setError(''); key.current = crypto.randomUUID();
  };
  const recheck = () => { invalidate(); setRefresh((value) => value + 1); };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !evaluation || !validDates) return;
    if (Date.now() >= evaluation.expires) { recheck(); return; }
    if (evaluation.data.justificacion_requerida && !justification.trim()) { setError('Explicá el motivo para aprobar con capacidad ajustada.'); return; }
    submitting.current = true; setBusy(true); setError('');
    try {
      const response = await aprobarPedido(pedidoId, { ...evaluation.data.seleccion, capacidad_token: evaluation.data.capacidad_token,
        ...(justification.trim() ? { justificacion_capacidad: justification.trim() } : {}), desplegar_inmediatamente: deployNow && !renewal && !future }, key.current);
      onAprobado?.(response.data); onClose();
    } catch (err) {
      setError(err);
      if (err.response?.status === 409) {
        setEvaluation(null);
        try { const { data } = await getTemplates(); setProfileOverrides(data); } catch { /* conservar selección y diagnóstico */ }
      }
    } finally { submitting.current = false; setBusy(false); }
  };
  if (!open || !pedido) return null;
  const blocked = Boolean(evaluation?.data.restricciones_fisicas?.length);
  const needsReason = Boolean(evaluation?.data.justificacion_requerida);
  const future = evaluation?.data.vigencia_efectiva?.inicio_at && Date.parse(evaluation.data.vigencia_efectiva.inicio_at) > Date.now();
  return <Dialog wide className="approval-dialog" title={`Aprobar pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="approval-form">
      <div className="approval-intro"><ShieldCheck size={22}/><div><strong>{pedido.catedra?.nombre || 'Revisá las condiciones del pedido'}</strong>
        <p>{pedido.parametros_extra?.titulo || 'Elegí el tamaño y confirmá las fechas. La disponibilidad se comprueba automáticamente.'}</p></div></div>
      <ErrorFormulario error={error}/>
      {!renewal && !pedido.template_id && <p className="callout"><strong>Servicio solicitado: {pedido.parametros_extra?.software_solicitado || 'Otro'}.</strong> Agregalo al catálogo y seleccionalo aquí.</p>}
      <div className="approval-grid">
        <section className="approval-section" aria-labelledby="approval-service-title">
          <h3 id="approval-service-title"><Server size={18}/>Servicio y tamaño</h3>
          <div className="field"><label htmlFor="approval-template">Servicio a entregar</label>
            <select id="approval-template" className="input" value={templateId} required disabled={busy || renewal} onChange={(e) => { setTemplateId(e.target.value); setSizeId(''); invalidate(); }}>
              <option value="">Seleccioná un servicio compatible</option>
              {available.map((t) => <option key={t.id} value={String(t.id)}>{renewal ? pedido.asignacion_snapshot?.nombre || t.nombre : t.nombre}</option>)}
              {renewal && !available.length && <option value={String(pedido.template_id)}>{pedido.asignacion_snapshot?.nombre || 'Asignación original'}</option>}
            </select></div>
          {renewal ? <div className="callout"><strong>Recursos originales</strong><p>{resumenRecursos(resources)}</p><p>La renovación conserva estos recursos.</p></div> : <>
            {loadingSizes && <p role="status">Cargando tamaños…</p>}
            {sizesError && <div role="alert" className="callout bad">{sizesError}<button type="button" className="btn btn-secondary" onClick={retry}>Reintentar carga de tamaños</button></div>}
            <SelectorTamano sizes={sizes} value={selectedSize?.id || ''} onChange={(value) => { setSizeId(value); invalidate(); }} allowed={allowed.map((size) => size.id)} disabled={busy} legend="Tamaño a asignar"/>
            {!loadingSizes && selected && !allowed.length && <p role="alert" className="callout warn">Este servicio necesita más recursos que Small y Medium.</p>}
          </>}
        </section>
        <section className="approval-section" aria-labelledby="approval-dates-title">
          <div className="approval-section-heading"><h3 id="approval-dates-title"><CalendarDays size={18}/>Fechas del servicio</h3>
            {period && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setEditDates(!editDates)}>{editDates ? 'Listo' : 'Cambiar fechas'}</button>}</div>
          {period && !editDates && <div className="approval-period"><span>Desde</span><strong>{fecha(period.desde)}</strong><span>Hasta</span><strong>{fecha(period.hasta)}</strong><p>Se conservan las fechas solicitadas por la cátedra.</p></div>}
          <fieldset className="approval-date-editor" disabled={busy} hidden={!editDates && Boolean(period)}><VigenciaFields value={dates}
            onChange={(value) => { setDates(value); invalidate(); }} onValid={setValidDates} onPeriodChange={setPeriod}/></fieldset>
        </section>
      </div>
      <section className={`approval-capacity ${blocked || needsReason ? 'is-warning' : evaluation ? 'is-ready' : ''}`} aria-label="Disponibilidad de recursos" aria-live="polite">
        <div className="approval-capacity-heading">{evaluating ? <LoaderCircle size={21} className="library-spinner"/> : evaluation && !blocked && !needsReason ? <CheckCircle2 size={21}/> : <Layers size={21}/>}
          <div><strong>{evaluating ? 'Comprobando disponibilidad…' : blocked ? 'No hay capacidad suficiente' : needsReason ? 'La capacidad está ajustada' : evaluation ? renewal ? 'Renovación lista para aprobar' : 'Hay capacidad para este pedido' : 'Disponibilidad pendiente de comprobar'}</strong>
            <p>{renewal ? 'La renovación conserva el servicio y sus datos.' : 'Los recursos se reservan al aprobar.'}</p></div>
          <button type="button" className="btn btn-ghost" disabled={busy || evaluating || !canEvaluate} onClick={recheck}>Actualizar disponibilidad</button></div>
        {evaluation && <details className="approval-capacity-details"><summary>Ver detalle de capacidad<ChevronDown size={14}/></summary><PanelCapacidad evaluacion={evaluation.data}/></details>}
      </section>
      {needsReason && <div className="field"><label htmlFor="approval-reason">Justificación de sobreasignación</label><textarea id="approval-reason" className="input" value={justification} maxLength={2000} disabled={busy} onChange={(e) => { setJustification(e.target.value); key.current = crypto.randomUUID(); }} required placeholder="Explicá por qué necesitás aprobar con esta capacidad."/></div>}
      {!renewal && destinations.length > 1 && <details className="approval-location"><summary>Ubicación del servicio</summary><label htmlFor="approval-destination">Destino autorizado</label><select id="approval-destination" className="input" value={destination} disabled={busy} onChange={(e) => { setDestination(e.target.value); invalidate(); }}>
        <option value="">Elegir automáticamente</option>{destinations.map((d) => <option key={`${d.destino.nodo}:${d.destino.storage}`} value={JSON.stringify(d.destino)}>{d.destino.nodo} / {d.destino.storage}</option>)}</select></details>}
      {evaluation?.data.cambio_version && <p className="callout"><Info size={16}/>Se usará la versión {evaluation.data.version_efectiva} del servicio y se informará a la cátedra.</p>}
      {!renewal && <label className="approval-deploy"><input type="checkbox" checked={deployNow && !future} disabled={busy || Boolean(future) || !evaluation} onChange={(e) => { setDeployNow(e.target.checked); key.current = crypto.randomUUID(); }}/>
        <span><strong>Desplegar después de aprobar</strong><small>{future ? 'Podrá desplegarse cuando comience la vigencia.' : 'Crear la instancia al confirmar este pedido.'}</small></span></label>}
      <div className="approval-actions"><button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || evaluating || !validDates || !evaluation || blocked || (needsReason && !justification.trim())}>{busy ? 'Aprobando…' : renewal ? 'Aprobar renovación' : 'Aprobar pedido'}</button></div>
    </form>
  </Dialog>;
}
