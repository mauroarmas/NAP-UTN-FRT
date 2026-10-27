import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { Dialog } from '../src/components/ui';
import Metricas from '../src/pages/Metricas';
import Servicios from '../src/pages/Servicios';
import AccesoServicio from '../src/components/AccesoServicio';
import * as api from '../src/services/api';

vi.mock('../src/services/api', async (original) => ({ ...await original(),
  getResumenMetricas: vi.fn(), capturarMetricas: vi.fn(), getHistorialMetricas: vi.fn(),
  listarServicios: vi.fn(), getPedidos: vi.fn(), getCatedras: vi.fn(), getCatedrasMias: vi.fn(),
  getTemplates: vi.fn(), listarOperaciones: vi.fn(), getOperacion: vi.fn(),
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(),
  getAlertas: vi.fn(), getAvisos: vi.fn(), getEstadoCorreo: vi.fn(),
}));
const admin = { id: 1, rol: 'admin' };
const services = ['iaas', 'paas', 'saas'].map((modelo, i) => ({ id: i + 1, catedra_id: 1,
  template_id: 1, nombre_snapshot: ['Linux experimental', 'Base experimental', 'Libro experimental'][i],
  modelo_servicio: modelo, estado: 'running', vcpus_asignados: 1, ram_asignada_mb: 512,
  disk_asignado_gb: 4, cobertura_actual: true, acciones_habilitadas: [] }));

beforeEach(() => {
  vi.clearAllMocks();
  api.getAlertas.mockResolvedValue({ data: [] });
  api.getAvisos.mockResolvedValue({ data: [] });
  api.getEstadoCorreo.mockResolvedValue({ data: [] });
  api.listarServicios.mockResolvedValue({ data: services });
  api.getPedidos.mockResolvedValue({ data: [] });
  api.getCatedras.mockResolvedValue({ data: [{ id: 1, nombre: 'Cátedra experimental' }] });
  api.getCatedrasMias.mockResolvedValue({ data: [{ id: 1, nombre: 'Cátedra experimental' }] });
  api.getTemplates.mockResolvedValue({ data: [] });
  api.listarOperaciones.mockResolvedValue({ data: [] });
});

test('carga, error y vacío confirmado son estados distintos y ofrecen reintento', async () => {
  let reject;
  api.getResumenMetricas.mockReturnValueOnce(new Promise((resolve, fail) => { reject = fail; }))
    .mockResolvedValueOnce({ data: [] });
  render(<Metricas user={admin} />);
  expect(screen.getByRole('status')).toHaveTextContent(/cargando/i);
  reject(new Error('Fallo de consulta inducido'));
  expect(await screen.findByRole('alert')).toHaveTextContent(/consultar|error/i);
  expect(screen.queryByText('No hay servicios con métricas disponibles.')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /reintentar/i }));
  expect(await screen.findByText(/No hay servicios con métricas disponibles/)).toBeVisible();
});

test('un refresco fallido conserva servicios previos y muestra su antigüedad', async () => {
  api.listarServicios.mockResolvedValueOnce({ data: services }).mockRejectedValue(new Error('Fallo inducido'));
  render(<Servicios user={admin} />);
  expect(await screen.findByText('Libro experimental')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/anteriores|actualizar|consultar/i);
  expect(screen.getByText('Libro experimental')).toBeVisible();
  expect(screen.getByText(/última.*(consulta|actualización)|datos de/i)).toBeVisible();
});

test('fallo parcial del catálogo no elimina los servicios y queda anunciado', async () => {
  api.getTemplates.mockRejectedValue(new Error('Catálogo no disponible'));
  render(<Servicios user={admin} />);
  expect(await screen.findByText('Libro experimental')).toBeVisible();
  expect(await screen.findByRole('alert')).toHaveTextContent(/perfil|catálogo|plantilla/i);
});

test('filtro usa el modelo guardado aunque todos sean LXC', async () => {
  render(<Servicios user={admin} />);
  expect(await screen.findByText('Libro experimental')).toBeVisible();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filtrar por tipo de servicio' }), 'paas');
  expect(screen.getByText('Base experimental')).toBeVisible();
  expect(screen.queryByText('Libro experimental')).not.toBeInTheDocument();
  expect(screen.queryByText('Linux experimental')).not.toBeInTheDocument();
});

test('Clipboard denegado nunca anuncia contraseña copiada', async () => {
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new DOMException('Denied', 'NotAllowedError'));
  api.getAccesoServicio.mockResolvedValue({ data: { puede_revelar_credenciales: true, estado_entrega: 'entregado' } });
  api.revelarAccesoServicio.mockResolvedValue({ data: { metodo: 'postgresql',
    credenciales: { usuario: 'laboratorio', password: 'solo-fixture' } } });
  render(<AccesoServicio servicio={{ id: 1 }} user={admin} />);
  await user.click(await screen.findByRole('button', { name: 'Revelar acceso inicial' }));
  await user.click(screen.getByRole('button', { name: /Copiar contraseña/ }));
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.queryByText(/Contraseña copiada/)).not.toBeInTheDocument();
});

test('revelado en curso impide repetir el envío', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { puede_revelar_credenciales: true } });
  api.revelarAccesoServicio.mockReturnValue(new Promise(() => {}));
  render(<AccesoServicio servicio={{ id: 1 }} user={admin} />);
  const reveal = await screen.findByRole('button', { name: 'Revelar acceso inicial' });
  await userEvent.dblClick(reveal);
  expect(reveal).toBeDisabled();
  expect(api.revelarAccesoServicio).toHaveBeenCalledTimes(1);
});

function Harness() {
  const [open, setOpen] = useState(false);
  return <main><button onClick={() => setOpen(true)}>Abrir formulario</button>
    {open && <Dialog title="Formulario de prueba" onClose={() => setOpen(false)} actions={<button>Guardar</button>}>
      <label htmlFor="test-name">Nombre</label><input id="test-name" autoFocus />
    </Dialog>}</main>;
}

test('diálogo nombrado retiene Tab y Shift+Tab, vuelve al disparador al cerrar', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  const trigger = screen.getByRole('button', { name: 'Abrir formulario' });
  await user.click(trigger);
  const dialog = screen.getByRole('dialog', { name: 'Formulario de prueba' });
  expect(dialog).toHaveAttribute('aria-modal', 'true');
  expect(within(dialog).getByLabelText('Nombre')).toHaveFocus();
  within(dialog).getByRole('button', { name: 'Guardar' }).focus();
  await user.tab();
  expect(dialog.contains(document.activeElement)).toBe(true);
  within(dialog).getByRole('button', { name: 'Cerrar' }).focus();
  await user.tab({ shift: true });
  expect(dialog.contains(document.activeElement)).toBe(true);
  await user.keyboard('{Escape}');
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
