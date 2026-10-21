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
  const [dates, setDates] = useState(vigenciaInicial);
  const [validDates, setValidDates] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  const admin = user?.rol === 'admin';
  const renewal = pedido?.tipo === 'renovacion';
  useEffect(() => {
    if (!open || !pedido || !admin) return;
    let active = true;
    setModel(pedido.modelo_servicio); setTemplateId(String(pedido.template_id || '')); setDescription(pedido.descripcion_requerimientos || '');
    setDates(pedido.vigencia ? { ...pedido.vigencia } : vigenciaInicial()); setError(''); setBusy(false); setValidDates(false);
    key.current = crypto.randomUUID(); submitting.current = false;
    getTemplates().then(({ data }) => { if (active) setTemplates(data); })
      .catch((err) => { if (active) setError(err); });
    return () => { active = false; };
  }, [open, pedido, admin]);
  if (!open || !pedido || !admin) return null;
  const available = templates.filter((t) => renewal ? t.id === pedido.template_id
    : t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === model);
  const edit = (setter, value) => { setter(value); key.current = crypto.randomUUID(); };
  const changeModel = (value) => {
    setModel(value); setTemplateId(String(templates.find((t) => t.activo !== false && t.oferta_disponible !== false && t.tipo === 'lxc' && t.modelo_servicio === value)?.id || ''));
    key.current = crypto.randomUUID();
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !templateId || !validDates) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const { data } = await reenviarPedido(pedido.id, { template_id: Number(templateId), modelo_servicio: model,
        descripcion_requerimientos: description.trim(), vigencia: dates }, key.current);
      onReenviado?.(data); onClose();
    } catch (err) { setError(err); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title={`Corregir y reenviar pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="col gap-3">
      <ErrorFormulario error={error} />
      <p>Observaciones registradas: {pedido.observaciones_ajuste || 'Sin observaciones adicionales'}</p>
      <label htmlFor="resend-model">Modelo</label>
      <select id="resend-model" value={model} onChange={(e) => changeModel(e.target.value)} disabled={busy || renewal}>
        <option value="iaas">IaaS</option><option value="paas">PaaS</option><option value="saas">SaaS</option>
      </select>
      <label htmlFor="resend-template">Plantilla</label>
      <select id="resend-template" value={templateId} onChange={(e) => edit(setTemplateId, e.target.value)} required disabled={busy || renewal}>
        <option value="">Seleccioná una plantilla compatible</option>
        {available.map((t) => <option key={t.id} value={String(t.id)}>{t.nombre}</option>)}
        {renewal && !available.length && <option value={String(pedido.template_id)}>{pedido.asignacion_snapshot?.nombre || 'Asignación histórica'}</option>}
      </select>
      <label htmlFor="resend-description">Requerimientos o propósito</label>
      <textarea id="resend-description" value={description} maxLength={5000} onChange={(e) => edit(setDescription, e.target.value)} disabled={busy} />
      {!pedido.vigencia && <p>Revisá una vigencia explícita: la solicitud anterior no conserva este dato completo.</p>}
      <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => edit(setDates, value)} onValid={setValidDates} /></fieldset>
      <div className="row gap-2"><button type="button" onClick={onClose} disabled={busy}>Cerrar</button>
        <button className="btn btn-primary" type="submit" disabled={busy || !templateId || !validDates}>{busy ? 'Guardando…' : 'Reenviar corrección'}</button></div>
    </form>
  </Dialog>;
}
