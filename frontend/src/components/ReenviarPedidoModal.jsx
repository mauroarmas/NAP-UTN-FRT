import { useEffect, useRef, useState } from 'react';
import { getTemplates, reenviarPedido } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import { Dialog } from './ui';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';

export default function ReenviarPedidoModal({ open, pedido, user, onClose, onReenviado }) {
  const [templates, setTemplates] = useState([]);
  const [model, setModel] = useState('iaas');
  const [templateId, setTemplateId] = useState('');
  const [description, setDescription] = useState('');
  const [title, setTitle] = useState('');
  const [otherName, setOtherName] = useState('');
  const [dates, setDates] = useState(vigenciaInicial);
  const [validDates, setValidDates] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  const admin = user?.rol === 'admin';
  const renewal = pedido?.tipo === 'renovacion';
  const canReply = admin || pedido?.estado === 'requiere_ajuste';
  useEffect(() => {
    if (!open || !pedido || !canReply) return;
    let active = true;
    setModel(pedido.modelo_servicio); setTemplateId(pedido.template_id ? String(pedido.template_id) : pedido.modelo_servicio !== 'iaas' ? 'otro' : ''); setDescription(pedido.descripcion_requerimientos || '');
    setTitle(pedido.parametros_extra?.titulo || ''); setOtherName(pedido.parametros_extra?.software_solicitado || '');
    setDates(pedido.vigencia ? { ...pedido.vigencia } : vigenciaInicial()); setError(''); setBusy(false); setValidDates(false);
    key.current = crypto.randomUUID(); submitting.current = false;
    getTemplates().then(({ data }) => { if (active) setTemplates(data); })
      .catch((err) => { if (active) setError(err); });
    return () => { active = false; };
  }, [open, pedido, canReply]);
  if (!open || !pedido || !canReply) return null;
  const isOther = templateId === 'otro';
  const complete = templateId && validDates && description.trim() && title.trim() && (!isOther || otherName.trim());
  const available = templates.filter((t) => renewal ? t.id === pedido.template_id
    : t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === model);
  const edit = (setter, value) => { setter(value); key.current = crypto.randomUUID(); };
  const changeModel = (value) => {
    const chosen = templates.find((t) => t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === value);
    setModel(value); setTemplateId(chosen ? String(chosen.id) : value !== 'iaas' ? 'otro' : ''); setOtherName('');
    key.current = crypto.randomUUID();
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !complete) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const { data } = await reenviarPedido(pedido.id, { template_id: isOther ? null : Number(templateId), modelo_servicio: model,
        ...(templates.find(t => String(t.id) === templateId)?.origen_biblioteca ? {oferta_revision: templates.find(t => String(t.id) === templateId).revision} : {}),
        descripcion_requerimientos: description.trim(), vigencia: dates,
        parametros_extra: { titulo: title.trim(), software_solicitado: isOther ? otherName.trim() : null } }, key.current);
      onReenviado?.(data); onClose();
    } catch (err) {
      setError(err);
      if (err?.response?.status === 409) {
        try {
          const { data } = await getTemplates(); setTemplates(data);
          if (!data.some(t => String(t.id) === templateId && t.activo !== false && t.oferta_disponible !== false) && !isOther && !renewal) setTemplateId('');
          if (data.find(t => String(t.id) === templateId)?.revision !== templates.find(t => String(t.id) === templateId)?.revision) key.current = crypto.randomUUID();
        } catch { /* El error original conserva el formulario. */ }
      }
    }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog wide title={`${admin ? 'Corregir y reenviar' : 'Responder aclaración del'} pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="request-form">
      <ErrorFormulario error={error} />
      <p className="callout">Aclaración solicitada: {pedido.observaciones_ajuste || 'Sin observaciones adicionales'}</p>
      <div className="request-field"><label htmlFor="resend-model">Tipo de servicio</label>
      <select id="resend-model" className="input" value={model} onChange={(e) => changeModel(e.target.value)} disabled={busy || renewal}>
        <option value="iaas">IaaS</option><option value="paas">PaaS</option><option value="saas">SaaS</option>
      </select></div>
      <div className="request-field"><label htmlFor="resend-template">{model === 'iaas' ? 'Plantilla' : 'Servicio'}</label>
      <select id="resend-template" className="input" value={templateId} onChange={(e) => { edit(setTemplateId, e.target.value); setOtherName(''); }} required disabled={busy || renewal}>
        <option value="">Seleccioná una plantilla compatible</option>
        {available.map((t) => <option key={t.id} value={String(t.id)}>{t.nombre}{t.version_ofrecida ? ` · versión ${t.version_ofrecida}` : ''}</option>)}
        {!renewal && model !== 'iaas' && <option value="otro">Otro</option>}
        {renewal && !available.length && <option value={String(pedido.template_id)}>{pedido.asignacion_snapshot?.nombre || 'Asignación histórica'}</option>}
      </select></div>
      {isOther && <div className="request-field"><label htmlFor="resend-other">¿Qué software o servicio necesitás?</label>
        <input id="resend-other" className="input" value={otherName} maxLength={200} onChange={(e) => edit(setOtherName, e.target.value)} disabled={busy} required />
      </div>}
      <div className="request-field"><label htmlFor="resend-title">Nombre de la solicitud</label>
        <input id="resend-title" className="input" value={title} maxLength={200} onChange={(e) => edit(setTitle, e.target.value)} disabled={busy} required />
      </div>
      <div className="request-field"><label htmlFor="resend-description">Justificación pedagógica y aclaraciones</label>
      <textarea id="resend-description" className="input" rows={4} value={description} maxLength={5000} onChange={(e) => edit(setDescription, e.target.value)} disabled={busy} required /></div>
      {!pedido.vigencia && <p>Revisá una vigencia explícita: la solicitud anterior no conserva este dato completo.</p>}
      <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => edit(setDates, value)} onValid={setValidDates} /></fieldset>
      <div className="request-form__actions"><button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cerrar</button>
        <button className="btn btn-primary" type="submit" disabled={busy || !complete}>{busy ? 'Enviando…' : 'Reenviar para revisión'}</button></div>
    </form>
  </Dialog>;
}
