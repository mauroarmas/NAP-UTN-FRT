import { useEffect, useRef, useState } from 'react';
import { createTemplate, getDefiniciones, updateTemplate } from '../services/api';
import { Dialog } from './ui';
import SelectorTamano from './SelectorTamano';
import { tamanosCompatibles } from '../utils/tamanos';
import useTamanos from '../hooks/useTamanos';
import { mensajeError } from '../utils/errors';

const initial = { nombre: '', descripcion: '', definicion_version_id: '', tamano: '' };

export default function TemplatesAdmin({ open, template, onClose, onGuardado, embedded = false, onBuscar, onBusyChange }) {
  const [form, setForm] = useState(initial);
  const [definitions, setDefinitions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);
  const { sizes, loading: loadingSizes, error: sizesError, retry } = useTamanos(open);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setForm(template ? { nombre: template.nombre, descripcion: template.descripcion || '',
      definicion_version_id: template.definicion_version_id || '', tamano: template.tamano_recomendado || '' } : initial);
    setError(''); setBusy(false); submitting.current = false; setLoading(true);
    getDefiniciones(true).then(({ data }) => { if (active) setDefinitions(data.filter((row) => row.estado === 'publicada')); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar las aplicaciones preparadas.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, template]);
  if (!open) return null;
  if (template?.tipo === 'qemu') return <Dialog title="Servicio histórico" onClose={onClose}>
    <p>{template.nombre} conserva su historial. El catálogo actual utiliza contenedores LXC.</p>
  </Dialog>;
  const selected = definitions.find((row) => row.id === form.definicion_version_id);
  const rawIaas = template?.config_extra?.origen === 'proxmox_iaas' && !template.definicion_version_id;
  const allowed = rawIaas ? sizes : tamanosCompatibles(sizes, selected?.minimum_resources);
  const chosen = allowed.find((size) => size.id === form.tamano) || allowed[0];
  const choose = (id) => {
    const definition = definitions.find((row) => row.id === id);
    setForm({ ...form, definicion_version_id: id, tamano: '',
      nombre: form.nombre || ({ linux: 'Linux', postgresql: 'PostgreSQL', bookstack: 'BookStack', drawio: 'Draw.io' }[definition?.producto] || '') });
  };
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || (!selected && !rawIaas) || !chosen) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const payload = { nombre: form.nombre.trim(), descripcion: form.descripcion.trim() || null,
        ...(rawIaas ? {} : { modelo_servicio: selected.modelo_servicio, definicion_version_id: selected.id, os_template: null, config_extra: null }), tamano: chosen.id,
        default_vcpus: chosen.vcpus, default_ram_mb: chosen.ram_mb, default_disk_gb: chosen.disk_gb };
      const result = template ? await updateTemplate(template.id, payload) : await createTemplate({ ...payload, tipo: 'lxc' });
      onGuardado?.(result.data); onClose();
    } catch (err) { setError(mensajeError(err, 'No se pudo guardar el servicio. Conservamos los datos.')); }
    finally { submitting.current = false; setBusy(false); }
  };
  const content = <form className="col gap-4" onSubmit={submit}>
      {(error || sizesError) && <div className="callout bad" role="alert">{error || sizesError}
        {sizesError && <button type="button" className="btn btn-secondary" onClick={retry}>Reintentar carga de tamaños</button>}</div>}
      {(loading || loadingSizes) && <p role="status">Cargando opciones…</p>}
      {!embedded && <p>{template ? 'Actualizá cómo se ofrece este servicio y su tamaño recomendado.' : 'Elegí la aplicación que querés ofrecer. Si todavía no está preparada, podés buscarla y continuar desde aquí.'}</p>}
      {!rawIaas && <div className="field"><label htmlFor="profile-definition">Servicio</label><select id="profile-definition" className="input" required disabled={loading || busy} value={form.definicion_version_id} onChange={(e) => choose(e.target.value)}>
        <option value="">Seleccioná una aplicación publicada</option>
        {definitions.map((row) => <option key={row.id} value={row.id}>{{linux:'Linux',postgresql:'PostgreSQL',bookstack:'BookStack',drawio:'Draw.io'}[row.producto] || row.codigo}</option>)}
      </select></div>}
      {onBuscar && <button type="button" className="btn btn-secondary service-add-search" disabled={busy} onClick={onBuscar}>Buscar en la biblioteca</button>}
      {!rawIaas && !loading && !definitions.length && <p className="callout">Buscá una aplicación en la biblioteca para comenzar.</p>}
      {(!embedded || selected) && <>
      <div className="field"><label htmlFor="profile-name">Nombre del servicio</label><input id="profile-name" className="input" required maxLength={100} disabled={busy} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></div>
      <div className="field"><label htmlFor="profile-description">Descripción para la cátedra</label><textarea id="profile-description" className="input" rows={3} maxLength={2000} disabled={busy} placeholder="¿Para qué sirve y qué se puede hacer con este servicio?" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} /></div>
      <SelectorTamano sizes={sizes} value={chosen?.id || ''} onChange={(tamano) => setForm({ ...form, tamano })}
        allowed={allowed.map((size) => size.id)} disabled={busy || (!selected && !rawIaas)} legend="Tamaño recomendado" />
      {selected && !loadingSizes && !allowed.length && <p role="alert" className="callout warn">Esta aplicación necesita más recursos que los tamaños disponibles. No se puede ofrecer hasta contar con una preparación compatible.</p>}
      <p className="card-meta">Los cambios se aplican a pedidos nuevos. Las asignaciones ya aprobadas conservan sus recursos.</p>
      </>}
      <div className="dialog-form-actions"><button type="button" className="btn btn-secondary" disabled={busy} onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" disabled={busy || loading || loadingSizes || Boolean(sizesError) || (!selected && !rawIaas) || !chosen}>{busy ? 'Guardando…' : template ? 'Guardar cambios' : 'Agregar servicio'}</button></div>
    </form>;
  return embedded ? content : <Dialog title={template ? `Editar servicio: ${template.nombre}` : 'Agregar servicio al catálogo'} onClose={onClose} closeDisabled={busy}>{content}</Dialog>;
}
