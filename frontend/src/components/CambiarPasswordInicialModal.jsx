import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Lock, ShieldCheck } from 'lucide-react';
import { cambiarPasswordInicial } from '../services/api';

export default function CambiarPasswordInicialModal({ user, onPasswordCambiada }) {
  const [password, setPassword] = useState('');
  const [confirmar, setConfirmar] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('La nueva contraseña debe tener al menos 8 caracteres.');
      return;
    }

    if (password !== confirmar) {
      setError('Las contraseñas ingresadas no coinciden.');
      return;
    }

    setLoading(true);
    try {
      const { data } = await cambiarPasswordInicial(password);
      if (onPasswordCambiada) {
        onPasswordCambiada(data);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al actualizar la contraseña');
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div
      className="dialog-backdrop"
      style={{
        zIndex: 9999,
        backgroundColor: 'rgba(15, 23, 42, 0.85)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        className="dialog"
        style={{
          maxWidth: 480,
          width: '90%',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.1)',
        }}
      >
        <div
          className="dialog-head"
          style={{
            borderBottom: '1px solid var(--color-border)',
            paddingBottom: '12px',
          }}
        >
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: 'var(--accent-tint, rgba(13, 71, 161, 0.1))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--color-accent, #0d47a1)',
              }}
            >
              <Lock size={18} />
            </div>
            <div>
              <div className="dialog-title" style={{ fontSize: 16 }}>Primer Ingreso al Portal</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                Cambio obligatorio de contraseña
              </div>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="dialog-body" style={{ paddingTop: 16 }}>
            <p style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--color-text-muted)', marginTop: 0 }}>
              Hola <strong>{user?.nombre || user?.username}</strong>. Has iniciado sesión con una contraseña provisoria. Por seguridad institucional, debes establecer tu nueva contraseña personal antes de acceder a tus servicios y recursos.
            </p>

            {error && (
              <div
                className="login__error"
                style={{
                  textAlign: 'left',
                  fontSize: 13,
                  padding: '8px 12px',
                  borderRadius: 4,
                  marginBottom: 16,
                }}
              >
                {error}
              </div>
            )}

            <div className="field">
              <label htmlFor="nueva-password">Nueva contraseña</label>
              <input
                id="nueva-password"
                className="input"
                type="password"
                placeholder="Mínimo 8 caracteres"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="field">
              <label htmlFor="confirmar-password">Confirmar nueva contraseña</label>
              <input
                id="confirmar-password"
                className="input"
                type="password"
                placeholder="Repite la nueva contraseña"
                value={confirmar}
                onChange={(e) => setConfirmar(e.target.value)}
                required
              />
            </div>

            <div
              style={{
                fontSize: 12,
                color: 'var(--color-text-muted)',
                marginTop: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <ShieldCheck size={14} style={{ color: 'var(--st-ok, #22c55e)' }} />
              <span>Esta será tu contraseña permanente para los próximos accesos.</span>
            </div>
          </div>

          <div
            className="dialog-actions"
            style={{
              borderTop: '1px solid var(--color-border)',
              paddingTop: 14,
              marginTop: 16,
            }}
          >
            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={loading}
              style={{ width: '100%' }}
            >
              {loading ? 'Guardando contraseña…' : 'Guardar y Continuar'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}

