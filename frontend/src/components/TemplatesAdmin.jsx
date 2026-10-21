import { useEffect, useRef, useState } from 'react';
import { createTemplate, getDefiniciones, updateTemplate } from '../services/api';
import { Dialog } from './ui';
import { mensajeError } from '../utils/errors';

const initial = { nombre: '', descripcion: '', modelo_servicio: 'iaas', definicion_version_id: '',
  default_vcpus: 1, default_ram_mb: 512, default_disk_gb: 4, justificacion_disco: '' };

export default function TemplatesAdmin({ open, template, onClose, onGuardado }) {
  const [form, setForm] = useState(initial);
  const [definitions, setDefinitions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setForm(template ? Object.fromEntries(Object.keys(initial).map((key) => [key, template[key] ?? initial[key]])) : initial);
    setError(''); setBusy(false); submitting.current = false; setLoading(true);
    getDefiniciones(true).then(({ data }) => { if (active) setDefinitions(data.filter((row) => row.estado === 'publicada')); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar las definiciones.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, template]);
  if (!open) return null;
  if (template?.tipo === 'qemu') return <Dialog title="Perfil histórico QEMU" onClose={onClose}>
    <p>{template.nombre}. Los perfiles QEMU conservan lectura histórica; esta entrega crea LXC.</p>
  </Dialog>;
  const available = definitions.filter((row) => row.modelo_servicio === form.modelo_servicio);
  const selected = available.find((row) => row.id === form.definicion_version_id);
  const choose = (id) => {
    const minimum = available.find((row) => row.id === id)?.minimum_resources || {};
    setForm({ ...form, definicion_version_id: id,
      default_vcpus: Math.max(Number(form.default_vcpus), minimum.vcpus || 1),
      default_ram_mb: Math.max(Number(form.default_ram_mb), minimum.ram_mb || 1),
      default_disk_gb: Math.max(Number(form.default_disk_gb), minimum.disk_gb || 1) });
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !selected) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const payload = { ...form, nombre: form.nombre.trim(), descripcion: form.descripcion.trim() || null,
        justificacion_disco: form.justificacion_disco.trim() || null, os_template: null,
        default_vcpus: Number(form.default_vcpus), default_ram_mb: Number(form.default_ram_mb), default_disk_gb: Number(form.default_disk_gb) };
      const result = template ? await updateTemplate(template.id, payload) : await createTemplate({ ...payload, tipo: 'lxc' });
      onGuardado?.(result.data); onClose();
    } catch (err) { setError(mensajeError(err, 'No se pudo guardar el perfil. Conservamos los datos.')); }
    finally { submitting.current = false; setBusy(false); }
  };
  const minimum = selected?.minimum_resources || {};
  return <Dialog title={template ? `Corregir perfil: ${template.nombre}` : 'Nuevo perfil de recursos'} onClose={onClose} closeDisabled={busy}>
    <form className="col gap-3" onSubmit={submit}>
      {error && <p className="callout bad" role="alert">{error}</p>}
      {loading && <p role="status">Cargando definiciones…</p>}
      <p>Contenedor LXC. La imagen y preparación proceden de la definición publicada.</p>
      <div className="field"><label htmlFor="profile-name">Nombre del perfil</label><input id="profile-name" className="input" required maxLength={100} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></div>
      <div className="field"><label htmlFor="profile-model">Modelo de servicio</label><select id="profile-model" className="input" value={form.modelo_servicio} onChange={(e) => setForm({ ...form, modelo_servicio: e.target.value, definicion_version_id: '' })}>
        <option value="iaas">IaaS · Linux</option><option value="paas">PaaS · PostgreSQL</option><option value="saas">SaaS · BookStack de referencia</option>
      </select></div>
      <div className="field"><label htmlFor="profile-definition">Definición publicada</label><select id="profile-definition" className="input" required disabled={loading || busy} value={form.definicion_version_id} onChange={(e) => choose(e.target.value)}>
        <option value="">Seleccioná una versión publicada</option>
        {available.map((row) => <option key={row.id} value={row.id}>{row.codigo} {row.version}</option>)}
      </select></div>
      {!loading && !available.length && <p>No hay definiciones publicadas para este modelo. Publicá una versión desde Definiciones.</p>}
      <div className="field"><label htmlFor="profile-description">Descripción</label><textarea id="profile-description" className="input" maxLength={2000} value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} /></div>
      <div className="grid cols-3">
        {[['default_vcpus', 'vCPUs', minimum.vcpus], ['default_ram_mb', 'RAM (MB)', minimum.ram_mb], ['default_disk_gb', 'Disco (GB)', minimum.disk_gb]].map(([key, label, min]) => <div className="field" key={key}>
          <label htmlFor={`profile-${key}`}>{label}</label><input id={`profile-${key}`} className="input" type="number" required step={1} min={min || 1} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
        </div>)}
      </div>
      <p>Los cambios se ofrecen a nuevas solicitudes. Las asignaciones ya aprobadas se conservan.</p>
      <div className="row gap-2"><button type="button" className="btn btn-secondary" disabled={busy} onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" disabled={busy || loading || !selected}>{busy ? 'Guardando…' : template ? 'Guardar cambios' : 'Crear perfil'}</button></div>
    </form>
  </Dialog>;
}
