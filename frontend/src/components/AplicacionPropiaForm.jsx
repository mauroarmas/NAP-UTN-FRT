import { useEffect, useId, useRef, useState } from 'react';
import { Box, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { agregarAplicacionPropia } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function AplicacionPropiaForm({ onAdded, onBusyChange, initialValues }) {
  const id = useId();
  const [form, setForm] = useState({
    nombre: initialValues?.nombre || '',
    imagen: initialValues?.imagen || '',
    puerto: initialValues?.puerto ? String(initialValues.puerto) : '',
    descripcion: initialValues?.descripcion || '',
    modelo_servicio: initialValues?.modelo_servicio || 'saas',
    persistencia: initialValues?.persistencia ? (Array.isArray(initialValues.persistencia) ? initialValues.persistencia.join('\n') : initialValues.persistencia) : '',
    ruta_salud: initialValues?.ruta_salud || '/',
    websocket: initialValues?.websocket || false,
  });
  const [variables, setVariables] = useState([]);
  const [secrets, setSecrets] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const decision = useRef(null);
  const pending = useRef(false);
  const errorRef = useRef(null);
  useEffect(() => () => onBusyChange?.(false), [onBusyChange]);
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const changeRow = (setter, index, key, value) => setter((rows) => rows.map((row, n) => n === index ? { ...row, [key]: value } : row));
  const submit = async (event) => {
    event.preventDefault();
    if (pending.current) return;
    const names = [...variables.map((row) => row.name.trim()), ...secrets.map((row) => row.name.trim())];
    if (new Set(names).size !== names.length) { setError('Los nombres de variables y datos privados no pueden repetirse.'); return; }
    const payload = { origen: 'imagen_docker', nombre: form.nombre.trim(), imagen: form.imagen.trim(), puerto: Number(form.puerto),
      descripcion: form.descripcion.trim() || null, modelo_servicio: form.modelo_servicio,
      variables: Object.fromEntries(variables.map((row) => [row.name.trim(), row.value])),
      secretos: secrets.map((row) => ({ nombre: row.name.trim(), etiqueta: row.label.trim(), modo: row.mode })),
      persistencia: form.persistencia.split('\n').map((p) => p.trim()).filter(Boolean), ruta_salud: form.ruta_salud.trim() || '/', websocket: form.websocket };
    const fingerprint = JSON.stringify(payload);
    if (decision.current?.fingerprint !== fingerprint) decision.current = { fingerprint, key: crypto.randomUUID() };
    pending.current = true; setBusy(true); onBusyChange?.(true); setError('');
    try { const { data } = await agregarAplicacionPropia(payload, decision.current.key); onAdded?.(data); }
    catch (err) { setError(mensajeError(err, 'No se pudo agregar la aplicación. Tus datos se conservan.')); queueMicrotask(() => errorRef.current?.focus()); }
    finally { pending.current = false; setBusy(false); onBusyChange?.(false); }
  };
  return <form className="own-application-form" onSubmit={submit} aria-busy={busy}>
    <div className="own-application-intro"><Box size={24}/><div><h3>{initialValues ? 'Configurar aplicación' : 'Aplicación propia'}</h3><p>{initialValues ? 'Configurá la aplicación seleccionada de Docker Hub.' : 'Usá una imagen Docker de tu cátedra o de un registro compatible.'}</p></div></div>
    {error && <div className="callout bad" role="alert" tabIndex={-1} ref={errorRef}>{error}</div>}
    <fieldset disabled={busy}>
      <div className="field"><label htmlFor={`${id}-name`}>Nombre del servicio</label><input className="input" id={`${id}-name`} required maxLength={100} value={form.nombre} onChange={(e) => update('nombre', e.target.value)} placeholder="Ej. Campus de prácticas"/></div>
      <div className="own-application-main-fields">
        <div className="field"><label htmlFor={`${id}-image`}>Imagen Docker</label><input className="input" id={`${id}-image`} required maxLength={512} value={form.imagen} onChange={(e) => update('imagen', e.target.value)} placeholder="universidad/mi-aplicacion:curso" autoCapitalize="none" spellCheck={false}/></div>
        <div className="field"><label htmlFor={`${id}-port`}>Puerto de la aplicación</label><input className="input" id={`${id}-port`} type="number" min={1} max={65535} required value={form.puerto} onChange={(e) => update('puerto', e.target.value)} placeholder="8080"/></div>
      </div>
      <details className="own-application-options"><summary>Opciones de la aplicación</summary><div className="own-application-option-fields">
        <div className="field"><label htmlFor={`${id}-description`}>Descripción</label><textarea className="input" id={`${id}-description`} maxLength={2000} rows={2} value={form.descripcion} onChange={(e) => update('descripcion', e.target.value)}/></div>
        <div className="own-application-main-fields">
          <div className="field"><label htmlFor={`${id}-model`}>Tipo de servicio</label><select className="input" id={`${id}-model`} value={form.modelo_servicio} onChange={(e) => update('modelo_servicio', e.target.value)}><option value="saas">SaaS — Aplicación</option><option value="paas">PaaS — Plataforma</option></select></div>
          <div className="field"><label htmlFor={`${id}-health`}>Ruta de comprobación</label><input className="input" id={`${id}-health`} maxLength={512} value={form.ruta_salud} onChange={(e) => update('ruta_salud', e.target.value)} placeholder="/"/></div>
        </div>
        <div className="field"><label htmlFor={`${id}-storage`}>Carpetas que conservan datos</label><textarea className="input" id={`${id}-storage`} rows={2} value={form.persistencia} onChange={(e) => update('persistencia', e.target.value)} placeholder="/data" aria-describedby={`${id}-storage-help`}/><p id={`${id}-storage-help`} className="card-meta">Una carpeta por línea, según las indicaciones de la aplicación.</p></div>
        <label className="own-application-checkbox"><input type="checkbox" checked={form.websocket} onChange={(e) => update('websocket', e.target.checked)}/>Permitir conexiones en tiempo real (WebSocket)</label>
        <section className="own-application-data" aria-label="Variables públicas"><h4>Variables públicas</h4><p className="card-meta">Sólo si la imagen las necesita. Las contraseñas van en Datos privados.</p>
          {variables.map((row, index) => <div className="own-application-row" key={row.id}>
            <input className="input" required aria-label={`Nombre de variable ${index + 1}`} value={row.name} onChange={(e) => changeRow(setVariables, index, 'name', e.target.value)} placeholder="Nombre" maxLength={64} pattern="[A-Za-z_][A-Za-z0-9_]*"/>
            <input className="input" aria-label={`Valor público ${index + 1}`} value={row.value} onChange={(e) => changeRow(setVariables, index, 'value', e.target.value)} placeholder="Valor público" maxLength={4096}/>
            <button type="button" className="btn btn-ghost" aria-label={`Quitar variable ${index + 1}`} onClick={() => setVariables((rows) => rows.filter((v) => v.id !== row.id))}><Trash2 size={16}/></button>
          </div>)}
          <button type="button" className="btn btn-secondary" disabled={variables.length + secrets.length >= 20} onClick={() => setVariables((rows) => [...rows, { id: crypto.randomUUID(), name: '', value: '' }])}><Plus size={15}/>Agregar variable</button>
        </section>
        <section className="own-application-data" aria-label="Datos privados"><h4>Datos privados por pedido</h4><p className="card-meta">Se generan o se completan al aprobar cada pedido. No ingreses su valor aquí.</p>
          {secrets.map((row, index) => <div className="own-application-row own-application-secret-row" key={row.id}>
            <input className="input" required aria-label={`Variable privada ${index + 1}`} value={row.name} onChange={(e) => changeRow(setSecrets, index, 'name', e.target.value)} placeholder="Nombre de variable" maxLength={64} pattern="[A-Za-z_][A-Za-z0-9_]*"/>
            <input className="input" required aria-label={`Etiqueta del dato privado ${index + 1}`} value={row.label} onChange={(e) => changeRow(setSecrets, index, 'label', e.target.value)} placeholder="Ej. Contraseña inicial" maxLength={100}/>
            <select className="input" aria-label={`Origen del dato privado ${index + 1}`} value={row.mode} onChange={(e) => changeRow(setSecrets, index, 'mode', e.target.value)}><option value="generado">Generar automáticamente</option><option value="por_pedido">Completar al aprobar</option></select>
            <button type="button" className="btn btn-ghost" aria-label={`Quitar dato privado ${index + 1}`} onClick={() => setSecrets((rows) => rows.filter((v) => v.id !== row.id))}><Trash2 size={16}/></button>
          </div>)}
          <button type="button" className="btn btn-secondary" disabled={variables.length + secrets.length >= 20} onClick={() => setSecrets((rows) => [...rows, { id: crypto.randomUUID(), name: '', label: '', mode: 'generado' }])}><Plus size={15}/>Agregar dato privado</button>
        </section>
      </div></details>
    </fieldset>
    <div className="own-application-submit"><p className="card-meta">Se agrega al catálogo. Se instalará al desplegar un pedido aprobado.</p><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={16}/>Verificando imagen…</> : <><Plus size={16}/>Agregar al catálogo</>}</button></div>
    {busy && <p role="status" className="callout">Verificando la imagen y su compatibilidad. Puede tardar unos segundos.</p>}
  </form>;
}
