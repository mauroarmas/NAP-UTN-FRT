import { mensajeError } from '../utils/errors.js';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../services/api';
import useTheme from '../hooks/useTheme';
import utnLogo from '../assets/utn-logo.jpeg';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toggle: toggleTheme } = useTheme();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { data } = await login(username, password);
      setPassword('');
      await onLogin(data);
      navigate('/');
    } catch (err) {
      setError(mensajeError(err, 'Error al iniciar sesión'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login fade-in">
      <div className="login__top">
        <span>Tema</span>
        <button className="theme-switch" onClick={toggleTheme} aria-label="Cambiar tema" title="Cambiar tema">
          <span className="knob" />
        </button>
      </div>

      <div className="login__center">
        <form className="login__card" onSubmit={handleSubmit}>
          <img className="login__crest" src={utnLogo} alt="Escudo UTN" />
          <div className="login__kicker">Universidad Tecnológica Nacional <br/> Facultad Regional Tucumán</div>
          <h2>NAP - Nube Académica Personal</h2>
          <p className="login__sub">Gestión de servicios por cátedra</p>

          {error && <div role="alert" className="login__error">{error}</div>}

          <div className="field">
            <label htmlFor="login-user">Usuario o Correo</label>
            <input
              id="login-user"
              className="input"
              type="text"
              placeholder="usuario o correo"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="login-pass">Contraseña</label>
            <input
              id="login-pass"
              className="input"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? 'Ingresando…' : 'Ingresar'}
          </button>

          <hr className="hr" />
          <p className="login__foot">
            ¿Problemas para acceder? Contactá a Mesa de Ayuda TIC — FRT.
          </p>
        </form>
      </div>
    </div>
  );
}
