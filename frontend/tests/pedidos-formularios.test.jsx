import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import NuevoPedidoModal from '../src/components/NuevoPedidoModal.jsx';
import AprobarPedidoModal from '../src/components/AprobarPedidoModal.jsx';
import * as api from '../src/services/api.js';

vi.mock('../src/services/api.js', () => ({
  getTemplates: vi.fn(), getCatedras: vi.fn(), getCatedrasMias: vi.fn(), createPedido: vi.fn(),
  getCalendario: vi.fn(), getPeriodosCalendario: vi.fn(), evaluarPedido: vi.fn(), aprobarPedido: vi.fn(), getCapacidad: vi.fn(),
}));

const templates = [
  { id: 1, nombre: 'Linux', modelo_servicio: 'iaas', tipo: 'lxc', activo: true, default_vcpus: 1, default_ram_mb: 512, default_disk_gb: 4 },
  { id: 2, nombre: 'PostgreSQL', modelo_servicio: 'paas', tipo: 'lxc', activo: true, default_vcpus: 2, default_ram_mb: 1024, default_disk_gb: 10 },
];
const teacher = { rol: 'catedra_admin' };
const dates = { tipo: 'personalizado', desde: '2027-03-01', hasta: '2027-06-30' };

beforeEach(() => {
  vi.clearAllMocks();
  api.getTemplates.mockResolvedValue({ data: templates });
  api.getCatedras.mockResolvedValue({ data: [{ id: 1, nombre: 'Propia' }] });
  api.getCatedrasMias.mockResolvedValue({ data: [{ id: 1, nombre: 'Propia' }] });
  api.getCalendario.mockResolvedValue({ data: { anio: 2027, revision: 1, periodos: [] } });
  api.getPeriodosCalendario.mockResolvedValue({ data: { anio: 2027, periodos: [] } });
  api.getCapacidad.mockResolvedValue({ data: { destinos: [] } });
  api.aprobarPedido.mockResolvedValue({ data: { id: 1, estado: 'aprobado' } });
});

test('reabrir una solicitud restaura modelo y plantilla compatibles', async () => {
  const user = userEvent.setup();
  const props = { open: true, onClose: vi.fn(), onCreated: vi.fn(), user: teacher };
  const view = render(<NuevoPedidoModal {...props} />);
  await waitFor(() => expect(screen.getByRole('button', { name: /PaaS/ })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: /PaaS/ }));
  view.rerender(<NuevoPedidoModal {...props} open={false} />);
  view.rerender(<NuevoPedidoModal {...props} />);
  await waitFor(() => expect(screen.getByRole('button', { name: /IaaS/ })).toHaveAttribute('aria-pressed', 'true'));
  expect(screen.getByRole('combobox', { name: /Plantilla/ })).toHaveValue('1');
  expect(screen.queryByRole('option', { name: /PostgreSQL/ })).not.toBeInTheDocument();
});

test('abrir desde catálogo conserva el perfil elegido y detecta su retiro', async () => {
  const props = { open: true, onClose: vi.fn(), user: teacher, initialTemplate: templates[1] };
  const view = render(<NuevoPedidoModal {...props} />);
  await waitFor(() => expect(screen.getByRole('combobox', { name: /Plantilla/ })).toHaveValue('2'));
  expect(screen.getByRole('button', { name: /PaaS/ })).toHaveAttribute('aria-pressed', 'true');
  view.rerender(<NuevoPedidoModal {...props} open={false} />);
  api.getTemplates.mockResolvedValue({ data: [templates[0]] });
  view.rerender(<NuevoPedidoModal {...props} />);
  expect(await screen.findByText(/perfil elegido dejó de estar disponible/)).toBeVisible();
  expect(screen.getByRole('combobox', { name: /Plantilla/ })).toHaveValue('');
  expect(api.createPedido).not.toHaveBeenCalled();
});

test('un año sin calendario explica el faltante sin inventar fechas', async () => {
  api.getCalendario.mockRejectedValue({ response: { status: 404, data: { detail: { codigo: 'calendario_no_configurado', mensaje: 'El año elegido no tiene calendario configurado' } } } });
  const user = userEvent.setup();
  render(<NuevoPedidoModal open onClose={vi.fn()} user={teacher} />);
  const year = await screen.findByLabelText('Año lectivo');
  await user.clear(year);
  await user.type(year, '2028');
  expect(await screen.findByText(/no tiene calendario configurado/)).toBeVisible();
  expect(api.createPedido).not.toHaveBeenCalled();
});

