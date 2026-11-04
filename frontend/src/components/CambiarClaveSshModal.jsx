import { useEffect, useRef, useState } from 'react';
import { registrarAccesoSsh } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import { Dialog } from './ui';

export default function CambiarClaveSshModal({ servicio, tieneClave, onClose, onDone }) {
  const [clave, setClave] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  useEffect(() => { setClave(''); setError(''); setBusy(false); key.current = crypto.randomUUID(); submitting.current = false; }, [servicio]);
  if (!servicio) return null;
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !clave.trim()) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const { data } = await registrarAccesoSsh(servicio.id, clave.trim(), key.current);
      onDone?.(data); onClose();
    } catch (err) { setError(err); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title={tieneClave ? 'Cambiar clave SSH' : 'Agregar clave SSH'} onClose={onClose} closeDisabled={busy}>
    <form className="col gap-3" onSubmit={submit}>
      <p>{tieneClave ? 'La clave anterior deja de servir cuando termina el cambio.' : 'Con esta clave vas a entrar a tu servicio.'} El servicio tiene que estar en marcha.</p>
      <ErrorFormulario error={error} />
      <div className="request-field">
        <label htmlFor="ssh-key-nueva">Clave pública SSH</label>
        <p id="ssh-key-nueva-help" className="request-hint">Pegá el contenido de tu archivo <code>.pub</code>. Nunca pegues la clave privada.</p>
        <textarea id="ssh-key-nueva" className="input" rows={3} maxLength={800} spellCheck={false} autoComplete="off"
          aria-describedby="ssh-key-nueva-help" value={clave} disabled={busy} onChange={(e) => { setClave(e.target.value); key.current = crypto.randomUUID(); }}
          placeholder="ssh-ed25519 AAAA… tu-usuario@tu-equipo" required />
      </div>
      <div className="row wrap gap-2">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancelar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || !clave.trim()}>{busy ? 'Enviando…' : tieneClave ? 'Cambiar clave' : 'Agregar clave'}</button>
      </div>
    </form>
  </Dialog>;
}
