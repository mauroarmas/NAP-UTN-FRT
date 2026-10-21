import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import useRemoteData from '../src/hooks/useRemoteData';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('respuesta anterior no reemplaza un alcance nuevo ni muestra sus datos', async () => {
  const old = deferred(), next = deferred();
  const load = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  const view = renderHook(({ scope }) => useRemoteData(load, { key: scope }), { initialProps: { scope: 'anterior' } });
  view.rerender({ scope: 'nuevo' });
  expect(view.result.current.data).toBeNull();
  await act(async () => next.resolve({ data: ['nuevo'] }));
  expect(view.result.current.data).toEqual(['nuevo']);
  await act(async () => old.resolve({ data: ['anterior'] }));
  expect(view.result.current.data).toEqual(['nuevo']);
});

test('fallo al actualizar conserva el último éxito y la fecha anterior', async () => {
  const load = vi.fn().mockResolvedValueOnce({ data: ['confirmado'] }).mockRejectedValue(new Error('fallo inducido'));
  const view = renderHook(() => useRemoteData(load, { errorMessage: 'Consulta fallida' }));
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  const time = view.result.current.updatedAt;
  await act(async () => view.result.current.reload());
  expect(view.result.current.error).toBe('Consulta fallida');
  expect(view.result.current.data).toEqual(['confirmado']);
  expect(view.result.current.updatedAt).toBe(time);
});

test('desmontar cancela la solicitud pendiente para el transporte', async () => {
  let signal;
  const load = vi.fn((options) => { signal = options.signal; return new Promise(() => {}); });
  const view = renderHook(() => useRemoteData(load));
  expect(signal.aborted).toBe(false);
  view.unmount();
  expect(signal.aborted).toBe(true);
});
