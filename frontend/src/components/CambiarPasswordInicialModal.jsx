import { useState } from 'react';
import { cambiarPasswordInicial } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function CambiarPasswordInicialModal({ user, onPasswordCambiada }) {
  const [password, setPassword] = useState('');
  const [confirmar, setConfirmar] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const guardar = async (event) => {
    event.preventDefault(); setError('');
    if (password.length < 8 || new TextEncoder().encode(password).length > 72) {
      setError('Usá al menos 8 caracteres y hasta 72 bytes UTF-8.'); return;
    }
    if (password !== confirmar) { setError('Las contraseñas ingresadas no coinciden.'); return; }
    setLoading(true);
    try {
      const { data } = await cambiarPasswordInicial(password);
      setPassword(''); setConfirmar('');
      await onPasswordCambiada(data);
    } catch (err) { setError(mensajeError(err, 'No se pudo cambiar la contraseña.')); }
    finally { setLoading(false); }
  };
  return <section className="login__card">
    <h1>Cambiar contraseña inicial</h1>
    <p>Hola {user?.nombre || user?.username}. Definí tu contraseña personal para habilitar el acceso.</p>
    <form onSubmit={guardar}>
      <div className="field"><label htmlFor="nueva-password">Nueva contraseña</label><input id="nueva-password" className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoFocus /></div>
      <div className="field"><label htmlFor="confirmar-password">Confirmar nueva contraseña</label><input id="confirmar-password" className="input" type="password" autoComplete="new-password" value={confirmar} onChange={(e) => setConfirmar(e.target.value)} required /></div>
      {error && <p role="alert">{error}</p>}
      <button className="btn btn-primary" disabled={loading}>{loading ? 'Guardando…' : 'Guardar y continuar'}</button>
    </form>
  </section>;
}
