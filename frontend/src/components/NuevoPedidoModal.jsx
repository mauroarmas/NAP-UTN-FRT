import { useEffect, useRef, useState } from 'react';
import { getTemplates, getCatedras, getCatedrasMias, createPedido } from '../services/api';
import { mensajeError } from '../utils/errors';
import { Dialog } from './ui';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';

const MODELOS = [['iaas', 'IaaS (Infraestructura)'], ['paas', 'PaaS (Plataforma)'], ['saas', 'SaaS (Software)']];
const compatible = (template, model) => template.activo !== false && template.oferta_disponible !== false && template.tipo === 'lxc' && (template.modelo_servicio || 'iaas') === model;

export default function NuevoPedidoModal({ open, onClose, onCreated, user, initialTemplate = null }) {
  const [model, setModel] = useState('iaas');
  const [templates, setTemplates] = useState([]);
  const [categories, setCategories] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [description, setDescription] = useState('');
  const [dates, setDates] = useState(vigenciaInicial);
  const [validDates, setValidDates] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [fields, setFields] = useState({});
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  const admin = user?.rol === 'admin';
  useEffect(() => {
    if (!open) return;
    let active = true;
    const initialModel = initialTemplate?.modelo_servicio || 'iaas';
    setModel(initialModel); setTemplateId(''); setCategoryId(''); setDescription(''); setDates(vigenciaInicial());
    setValidDates(false); setError(''); setFields({}); setBusy(false); submitting.current = false;
    key.current = crypto.randomUUID(); setLoading(true);
    Promise.all([getTemplates(), admin ? getCatedras() : getCatedrasMias()]).then(([tpl, cats]) => {
      if (!active) return;
      setTemplates(tpl.data); setCategories(cats.data);
      const chosen = initialTemplate ? tpl.data.find((t) => t.id === initialTemplate.id && compatible(t, initialModel)) : tpl.data.find((t) => compatible(t, initialModel));
      setTemplateId(String(chosen?.id || ''));
      if (initialTemplate && !chosen) setError('El perfil elegido dejó de estar disponible. Revisá la oferta actual.');
      if (cats.data.length === 1) setCategoryId(String(cats.data[0].id));
    }).catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar las opciones.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, admin, initialTemplate]);
  if (!open) return null;
  const available = templates.filter((t) => compatible(t, model));
  const edit = (setter, value) => { setter(value); key.current = crypto.randomUUID(); setFields({}); };
  const changeModel = (value) => {
    setModel(value); setTemplateId(String(templates.find((t) => compatible(t, value))?.id || ''));
    key.current = crypto.randomUUID(); setError(''); setFields({});
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !validDates || !templateId || !categoryId) return;
    submitting.current = true; setBusy(true); setError(''); setFields({});
    const payload = { modelo_servicio: model, template_id: Number(templateId), catedra_id: Number(categoryId),
      descripcion_requerimientos: description.trim() || null, vigencia: dates };
    try {
      const response = await createPedido(payload, key.current);
      onCreated?.(response.data); onClose();
    } catch (err) {
      setError(mensajeError(err, 'No se pudo confirmar la solicitud. Conservamos los datos.'));
      setFields(err.response?.data?.detail?.campos || {});
    } finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title="Nueva solicitud de servicio" onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="col gap-3">
      {error && <p role="alert" className="callout bad">{error}</p>}
      {Object.entries(fields).map(([field, message]) => <p role="alert" key={field}>{field}: {message}</p>)}
      {loading && <p role="status">Cargando opciones…</p>}
      <fieldset disabled={loading || busy}>
        <legend>Modelo de servicio</legend>
        {MODELOS.map(([value, label]) => <button key={value} type="button" className="btn btn-secondary" aria-pressed={model === value} onClick={() => changeModel(value)}>{label}</button>)}
      </fieldset>
      <label htmlFor="request-template">Plantilla</label>
      <select id="request-template" className="input" value={templateId} onChange={(e) => edit(setTemplateId, e.target.value)} disabled={loading || busy} required>
        <option value="">Seleccioná una plantilla</option>
        {available.map((t) => <option key={t.id} value={String(t.id)}>{t.nombre}</option>)}
      </select>
      {available.length === 0 && !loading && <p>No hay una oferta compatible disponible. Consultá a administración.</p>}
      <label htmlFor="request-category">Cátedra</label>
      <select id="request-category" className="input" value={categoryId} onChange={(e) => edit(setCategoryId, e.target.value)} disabled={loading || busy} required>
        <option value="">Seleccioná una cátedra</option>
        {categories.map((c) => <option key={c.id} value={String(c.id)}>{c.nombre}</option>)}
      </select>
      <label htmlFor="request-description">Requerimientos o propósito</label>
      <textarea id="request-description" className="input" maxLength={5000} value={description} onChange={(e) => edit(setDescription, e.target.value)} disabled={busy} />
      <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => edit(setDates, value)} onValid={setValidDates} /></fieldset>
      <div className="row gap-2">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cerrar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || loading || !validDates || !templateId || !categoryId}>{busy ? 'Enviando…' : 'Enviar solicitud'}</button>
      </div>
    </form>
  </Dialog>;
}
