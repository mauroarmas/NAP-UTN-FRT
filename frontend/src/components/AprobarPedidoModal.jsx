import { useEffect, useRef, useState } from 'react';
import { aprobarPedido, evaluarPedido, getCapacidad } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import PanelCapacidad from './PanelCapacidad';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';
import { Dialog } from './ui';
const EMPTY = [];

export default function AprobarPedidoModal({ open, pedido, templates = EMPTY, onClose, onAprobado }) {
  const [templateId, setTemplateId] = useState('');
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
  const available = templates.filter((t) => renewal ? t.id === pedido?.template_id
    : t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === pedido?.modelo_servicio);
  useEffect(() => {
    if (!open || !pedido) return;
    let active = true;
    sequence.current += 1; request.current?.abort();
    const template = templates.find((t) => t.id === pedido.template_id);
    const snapshot = pedido.asignacion_snapshot;
    setTemplateId(String(pedido.template_id || ''));
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
  const selected = templates.find((t) => String(t.id) === templateId);
  const definitionId = renewal ? pedido.asignacion_snapshot?.definicion_version_id : selected?.definicion_version_id;
  const payload = { asignacion: { template_id: Number(templateId),
    ...Object.fromEntries(Object.entries(resources).map(([name, value]) => [name, Number(value)])),
    ...(definitionId ? { definicion_version_id: definitionId } : {}) }, vigencia: dates,
    ...(destination ? { destino: JSON.parse(destination) } : {}) };
  const invalidate = () => {
    sequence.current += 1; request.current?.abort(); setEvaluation(null); setEvaluating(false);
    key.current = crypto.randomUUID(); setError('');
  };
  const evaluate = async () => {
    if (busy || evaluating) return;
    if (!templateId || !validDates || Object.values(resources).some((value) => !Number.isInteger(Number(value)) || Number(value) <= 0)) {
      setError('Revisá plantilla, recursos positivos y vigencia completa.'); return;
    }
    const current = ++sequence.current;
    const controller = new AbortController(); request.current = controller;
    setEvaluating(true); setError(''); setEvaluation(null);
    try {
      const { data } = await evaluarPedido(pedido.id, payload, controller.signal);
      if (sequence.current === current) setEvaluation({ data, expires: Date.now() + 60000 });
    } catch (err) { if (sequence.current === current) setError(err); }
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
      if (err.response?.status === 409) setEvaluation(null);
    } finally { submitting.current = false; setBusy(false); }
  };
  const changeTemplate = (value) => {
    const t = templates.find((item) => String(item.id) === value);
    setTemplateId(value);
    if (t) setResources({ vcpus: t.default_vcpus, ram_mb: t.default_ram_mb, disk_gb: t.default_disk_gb });
    invalidate();
  };
  return <Dialog wide title={`Aprobar pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="col gap-3">
      <ErrorFormulario error={error} />
      {!renewal && !pedido.template_id && <div className="callout">
        <strong>Servicio solicitado: {pedido.parametros_extra?.software_solicitado || 'Otro'}</strong>
        <p>Prepará el servicio y agregalo al catálogo. Después seleccioná aquí su oferta publicada para evaluar y aprobar la asignación de este pedido.</p>
      </div>}
      <label htmlFor="approval-template">Plantilla</label>
      <select id="approval-template" value={templateId} onChange={(e) => changeTemplate(e.target.value)} disabled={busy || renewal} required>
        <option value="">Seleccioná una plantilla compatible</option>
        {available.map((t) => <option key={t.id} value={String(t.id)}>{renewal ? pedido.asignacion_snapshot?.nombre || t.nombre : t.nombre}</option>)}
        {renewal && !available.length && <option value={String(pedido.template_id)}>{pedido.asignacion_snapshot?.nombre || 'Asignación histórica'}</option>}
      </select>
      <fieldset disabled={busy || renewal} className="row gap-2">
        <legend>Recursos efectivos</legend>
        {[['vcpus', 'vCPU'], ['ram_mb', 'RAM (MiB)'], ['disk_gb', 'Disco (GiB)']].map(([name, label]) => <label key={name}>{label}
          <input aria-label={label} type="number" min="1" step="1" value={resources[name]} onChange={(e) => { setResources((previous) => ({ ...previous, [name]: e.target.value })); invalidate(); }} required />
        </label>)}
      </fieldset>
      <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => { setDates(value); invalidate(); }} onValid={setValidDates} /></fieldset>
      {!renewal && <><label htmlFor="approval-destination">Destino autorizado</label>
        <select id="approval-destination" value={destination} onChange={(e) => { setDestination(e.target.value); invalidate(); }} disabled={busy}>
          <option value="">Selección automática entre destinos elegibles</option>
          {destinations.map((d) => <option key={`${d.destino.nodo}:${d.destino.storage}`} value={JSON.stringify(d.destino)}>{d.destino.nodo} / {d.destino.storage}</option>)}
        </select></>}
      <button type="button" className="btn btn-secondary" onClick={evaluate} disabled={busy || evaluating || !validDates}>{evaluating ? 'Evaluando…' : 'Evaluar asignación'}</button>
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
