import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import Dashboard from '../src/pages/Dashboard';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({ getCatedras: vi.fn(), getProxmoxStatus: vi.fn(),
  getProxmoxResources: vi.fn(), getProxmoxStorage: vi.fn() }));
vi.mock('../src/components/PanelCatedra', () => ({ default: () => <p>Panel de cátedra</p> }));
const user = { id: 1, rol: 'admin' };
const GIB = 1024 ** 3;
beforeEach(() => {
  vi.clearAllMocks();
  api.getCatedras.mockResolvedValue({ data: [] });
  api.getProxmoxStatus.mockResolvedValue({ data: { status: 'connected', nodes: [] } });
  api.getProxmoxResources.mockResolvedValue({ data: [{ type: 'lxc' }] });
  api.getProxmoxStorage.mockResolvedValue({ data: [] });
});

test('un almacenamiento compartido se cuenta una vez y los locales homónimos se cuentan por nodo', async () => {
  const shared = { storage: 'universidad', compartido: true, usado_bytes: 20 * GIB, total_bytes: 100 * GIB };
  const local = { storage: 'local', compartido: false, usado_bytes: GIB, total_bytes: 10 * GIB };
  api.getProxmoxStorage.mockResolvedValue({ data: [
    { ...shared, node: 'pve1' }, { ...shared, node: 'pve2' },
    { ...local, node: 'pve1' }, { ...local, node: 'pve2' },
  ] });
  render(<Dashboard user={user}/>);
  expect(await screen.findByText('22.0 GiB de 120.0 GiB')).toBeVisible();
  expect(screen.getAllByText('universidad')).toHaveLength(1);
  expect(screen.getAllByText('local')).toHaveLength(2);
  expect(screen.getByText(/nodos pve1, pve2/)).toBeVisible();
});

test('una consulta fallida conserva el inventario anterior y permite actualizarlo', async () => {
  const actor = userEvent.setup();
  api.getProxmoxResources.mockResolvedValueOnce({ data: [{ type: 'lxc' }, { type: 'qemu' }] })
    .mockRejectedValueOnce(new Error('network'));
  render(<Dashboard user={user}/>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Actualizar estado' })).toBeEnabled());
  const card = screen.getByText('Recursos').closest('.stat');
  expect(within(card).getByText('2')).toBeVisible();
  await actor.click(screen.getByRole('button', { name: 'Actualizar estado' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron consultar los recursos de Proxmox. Conservamos los datos anteriores.');
  expect(within(card).getByText('2')).toBeVisible();
});

test('la falta de datos no se presenta como cero recursos ni conexión confirmada', async () => {
  api.getProxmoxStatus.mockRejectedValue(new Error('network'));
  api.getProxmoxResources.mockRejectedValue(new Error('network'));
  render(<Dashboard user={user}/>);
  expect(await screen.findByText('Sin confirmar')).toBeVisible();
  const card = screen.getByText('Recursos').closest('.stat');
  expect(within(card).getByText('—')).toBeVisible();
  expect(within(card).queryByText('0')).not.toBeInTheDocument();
});

test('el panel de cátedra no consulta el inventario administrativo', () => {
  render(<Dashboard user={{ id: 2, rol: 'catedra_admin' }}/>);
  expect(screen.getByText('Panel de cátedra')).toBeVisible();
  expect(api.getProxmoxStatus).not.toHaveBeenCalled();
  expect(api.getProxmoxStorage).not.toHaveBeenCalled();
});
