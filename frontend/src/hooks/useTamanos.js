import { useEffect, useState } from 'react';
import { getTamanos } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function useTamanos(enabled = true) {
  const [sizes, setSizes] = useState([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    setLoading(true); setError('');
    getTamanos().then(({ data }) => { if (active) setSizes(data); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar Small y Medium.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [enabled, attempt]);
  return { sizes, loading, error, retry: () => setAttempt((value) => value + 1) };
}
