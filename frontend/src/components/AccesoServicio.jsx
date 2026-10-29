import { useEffect, useRef, useState } from 'react';
import { getAccesoServicio, getConsolaServicio, revelarAccesoServicio, abrirAplicacionServicio } from '../services/api';
import { mensajeError } from '../utils/errors';

function secureLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password &&
      ![...url.searchParams.keys()].some((key) => /password|ticket|token|secret/i.test(key)) ? url.href : null;
  } catch { return null; }
}

export default function AccesoServicio({ servicio, user }) {
  const [metadata, setMetadata] = useState(null);
  const [revealed, setRevealed] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [consoleURL, setConsoleURL] = useState(null);
  const submitting = useRef(false);
  const admin = user?.rol === 'admin';
  useEffect(() => {
    let active = true;
    setMetadata(null); setRevealed(null); setError(''); setNotice(''); setConsoleURL(null);
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
  const downloadCA = () => {
    const url = URL.createObjectURL(new Blob([revealed.credenciales.ca_pem], { type: 'application/x-pem-file' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'nap-ca.crt'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const instructions = metadata?.acceso_con_nap ? metadata.instrucciones
    : metadata?.estado_entrega === 'solo_validacion' ? 'El servicio se inició. Podés abrirlo y consultar sus datos de acceso.'
    : metadata?.estado_entrega === 'pendiente_verificacion' ? 'El servicio se inició. El acceso todavía no está habilitado.'
    : metadata?.instrucciones;
  const method = metadata?.metodo || revealed?.metodo;
  const link = method === 'https' ? secureLink(metadata?.direccion) : null;
  const openWithNap = () => act(async () => {
    const { data } = await abrirAplicacionServicio(servicio.id);
    const url = secureLink(data.destino);
    if (!url || new URL(url).pathname !== '/_nap/entrar' || new URL(url).search || !data.codigo) throw new Error('Destino no confirmado');
    // El código viaja por POST y no queda en URLs, historial, almacenamiento ni logs de acceso.
    const form = document.createElement('form');
    form.method = 'POST'; form.action = url; form.target = '_blank'; form.rel = 'noopener'; form.hidden = true;
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = 'codigo'; input.value = data.codigo;
    form.append(input); document.body.append(form);
    try { form.submit(); } finally { form.remove(); }
  });
  if (metadata?.acceso_con_nap) return <section aria-label="Acceso al servicio" className="col gap-3">
    {error && <p role="alert" className="callout bad">{error}</p>}
    <p>{instructions}</p>
    <button type="button" className="btn btn-primary" disabled={busy || !metadata.puede_abrir_con_nap} onClick={openWithNap}>{busy ? 'Abriendo…' : 'Abrir aplicación'}</button>
    <p className="card-meta">El acceso está vinculado a tu sesión y a tu cátedra. Guardá los diagramas en tu equipo para conservarlos.</p>
  </section>;
  return <section aria-label="Acceso al servicio" className="col gap-3">
    {error && <p role="alert" className="callout bad">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!metadata && !error && <p role="status">Consultando acceso…</p>}
    {metadata && <>
      <p>{instructions}</p>
      {metadata.direccion && <p>Dirección: <code style={{ overflowWrap: 'anywhere' }}>{metadata.direccion}</code></p>}
      {metadata.verificado_at && <p>Verificado el {new Date(metadata.verificado_at).toLocaleString('es-AR')}.</p>}
      {method === 'https' && link && (metadata.estado_entrega === 'entregado' || admin && metadata.estado_entrega === 'solo_validacion') && <a className="btn btn-secondary" href={link} target="_blank" rel="noopener noreferrer">
        Abrir aplicación</a>}
      {method === 'consola' && <div className="row wrap gap-2"><button className="btn btn-secondary" disabled={busy} onClick={queryConsole}>Consultar consola</button>
        {consoleURL && <a href={consoleURL} target="_blank" rel="noopener noreferrer">Abrir consola de esta instancia</a>}</div>}
      {metadata.puede_revelar_credenciales && !revealed && <button className="btn btn-primary" disabled={busy} onClick={reveal}>Revelar acceso inicial</button>}
    </>}
    {revealed && <section className="card" aria-label="Credenciales iniciales reveladas">
      <h3>Acceso inicial</h3>
      <p>Si cambiaste la contraseña dentro del servicio, usá la nueva. Este acceso inicial no se actualiza automáticamente.</p>
      <dl>{['usuario', 'password', ...(['postgresql', 'mariadb'].includes(method) ? ['host', 'puerto', 'base', 'sslmode', 'tls'] : [])]
        .filter((key) => Object.hasOwn(revealed.credenciales, key)).map((key) => <div key={key}>
        <dt>{{ usuario: 'Usuario', password: 'Contraseña inicial', host: 'Host', puerto: 'Puerto', base: 'Base', sslmode: 'Modo TLS', tls: 'Seguridad' }[key] || key}</dt>
        <dd><code style={{ overflowWrap: 'anywhere' }}>{String(revealed.credenciales[key])}</code></dd>
      </div>)}</dl>
      {method === 'mariadb' && revealed.credenciales.ca_pem && <p><button className="btn btn-secondary" onClick={downloadCA}>Descargar certificado CA</button> Configurá este certificado en el cliente y activá la verificación de identidad del servidor.</p>}
      <div className="row wrap gap-2"><button className="btn btn-secondary" onClick={() => setRevealed(null)}>Ocultar acceso inicial</button>
        <button className="btn btn-secondary" disabled={busy} onClick={copyPassword}>Copiar contraseña</button></div>
    </section>}
    {metadata?.producto === 'bookstack' && <p>El docente administra esta instancia BookStack. Creá cuentas individuales de lectura dentro de la aplicación y revisá sus permisos. El libro virtual definitivo está pendiente de relevamiento.</p>}
    {metadata?.producto === 'drawio' && <p>Guardá los diagramas en tu equipo para conservarlos y poder editarlos después.</p>}
  </section>;
}
