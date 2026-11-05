import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi, beforeEach } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), getConsolaServicio: vi.fn(), abrirAplicacionServicio: vi.fn(),
}));
import * as api from '../src/services/api';

const base = { servicio_id: 7, modelo_servicio: 'iaas', producto: 'linux', disponibilidad: 'utilizable', metodo: 'consola' };
const rechazo = (status, codigo, mensaje) => ({ response: { status, data: { detail: { codigo, mensaje, reintentable: status === 503 } } } });

beforeEach(() => {
  vi.clearAllMocks();
  api.getAccesoServicio.mockResolvedValue({ data: base });
});

async function consultar() {
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'admin' }} />);
  await userEvent.click(await screen.findByText('Respaldo de administración'));      // sólo administración, plegado por omisión
  await userEvent.click(await screen.findByRole('button', { name: 'Consultar consola' }));
}

test.each([
  [409, 'consola_no_habilitada', 'La consola todavía no está habilitada para tu cuenta. Pedíselo a administración.'],
  [409, 'servicio_no_disponible', 'El servicio debe estar encendido y con vigencia para abrir la consola.'],
  [503, 'consola_nodo_no_disponible', 'La consola no está disponible ahora. Probá de nuevo en unos minutos.'],
])('muestra el motivo en lenguaje llano sin datos de infraestructura (%s %s)', async (status, codigo, mensaje) => {
  api.getConsolaServicio.mockRejectedValue(rechazo(status, codigo, mensaje));
  await consultar();
  expect(await screen.findByText(mensaje)).toBeVisible();
  expect(screen.queryByRole('link', { name: /Abrir consola/ })).toBeNull();
});

test('con la consola habilitada ofrece primero el inicio de sesión del mismo nodo y luego el destino', async () => {
  api.getConsolaServicio.mockResolvedValue({ data: { url: 'https://nodo.example:8006/?console=lxc&xtermjs=1&vmid=100&node=n1', login_url: 'https://nodo.example:8006/', servicio_id: 7, vmid: 100, node: 'n1' } });
  await consultar();
  const login = await screen.findByRole('link', { name: 'Iniciar sesión' });
  expect(login).toHaveAttribute('href', 'https://nodo.example:8006/');
  const link = await screen.findByRole('link', { name: 'Abrir consola de esta instancia' });
  await waitFor(() => expect(link).toHaveAttribute('href', expect.stringContaining('xtermjs=1')));
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});
