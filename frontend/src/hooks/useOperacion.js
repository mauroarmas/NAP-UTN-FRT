import { useEffect, useRef, useState } from 'react';
import { obtenerOperacion } from '../services/api';

export const operacionAbierta = (operation) => ['pendiente', 'en_curso', 'incierta'].includes(operation?.estado);

export function textoOperacion(operation) {
  if (operation?.error_consulta) return 'No se pudo actualizar la operación. Conservamos el último resultado.';
  if (operation?.error_codigo?.startsWith('pool_') && ['pendiente', 'en_curso'].includes(operation.estado)) {
    return `${operation.error_detalle_seguro || 'Falta comprobar el pool de la cátedra.'} Se volverá a comprobar antes de desplegar.`;
  }
  if (operation?.estado === 'confirmada' && operation.sin_cambios) return 'Orden cerrada sin cambios: se actualizó la cobertura.';
  return {
    pendiente: 'Orden admitida. Resultado pendiente.',
    en_curso: 'Operación en curso. Esperando confirmación.',
    incierta: 'Resultado incierto. Estamos comprobando el recurso.',
    fallida: 'Operación fallida. Revisá el diagnóstico antes de reintentar.',
    confirmada: operation?.tipo === 'desplegar' || operation?.tipo === 'reparar'
      ? 'Infraestructura confirmada. Falta verificar el acceso a la aplicación.'
      : 'Efecto de infraestructura confirmado.',
  }[operation?.estado] || 'Consultando operación…';
}

export default function useOperacion(ids, onConfirmed) {
  const [operations, setOperations] = useState({});
  const cache = useRef({});
  const notified = useRef(new Set());
  const callback = useRef(onConfirmed);
  useEffect(() => { callback.current = onConfirmed; }, [onConfirmed]);
  const key = [...new Set(ids.filter(Boolean))].sort().join(',');

  useEffect(() => {
    if (!key) return;
    let timer;
    let stopped = false;
    let failures = 0;
    let running = false;
    const controller = new AbortController();
    const tracked = key.split(',');
    async function poll() {
      if (stopped || document.hidden || running) return;
      running = true;
      let failed = false;
      let completed = false;
      await Promise.all(tracked.map(async (id) => {
        if (cache.current[id] && !operacionAbierta(cache.current[id])) return;
        try {
          const { data } = await obtenerOperacion(id, controller.signal);
          if (stopped) return;
          cache.current = { ...cache.current, [id]: data };
          if (!operacionAbierta(data) && !notified.current.has(id)) {
            notified.current.add(id);
            completed = true;
          }
        } catch {
          if (stopped) return;
          failed = true;
          cache.current = { ...cache.current, [id]: { ...cache.current[id], operation_id: id,
            estado: cache.current[id]?.estado || 'pendiente', error_consulta: true } };
        }
      }));
      running = false;
      if (stopped) return;
      setOperations({ ...cache.current });
      if (completed) callback.current?.();
      failures = failed ? failures + 1 : 0;
      if (tracked.some((id) => !cache.current[id] || operacionAbierta(cache.current[id]))) {
        timer = setTimeout(poll, Math.min(30000, 2000 * 2 ** Math.min(failures, 4)));
      }
    }
    const visible = () => {
      clearTimeout(timer);
      if (!document.hidden) poll();
    };
    document.addEventListener('visibilitychange', visible);
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller.abort();
      document.removeEventListener('visibilitychange', visible);
    };
  }, [key]);
  return operations;
}
