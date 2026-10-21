import { useState } from 'react';
import { preparar2FA, confirmar2FA, prepararReemplazo2FA, confirmarReemplazo2FA, cancelarSetup2FA, regenerarCodigos2FA, desactivar2FA, verificarIngresoTotp, recuperar2FA, recuperar2FAAsistido } from '../services/api';
import { mensajeError } from '../utils/errors';

export function CodigosRecuperacion({ codes, onClose }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const copiar = async () => {
    try { await navigator.clipboard.writeText(codes.join('\n')); setCopied(true); }
    catch { setError('Seleccioná y guardá los códigos manualmente.'); }
  };
  return <section className="login__card">
    <h1>Guardar códigos de recuperación</h1>
    <p>Se muestran una sola vez. Guardalos fuera del portal, en un lugar privado. Cada código permite una recuperación.</p>
    <label htmlFor="codigos-recuperacion">Códigos de recuperación</label>
    <textarea id="codigos-recuperacion" className="input" rows={10} readOnly value={codes.join('\n')} />
    <button className="btn btn-secondary" onClick={copiar}>{copied ? 'Copiados' : 'Copiar códigos'}</button>
    <button className="btn btn-primary" onClick={onClose}>Ya guardé los códigos</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}

export function DesafioIngreso({ session, onRefresh }) {
  const [mode, setMode] = useState('totp');
  const [password, setPassword] = useState('');
  const [proof, setProof] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let response;
      if (mode === 'totp') response = await verificarIngresoTotp(session.desafio?.id, proof);
      else if (mode === 'codigo') response = await recuperar2FA({ password, codigo_recuperacion: proof });
      else if (mode === 'asistida') response = await recuperar2FAAsistido({ password, autorizacion_recuperacion: proof });
      else response = await desactivar2FA({ password, codigo_recuperacion: proof });
      setPassword(''); setProof('');
      await onRefresh(response.data);
    } catch (err) { setError(mensajeError(err, 'No se pudo verificar el acceso.')); }
    finally { setBusy(false); }
  };
  return <section className="login__card">
    <h1>Completar acceso</h1>
    <p>Tu cuenta tiene segundo factor activo. Completá la verificación antes de entrar al portal.</p>
    <form onSubmit={submit}>
      <div className="field"><label htmlFor="modo-verificacion">Forma de verificación</label><select id="modo-verificacion" className="input" value={mode} onChange={(e) => { setMode(e.target.value); setProof(''); }} disabled={busy}>
        <option value="totp">Aplicación autenticadora</option><option value="codigo">Recuperar con un código guardado</option><option value="asistida">Autorización institucional asistida</option><option value="desactivar">Desactivar 2FA deliberadamente con un código</option>
      </select></div>
      {mode !== 'totp' && <div className="field"><label htmlFor="verificacion-password">Contraseña actual</label><input id="verificacion-password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>}
      <div className="field"><label htmlFor="prueba-verificacion">{mode === 'totp' ? 'Código de la aplicación' : mode === 'asistida' ? 'Autorización asistida' : 'Código de recuperación'}</label><input id="prueba-verificacion" className="input" value={proof} onChange={(e) => setProof(e.target.value)} autoComplete="one-time-code" inputMode={mode === 'totp' ? 'numeric' : 'text'} required /></div>
      {mode === 'desactivar' && <p>Esta acción elimina el segundo factor y cierra todas tus sesiones. Deberás ingresar de nuevo.</p>}
      {error && <p role="alert">{error}</p>}
      <button className="btn btn-primary" disabled={busy || (mode === 'totp' && !session.desafio)}>{busy ? 'Verificando…' : mode === 'desactivar' ? 'Desactivar segundo factor y salir' : 'Continuar'}</button>
    </form>
  </section>;
}

