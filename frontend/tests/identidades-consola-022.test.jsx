import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi, beforeEach } from 'vitest';
import IdentidadesConsola from '../src/pages/IdentidadesConsola';

vi.mock('../src/services/api', () => ({ listarIdentidadesConsola: vi.fn(), reintentarIdentidadConsola: vi.fn() }));
import * as api from '../src/services/api';

const filas = [
  { usuario_id: 1, nombre: 'Docente Uno', estado: 'lista', pools_aplicados: ['catedra-3'], ultimo_error_seguro: null, reconciliada_at: '2026-11-04T20:00:00Z' },
  { usuario_id: 2, nombre: 'Docente Dos', estado: 'con_error', pools_aplicados: [], ultimo_error_seguro: 'No se pudo confirmar en la infraestructura; se reintenta automáticamente.', reconciliada_at: null },
];

beforeEach(() => { vi.clearAllMocks(); api.listarIdentidadesConsola.mockResolvedValue({ data: filas }); });

test('administración ve el estado de cada persona sin credenciales ni identidades técnicas', async () => {
  render(<IdentidadesConsola user={{ rol: 'admin' }} />);
  const tabla = await screen.findByRole('table', { name: 'Identidades de consola' });
  expect(within(tabla).getByText('Docente Uno')).toBeVisible();
  expect(within(tabla).getByText('Lista')).toBeVisible();
  expect(within(tabla).getByText('Con error')).toBeVisible();
  expect(within(tabla).getByText(/se reintenta automáticamente/)).toBeVisible();
  expect(tabla).not.toHaveTextContent(/nap-u|@pve|password|contraseña/i);
});

test('sólo las identidades con error ofrecen reintentar y el reintento llama a la API una vez', async () => {
  api.reintentarIdentidadConsola.mockResolvedValue({ data: { estado: 'reintento_solicitado' } });
  render(<IdentidadesConsola user={{ rol: 'admin' }} />);
  await screen.findByRole('table');
  expect(screen.getAllByRole('button', { name: 'Reintentar' })).toHaveLength(1);
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(api.reintentarIdentidadConsola).toHaveBeenCalledTimes(1);
  expect(api.reintentarIdentidadConsola).toHaveBeenCalledWith(2);
  expect(await screen.findByRole('status')).toHaveTextContent(/Docente Dos/);
});

test('un error de la API se muestra en lenguaje llano', async () => {
  api.listarIdentidadesConsola.mockRejectedValue({ response: { data: { detail: { mensaje: 'No disponible ahora.' } } } });
  render(<IdentidadesConsola user={{ rol: 'admin' }} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('No disponible ahora.');
});

test('quien no es administración no ve la pantalla', () => {
  render(<IdentidadesConsola user={{ rol: 'catedra_admin' }} />);
  expect(screen.getByText('Acceso reservado a administración')).toBeVisible();
  expect(api.listarIdentidadesConsola).not.toHaveBeenCalled();
});
