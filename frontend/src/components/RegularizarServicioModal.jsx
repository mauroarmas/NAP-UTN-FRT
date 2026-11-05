import { useEffect, useRef, useState } from 'react';
import { evaluarRegularizacion, confirmarRegularizacion, archivarDuplicadoLegacy } from '../services/api';
import useRemoteData from '../hooks/useRemoteData';
import EstadoConsulta from './EstadoConsulta';
import ErrorFormulario from './ErrorFormulario';
import { Dialog } from './ui';

export default function RegularizarServicioModal({ servicio, user, onClose, onConfirmed }) {
  const [canonical, setCanonical] = useState('');
  const [conflicts, setConflicts] = useState([]);
  const [form, setForm] = useState({ nombre: '', modelo_servicio: '', desde: '', hasta: '', referencia: '', motivo: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submitting = useRef(false);
  const initialized = useRef(false);
  const key = useRef(crypto.randomUUID());
  const remote = useRemoteData((options) => evaluarRegularizacion(servicio.id,
    canonical ? { canonico_id: Number(canonical) } : {}, options), {
    enabled: user?.rol === 'admin' && Boolean(servicio), key: `regularizacion:${servicio?.id}:${canonical}`,
    errorMessage: 'No se pudo comprobar el registro. Volvé a evaluar antes de confirmar.',
  });
  const preview = remote.data;
  useEffect(() => { if (preview) setConflicts(preview.conflictos || []); }, [preview]);
  useEffect(() => {
    if (!preview || initialized.current) return;
    initialized.current = true;
    setForm((current) => ({ ...current, nombre: preview.nombre || '', modelo_servicio: preview.modelo_servicio || '',
      desde: preview.desde || '', hasta: preview.hasta || '' }));
  }, [preview]);
  if (!servicio || user?.rol !== 'admin') return null;
  const edit = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    key.current = crypto.randomUUID();
  };
  const archiving = Boolean(canonical);
  const allowed = !busy && !remote.loading && !remote.error && (archiving
    ? preview?.puede_archivar_duplicado : preview?.puede_regularizar && preview?.asignacion_observada);
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !allowed) return;
    submitting.current = true; setBusy(true); setError(null);
    const reference = { fuente_sha256: preview.fuente_sha256, referencia: form.referencia.trim(), motivo: form.motivo.trim() };
    try {
      const { data } = await (archiving
        ? archivarDuplicadoLegacy(servicio.id, { ...reference, canonico_id: Number(canonical) }, key.current)
        : confirmarRegularizacion(servicio.id, { ...reference, nombre: form.nombre.trim(), modelo_servicio: form.modelo_servicio,
          asignacion: preview.asignacion_observada, desde: form.desde, hasta: form.hasta }, key.current));
      onConfirmed?.(data); onClose();
    } catch (failure) { setError(failure); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title="Regularizar registro histórico" onClose={onClose} closeDisabled={busy}>
    <form className="col gap-3" onSubmit={submit} aria-busy={busy}>
      <p>Servicio #{servicio.id}. La comprobación consulta su propiedad y configuración actual. Una fecha desconocida debe quedar pendiente hasta contar con respaldo.</p>
      <p>La regularización conserva el acceso como no verificado. Si está encendido fuera del período autorizado, se solicitará una pausa que deberá confirmar el sistema.</p>
      <EstadoConsulta remote={remote} nombre="regularización" mostrarCarga />
      <ErrorFormulario error={error} />
      {error && <button className="btn btn-secondary" type="button" disabled={busy || remote.loading} onClick={remote.reload}>Volver a evaluar</button>}
      <fieldset disabled={busy || remote.loading} className="col gap-3">
        {preview?.motivos?.length > 0 && <div className="callout warn">
          <p>Revisiones necesarias:</p><ul>{preview.motivos.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </div>}
        {conflicts.length > 0 && <label>Registro principal comprobado
          <select className="input" value={canonical} onChange={(event) => { setCanonical(event.target.value); key.current = crypto.randomUUID(); setError(null); }}>
            <option value="">Elegir el principal para revisar el duplicado</option>
            {conflicts.map((record) => <option key={record.id} value={record.id}>#{record.id} · {record.nombre}{!record.misma_catedra ? ' · otra cátedra' : ''}</option>)}
          </select>
        </label>}
        {archiving ? <p>Se archivará únicamente este registro duplicado. El recurso y el registro principal se conservan. La propiedad y los compromisos deben permitirlo.</p> : <>
          {preview?.asignacion_observada && <p>Configuración comprobada: {preview.asignacion_observada.vcpus} vCPU · {preview.asignacion_observada.ram_mb} MB RAM · {preview.asignacion_observada.disk_gb} GB de disco. Estado: {preview.estado_observado === 'running' ? 'encendido' : 'detenido'}.</p>}
          <label>Nombre histórico del servicio<input className="input" required maxLength={150} value={form.nombre} onChange={(event) => edit('nombre', event.target.value)} /></label>
          <label>Tipo de servicio<select className="input" required value={form.modelo_servicio} onChange={(event) => edit('modelo_servicio', event.target.value)}>
            <option value="">Elegir tipo comprobado</option><option value="iaas">IaaS</option><option value="paas">PaaS</option><option value="saas">SaaS</option>
          </select></label>
          <p>Fechas inclusive, en {preview?.zona_horaria || 'la zona institucional'}. Conservá los períodos ya aprobados; sus modificaciones requieren el flujo de vigencias.</p>
          <label>Fecha inicial respaldada<input className="input" type="date" required value={form.desde} onChange={(event) => edit('desde', event.target.value)} /></label>
          <label>Fecha final respaldada<input className="input" type="date" required min={form.desde || undefined} value={form.hasta} onChange={(event) => edit('hasta', event.target.value)} /></label>
        </>}
        <label>Referencia del respaldo<input className="input" required maxLength={200} value={form.referencia} onChange={(event) => edit('referencia', event.target.value)} /></label>
        <label>Motivo de la decisión<textarea className="input" required maxLength={500} value={form.motivo} onChange={(event) => edit('motivo', event.target.value)} /></label>
      </fieldset>
      <div className="row gap-2">
        <button className="btn btn-secondary" type="button" onClick={onClose} disabled={busy}>Cerrar</button>
        <button className="btn btn-primary" type="submit" disabled={!allowed}>{busy ? 'Guardando…' : archiving ? 'Archivar registro duplicado' : 'Confirmar regularización'}</button>
      </div>
    </form>
  </Dialog>;
}