export default function Seguridad({ user, recovery = false, onRefresh }) {
  const [mode, setMode] = useState(user?.totp_habilitado ? 'reemplazar' : 'activar');
  const [password, setPassword] = useState('');
  const [proof, setProof] = useState('');
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let response;
      if (pending) {
        const data = { desafio_id: pending.desafio_id, codigo_totp: proof };
        response = pending.replacement ? await confirmarReemplazo2FA(data) : await confirmar2FA(data);
        setPending(null); setPassword(''); setProof('');
        await onRefresh(response.data);
      } else if (recovery || mode === 'activar' || mode === 'reemplazar') {
        const replacement = !recovery && mode === 'reemplazar';
        response = replacement ? await prepararReemplazo2FA({ password, codigo_totp: proof }) : await preparar2FA(recovery ? {} : { password });
        setPending({ ...response.data, replacement }); setProof(''); setPassword('');
      } else {
        response = mode === 'regenerar' ? await regenerarCodigos2FA({ password, codigo_totp: proof }) : await desactivar2FA({ password, codigo_totp: proof });
        setPassword(''); setProof(''); await onRefresh(response.data);
      }
    } catch (err) { setError(mensajeError(err, 'No se pudo guardar la configuración.')); }
    finally { setBusy(false); }
  };
  const cancelar = async () => {
    setBusy(true); setError('');
    try { await cancelarSetup2FA(pending.desafio_id); setPending(null); setProof(''); }
    catch (err) { setError(mensajeError(err, 'No se pudo cancelar la configuración.')); }
    finally { setBusy(false); }
  };
  return <section className={recovery ? 'login__card' : 'card'}>
    <h1>{recovery ? 'Recuperar segundo factor' : 'Seguridad de la cuenta'}</h1>
    <p>{recovery ? 'Configurá y verificá un factor nuevo para recuperar el acceso. El factor anterior se conserva hasta confirmar el reemplazo.' : `El segundo factor es opcional. Estado actual: ${user?.totp_habilitado ? 'activado' : 'desactivado'}.`}</p>
    <form onSubmit={submit}>
      {pending ? <>
        <p>Agregá esta clave a tu aplicación autenticadora y confirmá el código generado. La configuración vence en cinco minutos.</p>
        <div className="field"><label htmlFor="clave-autenticador">Clave del autenticador</label><input id="clave-autenticador" className="input" readOnly value={pending.secret} /></div>
        <details><summary>Configuración manual de la aplicación</summary><p style={{ overflowWrap: 'anywhere' }}><code>{pending.provisioning_uri}</code></p></details>
      </> : <>
        {!recovery && user?.totp_habilitado && <div className="field"><label htmlFor="accion-seguridad">Acción de seguridad</label><select id="accion-seguridad" className="input" value={mode} onChange={(e) => setMode(e.target.value)} disabled={busy}><option value="reemplazar">Reemplazar aplicación autenticadora</option><option value="regenerar">Regenerar códigos de recuperación</option><option value="desactivar">Desactivar segundo factor y salir</option></select></div>}
        {!recovery && <div className="field"><label htmlFor="seguridad-password">Contraseña actual</label><input id="seguridad-password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>}
      </>}
      {(pending || (!recovery && user?.totp_habilitado)) && <div className="field"><label htmlFor="seguridad-totp">Código de la aplicación {pending ? 'nueva' : 'actual'}</label><input id="seguridad-totp" className="input" value={proof} onChange={(e) => setProof(e.target.value)} inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" /></div>}
      {error && <p role="alert">{error}</p>}
      <button className="btn btn-primary" disabled={busy}>{busy ? 'Procesando…' : pending ? 'Confirmar nuevo factor' : recovery ? 'Configurar factor nuevo' : mode === 'activar' ? 'Activar segundo factor opcional' : mode === 'desactivar' ? 'Desactivar segundo factor y salir' : mode === 'regenerar' ? 'Generar códigos nuevos' : 'Preparar reemplazo'}</button>
      {pending && <button type="button" className="btn btn-secondary" disabled={busy} onClick={cancelar}>Cancelar configuración</button>}
    </form>
  </section>;
}
