import { useEffect, useRef, useState } from 'react';
import { getAccesoServicio, getConsolaServicio, revelarAccesoServicio, abrirAplicacionServicio, actualizarAccesoConsola } from '../services/api';
import { mensajeError } from '../utils/errors';
import CambiarClaveSshModal from './CambiarClaveSshModal';

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
  const [consoleLogin, setConsoleLogin] = useState(null);
  const [sshModal, setSshModal] = useState(false);
  const submitting = useRef(false);
  const admin = user?.rol === 'admin';
  useEffect(() => {
    let active = true;
    setMetadata(null); setRevealed(null); setError(''); setNotice(''); setConsoleURL(null); setConsoleLogin(null);
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
    setConsoleLogin(secureLink(data.login_url));
  });
  const copyPassword = () => act(async () => {
    try { await navigator.clipboard.writeText(revealed.credenciales.password); }
    catch { setError('No se pudo copiar la contraseña. Podés seleccionarla y copiarla manualmente.'); return; }
    setNotice('Contraseña copiada por tu solicitud.');
  });
  const refresh = () => act(async () => {
    const { data } = await getAccesoServicio(servicio.id);
    setMetadata(data);
  });
  const copyCommand = () => act(async () => {
    try { await navigator.clipboard.writeText(metadata.acceso_ssh.comando); }
    catch { setError('No se pudo copiar el comando. Podés seleccionarlo y copiarlo manualmente.'); return; }
    setNotice('Comando copiado.');
  });
  const updateConsole = () => act(async () => {
    await actualizarAccesoConsola(servicio.id);
    setNotice('Estamos actualizando el acceso de consola. Cuando termine, la persona debe volver a revelar el acceso inicial: ahora se entra como nap.');
    await refresh();
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
      {metadata.acceso_ssh && <section className="card col gap-2" aria-label="Acceso por SSH">
        <h3>Conexión por SSH</h3>
        {metadata.acceso_ssh.puede_conectar ? <>
          <p>Entrá desde tu computadora, dentro de la red institucional, con la clave que registraste. No usa contraseña.</p>
          <p><code style={{ overflowWrap: 'anywhere' }}>{metadata.acceso_ssh.comando}</code></p>
          <p className="card-meta">Clave registrada: <code style={{ overflowWrap: 'anywhere' }}>{metadata.acceso_ssh.huella}</code></p>
          <div className="row wrap gap-2"><button className="btn btn-secondary" disabled={busy} onClick={copyCommand}>Copiar comando</button></div>
        </> : <p role="status">{metadata.acceso_ssh.motivo}</p>}
        <div className="row wrap gap-2">
          {metadata.acceso_ssh.estado === 'pendiente' && <button className="btn btn-secondary" disabled={busy} onClick={refresh}>Actualizar estado</button>}
          {metadata.acceso_ssh.estado !== 'pendiente' && <button className="btn btn-secondary" disabled={busy} onClick={() => setSshModal(true)}>
            {metadata.acceso_ssh.estado === 'sin_clave' ? 'Agregar clave' : 'Cambiar clave'}</button>}
        </div>
      </section>}
      {admin && metadata.consola_usuario === 'root' && <div className="row wrap gap-2">
        <button className="btn btn-secondary" disabled={busy} onClick={updateConsole}>Actualizar acceso de consola</button>
        <span className="muted">La consola pasará a usar el usuario nap con una contraseña nueva; la de root dejará de servir.</span></div>}
      {method === 'consola' && <div className="row wrap gap-2"><button className="btn btn-secondary" disabled={busy} onClick={queryConsole}>Consultar consola</button>
        {consoleURL && <ol className="stack gap-1" aria-label="Pasos para abrir la consola">
          {consoleLogin && <li>Primero iniciá sesión con tu cuenta personal de consola (dominio «Proxmox VE»):{' '}
            <a href={consoleLogin} target="_blank" rel="noopener noreferrer">Iniciar sesión</a>. Solo hace falta si no lo hiciste hace poco.</li>}
          <li><a href={consoleURL} target="_blank" rel="noopener noreferrer">Abrir consola de esta instancia</a></li>
          {metadata.consola_usuario === 'nap'
            ? <li>Dentro de la consola entrá como <strong>nap</strong> con la contraseña de «Revelar acceso inicial». Para tareas de administración usá <code>sudo</code>.</li>
            : <li>Dentro de la consola entrá como <strong>root</strong> con la contraseña de «Revelar acceso inicial». El usuario <strong>nap</strong> sólo entra por SSH con clave.</li>}</ol>}</div>}
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
    {sshModal && <CambiarClaveSshModal servicio={servicio} tieneClave={metadata?.acceso_ssh?.estado !== 'sin_clave'}
      onClose={() => setSshModal(false)} onDone={() => { setNotice('Estamos aplicando la clave. Puede tardar unos segundos.'); refresh(); }} />}
    {metadata?.producto === 'bookstack' && <p>El docente administra esta instancia BookStack. Creá cuentas individuales de lectura dentro de la aplicación y revisá sus permisos. El libro virtual definitivo está pendiente de relevamiento.</p>}
    {metadata?.producto === 'drawio' && <p>Guardá los diagramas en tu equipo para conservarlos y poder editarlos después.</p>}
  </section>;
}
