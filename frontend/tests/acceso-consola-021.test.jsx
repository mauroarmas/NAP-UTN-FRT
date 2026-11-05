import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi, beforeEach } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), getConsolaServicio: vi.fn(), abrirAplicacionServicio: vi.fn(),
  actualizarAccesoConsola: vi.fn(),
}));
import * as api from '../src/services/api';

const base = { servicio_id: 7, modelo_servicio: 'iaas', producto: 'linux', disponibilidad: 'utilizable', metodo: 'consola', puede_revelar_credenciales: true };
const destino = { data: { url: 'https://nodo.example:8006/?console=lxc&xtermjs=1&vmid=100&node=n1', login_url: 'https://nodo.example:8006/', servicio_id: 7, vmid: 100, node: 'n1' } };

beforeEach(() => { vi.clearAllMocks(); api.getConsolaServicio.mockResolvedValue(destino); });

async function abrir(usuario, rol = 'catedra_admin') {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: usuario } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol }} />);
  return screen.findByRole('button', { name: 'Abrir terminal' });
}

test('con el acceso de nap la indicación junto a la terminal nombra a nap, sin pedir root', async () => {
  await abrir('nap');
  const indicacion = screen.getByText(/Se abre acá, en el portal/).closest('div');
  expect(indicacion).toHaveTextContent(/Entrá como nap con la contraseña de «Revelar acceso inicial»/);
  expect(indicacion).not.toHaveTextContent(/como root/);
});

test('mientras el servicio no se actualizó se indica root', async () => {
  await abrir('root');
  expect(screen.getByText(/Se abre acá, en el portal/).closest('div')).toHaveTextContent(/Entrá como root/);
});

test('la persona de cátedra no ve el respaldo de administración con la interfaz de la infraestructura', async () => {
  await abrir('nap');
  expect(screen.queryByText('Respaldo de administración')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Consultar consola' })).toBeNull();
});

test('administración ve la acción de actualizar sólo si el servicio todavía usa root', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'root' } });
  const { unmount } = render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  expect(await screen.findByRole('button', { name: 'Actualizar acceso de consola' })).toBeVisible();
  unmount();
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'nap' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  await screen.findByRole('button', { name: 'Abrir terminal' });
  expect(screen.queryByRole('button', { name: 'Actualizar acceso de consola' })).toBeNull();
});

test('la persona de cátedra no ve la acción de administración', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, consola_usuario: 'root' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  await screen.findByRole('button', { name: 'Abrir terminal' });
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
