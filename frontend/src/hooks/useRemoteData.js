import { useCallback, useEffect, useRef, useState } from 'react';
import { mensajeError } from '../utils/errors';

/** Consulta cancelable; conserva el último éxito dentro del mismo alcance. */
export default function useRemoteData(load, { key = 'default', enabled = true, refreshMs = 0,
  canRefresh, errorMessage = 'No se pudo consultar la información.' } = {}) {
  const [state, setState] = useState({ key, data: null, error: '', loading: enabled, updatedAt: null });
  const loader = useRef(load);
  const options = useRef({ canRefresh, errorMessage });
  const request = useRef({ version: 0, controller: null, running: false, mounted: false });
  useEffect(() => { loader.current = load; options.current = { canRefresh, errorMessage }; });
  const reload = useCallback(async () => {
    if (!enabled || !request.current.mounted) return;
    request.current.controller?.abort();
    const version = ++request.current.version;
    const controller = new AbortController();
    request.current.controller = controller;
    request.current.running = true;
    setState((previous) => ({ ...(previous.key === key ? previous : { data: null, updatedAt: null }),
      key, error: '', loading: true }));
    try {
      const result = await loader.current({ signal: controller.signal });
      if (!request.current.mounted || request.current.version !== version || controller.signal.aborted) return;
      setState({ key, data: result.data, error: '', loading: false, updatedAt: new Date() });
    } catch (error) {
      if (!request.current.mounted || request.current.version !== version || controller.signal.aborted) return;
      setState((previous) => ({ ...previous, loading: false,
        error: mensajeError(error, options.current.errorMessage) }));
    } finally {
      if (request.current.version === version) request.current.running = false;
    }
  }, [key, enabled]);
  useEffect(() => {
    const current = request.current;
    current.mounted = true;
    if (enabled) reload();
    return () => {
      current.mounted = false;
      current.version += 1;
      current.controller?.abort();
      current.running = false;
    };
  }, [reload, enabled]);
  useEffect(() => {
    if (!enabled || !refreshMs) return;
    const refresh = () => {
      if (document.hidden || request.current.running || options.current.canRefresh?.() === false) return;
      reload();
    };
    const timer = setInterval(refresh, refreshMs);
    document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [enabled, refreshMs, reload]);
  const current = state.key === key ? state : { data: null, error: '', loading: enabled, updatedAt: null };
  return { ...current, loading: enabled && current.loading, reload };
}
