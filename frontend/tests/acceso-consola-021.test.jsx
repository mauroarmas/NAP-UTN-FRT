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
