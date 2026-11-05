import { useCallback, useEffect, useState } from 'react';
import { getMe, logout as cerrarSesion } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function useSession() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [codes, setCodes] = useState(null);
  const refresh = useCallback(async (transition) => {
    try {
      const { data } = await getMe();
      setSession(data);
      setError('');
      if (transition?.codigos_recuperacion) setCodes(transition.codigos_recuperacion);
    } catch (err) {
      setSession(null);
      if (err.response?.status !== 401) setError(mensajeError(err, 'No se pudo consultar la sesión.'));
    } finally { setLoading(false); }
  }, []);
  const logout = useCallback(async () => {
    try {
      await cerrarSesion();
      setSession(null); setCodes(null); setError('');
      return true;
    } catch (err) { setError(mensajeError(err, 'No se pudo confirmar el cierre de sesión.')); return false; }
  }, []);
  useEffect(() => {
    // Se descartan sin interpretar datos heredados; el servidor acredita acceso.
    localStorage.removeItem('token'); localStorage.removeItem('user');
    refresh();
    const invalid = () => { setSession(null); setCodes(null); };
    const reload = () => { refresh(); };
    window.addEventListener('nap:session-invalid', invalid);
    window.addEventListener('nap:session-refresh', reload);
    return () => {
      window.removeEventListener('nap:session-invalid', invalid);
      window.removeEventListener('nap:session-refresh', reload);
    };
  }, [refresh]);
  return { session, user: session?.usuario, loading, error, refresh, logout, codes, clearCodes: () => setCodes(null) };
}
