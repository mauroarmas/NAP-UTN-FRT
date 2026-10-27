import { useEffect, useRef, useState } from 'react';
import { getTemplates, getCatedras, getCatedrasMias, createPedido } from '../services/api';
import { mensajeError } from '../utils/errors';
import { Dialog } from './ui';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';
import { Server, Layers, BookOpen, Info, Send } from 'lucide-react';

const MODELOS = [
  ['iaas', 'IaaS (Infraestructura)', 'Infraestructura', 'Un entorno de trabajo', Server],
  ['paas', 'PaaS (Plataforma)', 'Plataforma', 'Herramientas para prácticas', Layers],
  ['saas', 'SaaS (Software)', 'Software', 'Aplicaciones para enseñar', BookOpen],
];
const compatible = (template, model) => template.activo !== false && template.oferta_disponible !== false && template.tipo === 'lxc' && (template.modelo_servicio || 'iaas') === model;

export default function NuevoPedidoModal({ open, onClose, onCreated, user, initialTemplate = null }) {
  const [model, setModel] = useState('iaas');
  const [templates, setTemplates] = useState([]);
  const [categories, setCategories] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [description, setDescription] = useState('');
  const [title, setTitle] = useState('');
  const [otherName, setOtherName] = useState('');
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
    setModel(initialModel); setTemplateId(''); setCategoryId(''); setDescription(''); setTitle(''); setOtherName(''); setDates(vigenciaInicial());
    setValidDates(false); setError(''); setFields({}); setBusy(false); submitting.current = false;
    key.current = crypto.randomUUID(); setLoading(true);
    Promise.all([getTemplates(), admin ? getCatedras() : getCatedrasMias()]).then(([tpl, cats]) => {
      if (!active) return;
      setTemplates(tpl.data); setCategories(cats.data);
      const chosen = initialTemplate ? tpl.data.find((t) => t.id === initialTemplate.id && compatible(t, initialModel)) : tpl.data.find((t) => compatible(t, initialModel));
      setTemplateId(chosen ? String(chosen.id) : !initialTemplate && initialModel !== 'iaas' ? 'otro' : '');
      if (initialTemplate && !chosen) setError('El perfil elegido dejó de estar disponible. Revisá la oferta actual.');
      if (cats.data.length === 1) setCategoryId(String(cats.data[0].id));
    }).catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar las opciones.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, admin, initialTemplate]);
  if (!open) return null;
  const available = templates.filter((t) => compatible(t, model));
  const isOther = templateId === 'otro';
  const complete = Boolean(validDates && templateId && categoryId && title.trim() && description.trim() && (!isOther || otherName.trim()));
  const edit = (setter, value) => { setter(value); key.current = crypto.randomUUID(); setFields({}); };
  const changeModel = (value) => {
    const first = templates.find((t) => compatible(t, value));
    setModel(value); setTemplateId(first ? String(first.id) : value !== 'iaas' ? 'otro' : ''); setOtherName('');
    key.current = crypto.randomUUID(); setError(''); setFields({});
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !complete) return;
    submitting.current = true; setBusy(true); setError(''); setFields({});
    const payload = { modelo_servicio: model, template_id: isOther ? null : Number(templateId), catedra_id: Number(categoryId),
      descripcion_requerimientos: description.trim(), vigencia: dates,
      parametros_extra: { titulo: title.trim(), software_solicitado: isOther ? otherName.trim() : null } };
    const chosen = templates.find(t => String(t.id) === templateId);
    if (chosen?.origen_biblioteca) payload.oferta_revision = chosen.revision;
    try {
      const response = await createPedido(payload, key.current);
      onCreated?.(response.data); onClose();
    } catch (err) {
      setError(mensajeError(err, 'No se pudo confirmar la solicitud. Conservamos los datos.'));
      setFields(err.response?.data?.detail?.campos || {});
      if (err.response?.status === 409) {
        try { const {data} = await getTemplates(); setTemplates(data);
          if (!data.some(t => String(t.id) === templateId && t.oferta_disponible !== false && t.activo !== false)) setTemplateId('');
          if (data.find(t => String(t.id) === templateId)?.revision !== templates.find(t => String(t.id) === templateId)?.revision) key.current = crypto.randomUUID();
        } catch { /* El mensaje original y los campos quedan disponibles. */ }
      }
    } finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog wide title="Nueva solicitud de servicio" onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="request-form">
      <p className="request-form__intro">Contanos qué necesitás para tu cátedra. Administración revisará el pedido y te acompañará en su preparación.</p>
      {error && <p role="alert" className="callout bad">{error}</p>}
      {Object.entries(fields).map(([field, message]) => <p role="alert" key={field}>{field}: {message}</p>)}
      {loading && <p role="status">Cargando opciones…</p>}
      <section className="request-section">
        <h3 className="request-section__title"><span>1</span> ¿Qué necesitás?</h3>
        <div className="request-context">
          <div className="request-field">
            <label htmlFor="request-category">Cátedra</label>
            <select id="request-category" className="input" value={categoryId} onChange={(e) => edit(setCategoryId, e.target.value)} disabled={loading || busy} required>
              <option value="">Seleccioná una cátedra</option>
              {categories.map((c) => <option key={c.id} value={String(c.id)}>{c.nombre}</option>)}
            </select>
          </div>
          {user?.nombre && <p className="request-responsible">Responsable<strong>{user.nombre}</strong></p>}
        </div>
        <fieldset disabled={loading || busy}>
          <legend className="request-label">Tipo de servicio</legend>
          <div className="request-models">
            {MODELOS.map(([value, label, name, hint, Icon]) => <button key={value} type="button"
              className="request-model" aria-label={label} aria-pressed={model === value} onClick={() => changeModel(value)}>
              <Icon size={20} aria-hidden="true" /><strong>{name}</strong><span>{hint}</span>
            </button>)}
          </div>
        </fieldset>
        <div className="request-field">
          <label htmlFor="request-template">{model === 'iaas' ? 'Plantilla' : 'Servicio'}</label>
          <select id="request-template" className="input" value={templateId} onChange={(e) => { edit(setTemplateId, e.target.value); setOtherName(''); }} disabled={loading || busy} required>
            <option value="">Seleccioná {model === 'iaas' ? 'una plantilla' : 'un servicio'}</option>
            {available.map((t) => <option key={t.id} value={String(t.id)}>{t.nombre}{t.version_ofrecida ? ` · versión ${t.version_ofrecida}` : ''}</option>)}
            {model !== 'iaas' && <option value="otro">Otro</option>}
          </select>
          {available.length === 0 && !loading && <p className="request-hint">{model === 'iaas' ? 'No hay plantillas disponibles. Consultá a administración.' : 'Podés elegir «Otro» y contarnos qué servicio necesitás.'}</p>}
        </div>
        {isOther && <div className="request-other">
          <div className="request-field">
            <label htmlFor="request-other">¿Qué software o servicio necesitás?</label>
            <input id="request-other" className="input" maxLength={200} value={otherName} disabled={busy}
              onChange={(e) => edit(setOtherName, e.target.value)} placeholder="Nombre del servicio y su función principal" required />
          </div>
          <p className="request-hint"><Info size={15} aria-hidden="true" /> Administración evaluará tu propuesta, preparará el servicio y lo incorporará al catálogo antes de aprobar su asignación.</p>
        </div>}
      </section>
      <section className="request-section">
        <h3 className="request-section__title"><span>2</span> Uso en la cátedra</h3>
        <div className="request-field">
          <label htmlFor="request-title">Nombre de la solicitud</label>
          <input id="request-title" className="input" maxLength={200} value={title} onChange={(e) => edit(setTitle, e.target.value)}
            placeholder="Ej.: Libro virtual para Bases de Datos" disabled={busy} required />
        </div>
        <div className="request-field">
          <label htmlFor="request-description">Justificación pedagógica</label>
          <p id="request-description-help" className="request-hint">Describí las actividades, qué necesitan hacer los estudiantes y cómo ayudará este servicio. Incluí la cantidad estimada de participantes y los requisitos que consideres importantes.</p>
          <textarea id="request-description" className="input" rows={4} maxLength={5000} aria-describedby="request-description-help"
            value={description} onChange={(e) => edit(setDescription, e.target.value)} disabled={busy} required />
        </div>
      </section>
      <section className="request-section">
        <h3 className="request-section__title"><span>3</span> ¿Por cuánto tiempo?</h3>
        <fieldset disabled={busy}><VigenciaFields value={dates} onChange={(value) => edit(setDates, value)} onValid={setValidDates} /></fieldset>
      </section>
      <div className="request-form__actions">
        <span>Todos los campos son obligatorios.</span>
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cerrar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || loading || !complete}><Send size={15} aria-hidden="true" />{busy ? 'Enviando…' : 'Enviar solicitud'}</button>
      </div>
    </form>
  </Dialog>;
}
