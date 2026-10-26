import { useEffect, useRef, useState } from 'react';
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

export default function AprobarPedidoModal({ open, pedido, templates = EMPTY, onClose, onAprobado }) {
  const [profileOverrides, setProfileOverrides] = useState(null);
  const effectiveTemplates = profileOverrides || templates;
  const [templateId, setTemplateId] = useState('');
  const [sizeId, setSizeId] = useState('');
  const [resources, setResources] = useState({ vcpus: 1, ram_mb: 512, disk_gb: 4 });
  const [dates, setDates] = useState(vigenciaInicial);
  const [validDates, setValidDates] = useState(false);
  const [destination, setDestination] = useState('');
  const [destinations, setDestinations] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [justification, setJustification] = useState('');
  const [deployNow, setDeployNow] = useState(false);
  const [error, setError] = useState('');
  const [evaluating, setEvaluating] = useState(false);
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const request = useRef(null);
  const submitting = useRef(false);
  const key = useRef(crypto.randomUUID());
  const renewal = pedido?.tipo === 'renovacion';
  const { sizes, loading: loadingSizes, error: sizesError, retry } = useTamanos(open && !renewal);
  const available = effectiveTemplates.filter((t) => renewal ? t.id === pedido?.template_id
    : t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === pedido?.modelo_servicio);
  useEffect(() => {
    if (!open || !pedido) return;
    let active = true;
    sequence.current += 1; request.current?.abort();
    setProfileOverrides(null);
    const template = templates.find((t) => t.id === pedido.template_id);
    const snapshot = pedido.asignacion_snapshot;
    setTemplateId(String(pedido.template_id || ''));
    setSizeId('');
    setResources({ vcpus: snapshot?.vcpus ?? template?.default_vcpus ?? 1,
      ram_mb: snapshot?.ram_mb ?? template?.default_ram_mb ?? 512, disk_gb: snapshot?.disk_gb ?? template?.default_disk_gb ?? 4 });
    setDates(pedido.vigencia ? { ...pedido.vigencia } : vigenciaInicial()); setValidDates(false);
    setDestination(''); setEvaluation(null); setJustification(''); setDeployNow(false); setError('');
    setBusy(false); setEvaluating(false); submitting.current = false; key.current = crypto.randomUUID();
    getCapacidad().then((response) => { if (active) setDestinations(response?.data?.destinos || []); })
      .catch(() => { if (active) setDestinations([]); });
    return () => { active = false; sequence.current += 1; request.current?.abort(); };
  }, [open, pedido, templates]);
  if (!open || !pedido) return null;
  const selected = effectiveTemplates.find((t) => String(t.id) === templateId);
  const allowed = selected?.tamanos_permitidos ? sizes.filter((size) => selected.tamanos_permitidos.includes(size.id))
    : tamanosCompatibles(sizes, selected?.minimum_resources);
  const selectedSize = allowed.find((size) => size.id === sizeId) || allowed.find((size) => size.id === selected?.tamano_recomendado) || allowed[0];
  const effectiveResources = renewal ? resources : selectedSize ? recursosTamano(selectedSize) : {};
  const definitionId = renewal ? pedido.asignacion_snapshot?.definicion_version_id : selected?.definicion_version_id;
  const payload = { asignacion: { template_id: Number(templateId),
    ...effectiveResources, ...(!renewal && selectedSize ? { tamano: selectedSize.id } : {}),
    ...(definitionId ? { definicion_version_id: definitionId } : {}) }, vigencia: dates,
    ...(destination ? { destino: JSON.parse(destination) } : {}) };
  const invalidate = () => {
    sequence.current += 1; request.current?.abort(); setEvaluation(null); setEvaluating(false);
    key.current = crypto.randomUUID(); setError('');
  };
  const evaluate = async () => {
    if (busy || evaluating) return;
    if (!templateId || !validDates || (!renewal && (!selectedSize || sizesError || loadingSizes))) {
      setError('Seleccioná un servicio, un tamaño compatible y la vigencia completa.'); return;
    }
    const current = ++sequence.current;
    const controller = new AbortController(); request.current = controller;
    setEvaluating(true); setError(''); setEvaluation(null);
    try {
      const { data } = await evaluarPedido(pedido.id, payload, controller.signal);
      if (sequence.current === current) setEvaluation({ data, expires: Date.now() + 60000 });
    } catch (err) { if (sequence.current === current) { setError(err);
      if (err.response?.status === 409) { try { const {data} = await getTemplates(); setProfileOverrides(data); } catch { /* conservar error y campos */ } }
    } }
    finally { if (sequence.current === current) setEvaluating(false); }
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !evaluation || !validDates) return;
    if (Date.now() >= evaluation.expires) { setEvaluation(null); setError('La evaluación venció. Evaluá nuevamente.'); return; }
    if (evaluation.data.justificacion_requerida && !justification.trim()) { setError('Ingresá la justificación de sobreasignación.'); return; }
    submitting.current = true; setBusy(true); setError('');
    try {
      const body = { ...evaluation.data.seleccion, capacidad_token: evaluation.data.capacidad_token,
        ...(justification.trim() ? { justificacion_capacidad: justification.trim() } : {}), desplegar_inmediatamente: deployNow && !renewal };
      const response = await aprobarPedido(pedido.id, body, key.current);
      onAprobado?.(response.data); onClose();
    } catch (err) {
      setError(err);
      if (err.response?.status === 409) { setEvaluation(null);
        try { const {data} = await getTemplates(); setProfileOverrides(data); } catch { /* conservar error y campos */ }
      }
    } finally { submitting.current = false; setBusy(false); }
  };
  const changeTemplate = (value) => {
    const t = effectiveTemplates.find((item) => String(item.id) === value);
    setTemplateId(value);
    setSizeId('');
    if (t) setResources({ vcpus: t.default_vcpus, ram_mb: t.default_ram_mb, disk_gb: t.default_disk_gb });
    invalidate();
  };
  return <Dialog wide title={`Aprobar pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="col gap-3">
      {evaluation?.data?.version_efectiva && <p role="status">Versión solicitada: {evaluation.data.version_solicitada || 'sin versión previa'}. Versión a autorizar: {evaluation.data.version_efectiva}.{evaluation.data.cambio_version ? ' Se informará el cambio a la cátedra sin pedir confirmación adicional.' : ''}</p>}
      <ErrorFormulario error={error} />
      {!renewal && !pedido.template_id && <div className="callout">
        <strong>Servicio solicitado: {pedido.parametros_extra?.software_solicitado || 'Otro'}</strong>
        <p>Prepará el servicio y agregalo al catálogo. Después seleccioná aquí su oferta publicada para evaluar y aprobar la asignación de este pedido.</p>
      </div>}
      <label htmlFor="approval-template">Servicio a entregar</label>
      <select id="approval-template" value={templateId} onChange={(e) => changeTemplate(e.target.value)} disabled={busy || renewal} required>
        <option value="">Seleccioná un servicio compatible</option>
        {available.map((t) => <option key={t.id} value={String(t.id)}>{renewal ? pedido.asignacion_snapshot?.nombre || t.nombre : t.nombre}</option>)}
        {renewal && !available.length && <option value={String(pedido.template_id)}>{pedido.asignacion_snapshot?.nombre || 'Asignación histórica'}</option>}
      </select>
      {renewal ? <div className="callout"><strong>Recursos de la asignación original</strong><p>{resumenRecursos(resources)}</p><p>La renovación conserva estos recursos.</p></div> : <>
        {loadingSizes && <p role="status">Cargando tamaños…</p>}
        {sizesError && <div role="alert" className="callout bad">{sizesError}<button type="button" className="btn btn-secondary" onClick={retry}>Reintentar carga de tamaños</button></div>}
        <SelectorTamano sizes={sizes} value={selectedSize?.id || ''} onChange={(value) => { setSizeId(value); invalidate(); }} allowed={allowed.map((size) => size.id)} disabled={busy} legend="Tamaño a asignar" />
        {!loadingSizes && selected && !allowed.length && <p role="alert" className="callout warn">Los tamaños Small y Medium no alcanzan los mínimos comprobados de este servicio. Revisá su preparación antes de aprobar.</p>}
        <p className="card-meta">Ambos tamaños usan la misma base Linux. Los recursos se reservan al confirmar la aprobación.</p>
      </>}
      <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => { setDates(value); invalidate(); }} onValid={setValidDates} /></fieldset>
      {!renewal && <><label htmlFor="approval-destination">Destino autorizado</label>
        <select id="approval-destination" value={destination} onChange={(e) => { setDestination(e.target.value); invalidate(); }} disabled={busy}>
          <option value="">Selección automática entre destinos elegibles</option>
          {destinations.map((d) => <option key={`${d.destino.nodo}:${d.destino.storage}`} value={JSON.stringify(d.destino)}>{d.destino.nodo} / {d.destino.storage}</option>)}
        </select></>}
      <button type="button" className="btn btn-secondary" onClick={evaluate} disabled={busy || evaluating || !validDates || (!renewal && (!selectedSize || loadingSizes || Boolean(sizesError)))}>{evaluating ? 'Evaluando…' : 'Evaluar asignación'}</button>
      {evaluation && <PanelCapacidad evaluacion={evaluation.data} />}
      {evaluation?.data.justificacion_requerida && <label>Justificación de sobreasignación
        <textarea aria-label="Justificación de sobreasignación" value={justification} maxLength={2000} onChange={(e) => { setJustification(e.target.value); key.current = crypto.randomUUID(); }} required />
      </label>}
      {!renewal && <label><input type="checkbox" checked={deployNow} disabled={busy} onChange={(e) => { setDeployNow(e.target.checked); key.current = crypto.randomUUID(); }} />Solicitar despliegue después de aprobar, si la fecha inicial ya está habilitada.</label>}
      {renewal && <p>La renovación registra condiciones. El estado del contenedor y sus datos se conservan.</p>}
      <div className="row gap-2"><button type="button" onClick={onClose} disabled={busy}>Cerrar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || !validDates || !evaluation || Boolean(evaluation?.data.restricciones_fisicas?.length)}>{busy ? 'Guardando…' : renewal ? 'Aprobar renovación' : 'Aprobar asignación'}</button></div>
    </form>
  </Dialog>;
}
