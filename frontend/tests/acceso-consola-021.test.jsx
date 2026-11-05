import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi, beforeEach } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), getConsolaServicio: vi.fn(), abrirAplicacionServicio: vi.fn(),
  actualizarAccesoConsola: vi.fn(),
}));
import * as api from '../src/services/api';

const base = { servicio_id: 7, modelo_servicio: 'iaas', producto: 'linux', disponibilidad: 'utilizable', metodo: 'consola' };
const destino = { data: { url: 'https://nodo.example:8006/?console=lxc&xtermjs=1&vmid=100&node=n1', login_url: 'https://nodo.example:8006/', servicio_id: 7, vmid: 100, node: 'n1' } };

beforeEach(() => { vi.clearAllMocks(); api.getConsolaServicio.mockResolvedValue(destino); });

async function consultar(usuario, rol = 'catedra_admin') {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: usuario } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol }} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Consultar consola' }));
}

test('con el acceso de nap la indicación nombra a nap y sudo, sin pedir root', async () => {
  await consultar('nap');
  const pasos = await screen.findByRole('list', { name: 'Pasos para abrir la consola' });
  expect(pasos).toHaveTextContent(/entrá como nap/);
  expect(pasos).toHaveTextContent(/sudo/);
  expect(pasos).not.toHaveTextContent(/entrá como root/);
});

test('mientras el servicio no se actualizó se indica root', async () => {
  await consultar('root');
  expect(await screen.findByRole('list', { name: 'Pasos para abrir la consola' })).toHaveTextContent(/entrá como root/);
});

test('administración ve la acción de actualizar sólo si el servicio todavía usa root', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'root' } });
  const { unmount } = render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  expect(await screen.findByRole('button', { name: 'Actualizar acceso de consola' })).toBeVisible();
  unmount();
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'nap' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  await screen.findByRole('button', { name: 'Consultar consola' });
  expect(screen.queryByRole('button', { name: 'Actualizar acceso de consola' })).toBeNull();
});

test('la persona de cátedra no ve la acción de administración', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'root' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  await screen.findByRole('button', { name: 'Consultar consola' });
  expect(screen.queryByRole('button', { name: 'Actualizar acceso de consola' })).toBeNull();
});

test('actualizar llama a la API del servicio y avisa que hay que volver a revelar el acceso', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'root' } });
  api.actualizarAccesoConsola.mockResolvedValue({ data: { estado: 'pendiente' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Actualizar acceso de consola' }));
  expect(api.actualizarAccesoConsola).toHaveBeenCalledWith(7);
  expect(await screen.findByText(/volver a revelar el acceso inicial/)).toBeVisible();
});