test('editar costo invalida la evaluación y el token hasta volver a evaluar', async () => {
  const user = userEvent.setup();
  api.evaluarPedido.mockImplementation(async (_id, payload) => ({ data: {
    pedido_id: 1, seleccion: payload, capacidad_token: 'token-' + payload.asignacion.ram_mb,
    justificacion_requerida: payload.asignacion.ram_mb > 512, restricciones_fisicas: [],
    costo_incremental: payload.asignacion, destino: payload.destino,
    vigencia_efectiva: { inicio_at: '2027-03-01T03:00:00Z', fin_exclusivo_at: '2027-07-01T03:00:00Z' },
  } }));
  render(<AprobarPedidoModal open pedido={{ id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates }} templates={templates} onClose={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Evaluar asignación' }));
  await waitFor(() => expect(api.evaluarPedido).toHaveBeenCalledTimes(1));
  const ram = screen.getByLabelText('RAM (MiB)');
  await user.clear(ram);
  await user.type(ram, '1024');
  expect(screen.getByRole('button', { name: /^Aprobar/ })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Evaluar asignación' }));
  await user.type(await screen.findByLabelText(/Justificación/), 'Capacidad deliberada para la práctica');
  await user.click(screen.getByRole('button', { name: /^Aprobar/ }));
  await waitFor(() => expect(api.aprobarPedido).toHaveBeenCalled());
  const payload = api.aprobarPedido.mock.calls[0][1];
  expect(payload.asignacion.ram_mb).toBe(1024);
  expect(payload.capacidad_token).toBe('token-1024');
});

test('409 conserva recursos, fechas y motivo pero exige reevaluar', async () => {
  const user = userEvent.setup();
  api.evaluarPedido.mockImplementation(async (_id, seleccion) => ({ data: {
    seleccion, capacidad_token: 'token', justificacion_requerida: true, restricciones_fisicas: [],
    costo_incremental: seleccion.asignacion,
  } }));
  api.aprobarPedido.mockRejectedValue({ response: { status: 409, data: { detail: {
    codigo: 'token_desactualizado', mensaje: 'La capacidad cambió. Volvé a evaluar.',
  } } } });
  render(<AprobarPedidoModal open pedido={{ id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates }} templates={templates} onClose={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Evaluar asignación' }));
  await user.type(await screen.findByLabelText(/Justificación/), 'Motivo que debe conservarse');
  await user.click(screen.getByRole('button', { name: /^Aprobar/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La capacidad cambió');
  expect(screen.getByLabelText('RAM (MiB)')).toHaveValue(512);
  expect(screen.getByLabelText('Fecha desde')).toHaveValue('2027-03-01');
  expect(screen.getByLabelText('Fecha hasta')).toHaveValue('2027-06-30');
  expect(screen.getByRole('button', { name: /^Aprobar/ })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Evaluar asignación' }));
  expect(await screen.findByLabelText(/Justificación/)).toHaveValue('Motivo que debe conservarse');
});

test('cambiar modalidad y año envía el objeto completo sin arrastrar fechas', async () => {
  const user = userEvent.setup();
  api.getCalendario.mockImplementation(async (year) => ({ data: { anio: Number(year), revision: 1,
    zona_horaria: 'America/Argentina/Tucuman', periodos: [{ tipo: 'anual', desde: `${year}-03-01`, hasta: `${year}-11-30` }] } }));
  api.createPedido.mockRejectedValue({ response: { status: 409, data: { detail: { codigo: 'conflicto', mensaje: 'Revisar antes de confirmar.' } } } });
  render(<NuevoPedidoModal open user={teacher} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Plantilla')).toHaveValue('1'));
  await user.click(screen.getByRole('button', { name: 'Rango Personalizado' }));
  await user.type(screen.getByLabelText('Fecha desde'), '2027-04-01');
  await user.type(screen.getByLabelText('Fecha hasta'), '2027-05-01');
  await user.type(screen.getByLabelText('Requerimientos o propósito'), 'Datos válidos para conservar');
  await user.click(screen.getByRole('button', { name: 'Ciclo Lectivo Anual' }));
  const year = screen.getByLabelText('Año lectivo');
  await user.clear(year); await user.type(year, '2028');
  const send = screen.getByRole('button', { name: 'Enviar solicitud', exact: true });
  await waitFor(() => expect(send).toBeEnabled());
  await user.click(send);
  expect(await screen.findByText('Revisar antes de confirmar.')).toBeVisible();
  expect(api.createPedido.mock.calls[0][0].vigencia).toEqual({ tipo: 'anual', anio_lectivo: 2028 });
  expect(screen.getByLabelText('Requerimientos o propósito')).toHaveValue('Datos válidos para conservar');
  expect(screen.queryByLabelText('Fecha hasta')).not.toBeInTheDocument();
  await user.click(send);
  expect(api.createPedido.mock.calls[0][1]).toBe(api.createPedido.mock.calls[1][1]);
});
