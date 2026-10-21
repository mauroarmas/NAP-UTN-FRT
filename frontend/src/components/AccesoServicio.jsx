import { useEffect, useId, useRef, useState } from 'react';
import { getAccesoServicio, getConsolaServicio, revelarAccesoServicio, verificarAccesoServicio } from '../services/api';
import RegistroEvidencia from './RegistroEvidencia';
import { mensajeError } from '../utils/errors';

function secureLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password &&
      ![...url.searchParams.keys()].some((key) => /password|ticket|token|secret/i.test(key)) ? url.href : null;
  } catch { return null; }
}

export default function AccesoServicio({ servicio, user, onVerified }) {
  const id = useId();
  const [metadata, setMetadata] = useState(null);
  const [revealed, setRevealed] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [reference, setReference] = useState('');
  const [observed, setObserved] = useState('');
  const [consoleURL, setConsoleURL] = useState(null);
  const submitting = useRef(false);
  const keys = useRef({});
  const admin = user?.rol === 'admin';
  useEffect(() => {
    let active = true;
    setMetadata(null); setRevealed(null); setError(''); setNotice(''); setConsoleURL(null);
    setReference(''); setObserved('');
    getAccesoServicio(servicio.id).then(({ data }) => { if (active) setMetadata(data); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudo consultar el acceso.')); });
    return () => { active = false; };
  }, [servicio.id]);
  const act = async (callback) => {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError(''); setNotice('');
    try { await callback(); }
    catch (err) { setError(mensajeError(err, 'No se confirmó la acción. Podés volver a consultar.')); }
    finally { submitting.current = false; setBusy(false); }
  };
  const reveal = () => act(async () => {
    const { data } = await revelarAccesoServicio(servicio.id);
    setRevealed(data);
  });
  const verify = (event) => {
    event.preventDefault();
    act(async () => {
      const body = { evidencia_ref: reference.trim(), endpoint: metadata.direccion, observado_at: observed.trim() };
      const fingerprint = JSON.stringify([servicio.id, body]);
      const key = keys.current[fingerprint] ||= crypto.randomUUID();
      await verificarAccesoServicio(servicio.id, body, key);
      setRevealed(null);
      const { data } = await getAccesoServicio(servicio.id);
      setMetadata(data); setNotice('Acceso verificado. La entrega quedó registrada.');
      onVerified?.();
    });
  };
  const queryConsole = () => act(async () => {
    const { data } = await getConsolaServicio(servicio.id);
    const url = secureLink(data.url);
    if (!url) throw new Error('Destino no confirmado');
    setConsoleURL(url);
  });
  const copyPassword = () => act(async () => {
    try { await navigator.clipboard.writeText(revealed.credenciales.password); }
    catch { setError('No se pudo copiar la contraseña. Podés seleccionarla y copiarla manualmente.'); return; }
    setNotice('Contraseña copiada por tu solicitud.');
  });
  const method = metadata?.metodo || revealed?.metodo;
  const link = method === 'https' ? secureLink(metadata?.direccion) : null;
  return <section aria-label="Acceso al servicio" className="col gap-3">
    {error && <p role="alert" className="callout bad">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!metadata && !error && <p role="status">Consultando acceso…</p>}
    {metadata && <>
      {metadata.estado_entrega === 'solo_validacion' && <p className="callout warn"><strong>Solo para validación</strong>. Falta comprobar acceso desde la red prevista.</p>}
      <p>{metadata.instrucciones}</p>
      {metadata.direccion && <p>Dirección observada: <code style={{ overflowWrap: 'anywhere' }}>{metadata.direccion}</code></p>}
      {metadata.verificado_at && <p>Verificado el {new Date(metadata.verificado_at).toLocaleString('es-AR')}.</p>}
      {method === 'https' && link && (metadata.estado_entrega === 'entregado' || admin && metadata.estado_entrega === 'solo_validacion') && <a className="btn btn-secondary" href={link} target="_blank" rel="noopener noreferrer">
        {metadata.estado_entrega === 'solo_validacion' ? 'Abrir aplicación para validar' : 'Abrir aplicación'}</a>}
      {method === 'consola' && <div className="row wrap gap-2"><button className="btn btn-secondary" disabled={busy} onClick={queryConsole}>Consultar consola autorizada</button>
        {consoleURL && <a href={consoleURL} target="_blank" rel="noopener noreferrer">Abrir consola de esta instancia</a>}</div>}
      {metadata.puede_revelar_credenciales && !revealed && <button className="btn btn-primary" disabled={busy} onClick={reveal}>Revelar acceso inicial</button>}
    </>}
    {revealed && <section className="card" aria-label="Credenciales iniciales reveladas">
      <h3>Acceso inicial</h3>
      <p>Si cambiaste la contraseña dentro del servicio, usá la nueva. Este acceso inicial no se actualiza automáticamente.</p>
      <dl>{['usuario', 'password', ...(method === 'postgresql' ? ['host', 'puerto', 'base', 'sslmode'] : [])]
        .filter((key) => Object.hasOwn(revealed.credenciales, key)).map((key) => <div key={key}>
        <dt>{{ usuario: 'Usuario', password: 'Contraseña inicial', host: 'Host', puerto: 'Puerto', base: 'Base', sslmode: 'Modo TLS' }[key] || key}</dt>
        <dd><code style={{ overflowWrap: 'anywhere' }}>{String(revealed.credenciales[key])}</code></dd>
      </div>)}</dl>
      <div className="row wrap gap-2"><button className="btn btn-secondary" onClick={() => setRevealed(null)}>Ocultar acceso inicial</button>
        <button className="btn btn-secondary" disabled={busy} onClick={copyPassword}>Copiar contraseña</button></div>
    </section>}
    {method === 'https' && <p>El docente administra esta instancia BookStack. Creá cuentas individuales de lectura dentro de la aplicación y revisá sus permisos. El libro virtual definitivo está pendiente de relevamiento.</p>}
    {admin && metadata?.estado_entrega === 'solo_validacion' && <>
      {metadata.verificacion_instancia && <details><summary>Identidad para la evidencia de esta instancia</summary>
        <pre style={{ overflowX: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(metadata.verificacion_instancia, null, 2)}</pre>
      </details>}
      <RegistroEvidencia disabled={busy} onDraftChange={() => { setReference(''); setObserved(''); }} onDocumentRegistered={(record, document) => {
        setReference(record.evidencia_ref); setObserved(document?.observado_at || '');
        setNotice('Evidencia registrada. Revisá la referencia y confirmá la verificación por separado.');
      }} />
      <form className="col gap-3" onSubmit={verify}>
        <h3>Confirmar prueba de acceso</h3>
        <div className="field"><label htmlFor={id + '-ref'}>Referencia UUID de evidencia registrada</label><input id={id + '-ref'} className="input" required disabled={busy} value={reference} onChange={(e) => setReference(e.target.value)} /></div>
        <div className="field"><label htmlFor={id + '-observed'}>Fecha UTC de la prueba, con Z</label><input id={id + '-observed'} className="input" required disabled={busy} value={observed} onChange={(e) => setObserved(e.target.value)} /></div>
        <p>El documento debe acreditar la función del producto y el acceso desde la red prevista, con el endpoint observado de esta instancia.</p>
        <button className="btn btn-primary" disabled={busy || !reference.trim() || !observed.trim() || !metadata.direccion}>Confirmar verificación de acceso</button>
      </form>
    </>}
  </section>;
}
