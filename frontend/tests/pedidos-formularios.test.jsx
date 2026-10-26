import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import NuevoPedidoModal from '../src/components/NuevoPedidoModal.jsx';
import AprobarPedidoModal from '../src/components/AprobarPedidoModal.jsx';
import * as api from '../src/services/api.js';
import { sizes } from './fixtures/tamanos';

vi.mock('../src/services/api.js', () => ({
  getTemplates: vi.fn(), getTamanos: vi.fn(), getCatedras: vi.fn(), getCatedrasMias: vi.fn(), createPedido: vi.fn(),
  getCalendario: vi.fn(), getPeriodosCalendario: vi.fn(), evaluarPedido: vi.fn(), aprobarPedido: vi.fn(), getCapacidad: vi.fn(),
}));

const templates = [
  { id: 1, nombre: 'Linux', modelo_servicio: 'iaas', tipo: 'lxc', activo: true, default_vcpus: 1, default_ram_mb: 512, default_disk_gb: 4, minimum_resources: { vcpus: 1, ram_mb: 512, disk_gb: 4 } },
  { id: 2, nombre: 'PostgreSQL', modelo_servicio: 'paas', tipo: 'lxc', activo: true, default_vcpus: 2, default_ram_mb: 1024, default_disk_gb: 10, minimum_resources: { vcpus: 1, ram_mb: 512, disk_gb: 4 } },
];
const teacher = { rol: 'catedra_admin' };
const dates = { tipo: 'personalizado', desde: '2027-03-01', hasta: '2027-06-30' };

beforeEach(() => {
  vi.clearAllMocks();
  api.getTamanos.mockResolvedValue({ data: sizes });
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
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Servicio', exact: true })).toHaveValue('2'));
  expect(screen.getByRole('button', { name: /PaaS/ })).toHaveAttribute('aria-pressed', 'true');
  view.rerender(<NuevoPedidoModal {...props} open={false} />);
  api.getTemplates.mockResolvedValue({ data: [templates[0]] });
  view.rerender(<NuevoPedidoModal {...props} />);
  expect(await screen.findByText(/perfil elegido dejó de estar disponible/)).toBeVisible();
  expect(screen.getByRole('combobox', { name: 'Servicio', exact: true })).toHaveValue('');
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

test('cambiar tamaño actualiza disponibilidad automáticamente antes de aprobar', async () => {
  const user = userEvent.setup();
  api.evaluarPedido.mockImplementation(async (_id, payload) => ({ data: {
    pedido_id: 1, seleccion: payload, version_solicitada: '1.0.0', version_efectiva: '2.0.0', cambio_version: true, capacidad_token: 'token-' + payload.asignacion.ram_mb,
    justificacion_requerida: payload.asignacion.ram_mb > 512, restricciones_fisicas: [],
    costo_incremental: payload.asignacion, destino: payload.destino,
    vigencia_efectiva: { inicio_at: '2027-03-01T03:00:00Z', fin_exclusivo_at: '2027-07-01T03:00:00Z' },
  } }));
  render(<AprobarPedidoModal open pedido={{ id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates }} templates={templates} onClose={vi.fn()} />);
  await waitFor(() => expect(api.evaluarPedido).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(/Se usará la versión 2.0.0/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Evaluar asignación' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('radio', { name: /^Medium/ }));
  expect(screen.getByRole('button', { name: 'Aprobar pedido' })).toBeDisabled();
  await user.type(await screen.findByLabelText(/Justificación/), 'Capacidad deliberada para la práctica');
  await user.click(screen.getByRole('button', { name: 'Aprobar pedido' }));
  await waitFor(() => expect(api.aprobarPedido).toHaveBeenCalled());
  const payload = api.aprobarPedido.mock.calls[0][1];
  expect(payload.asignacion).toMatchObject({ ram_mb: 1024, vcpus: 2, disk_gb: 8, tamano: 'medium' });
  expect(payload.capacidad_token).toBe('token-1024');
});

test('409 conserva selección, fechas y motivo y permite actualizar disponibilidad', async () => {
  const user = userEvent.setup();
  api.evaluarPedido.mockImplementation(async (_id, seleccion) => ({ data: {
    seleccion, capacidad_token: 'token', justificacion_requerida: true, restricciones_fisicas: [], costo_incremental: seleccion.asignacion,
  } }));
  api.aprobarPedido.mockRejectedValue({ response: { status: 409, data: { detail: {
    codigo: 'token_desactualizado', mensaje: 'La capacidad cambió. Volvé a evaluar.',
  } } } });
  render(<AprobarPedidoModal open pedido={{ id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates }} templates={templates} onClose={vi.fn()} />);
  await user.type(await screen.findByLabelText(/Justificación/), 'Motivo que debe conservarse');
  await user.click(screen.getByRole('button', { name: 'Aprobar pedido' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La capacidad cambió');
  expect(screen.getByRole('radio', { name: /^Small/ })).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Cambiar fechas' }));
  expect(screen.getByLabelText('Fecha desde')).toHaveValue('2027-03-01');
  expect(screen.getByLabelText('Fecha hasta')).toHaveValue('2027-06-30');
  expect(screen.getByRole('button', { name: 'Aprobar pedido' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Actualizar disponibilidad' }));
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
  await user.type(screen.getByLabelText('Nombre de la solicitud'), 'Prácticas de consultas');
  await user.type(screen.getByLabelText('Justificación pedagógica'), 'Datos válidos para conservar');
  await user.click(screen.getByRole('button', { name: 'Ciclo Lectivo Anual' }));
  const year = screen.getByLabelText('Año lectivo');
  await user.clear(year); await user.type(year, '2028');
  const send = screen.getByRole('button', { name: 'Enviar solicitud', exact: true });
  await waitFor(() => expect(send).toBeEnabled());
  await user.click(send);
  expect(await screen.findByText('Revisar antes de confirmar.')).toBeVisible();
  expect(api.createPedido.mock.calls[0][0].vigencia).toEqual({ tipo: 'anual', anio_lectivo: 2028 });
  expect(screen.getByLabelText('Justificación pedagógica')).toHaveValue('Datos válidos para conservar');
  expect(screen.queryByLabelText('Fecha hasta')).not.toBeInTheDocument();
  await user.click(send);
  expect(api.createPedido.mock.calls[0][1]).toBe(api.createPedido.mock.calls[1][1]);
});

test('Otro guarda servicio, título y justificación sin seleccionar una plantilla ficticia', async () => {
  const user = userEvent.setup();
  api.createPedido.mockResolvedValue({ data: { id: 30, estado: 'solicitado' } });
  const onCreated = vi.fn();
  render(<NuevoPedidoModal open user={teacher} onClose={vi.fn()} onCreated={onCreated} />);
  await waitFor(() => expect(screen.getByLabelText('Plantilla')).toHaveValue('1'));
  await user.click(screen.getByRole('button', { name: /SaaS/ }));
  expect(screen.getByLabelText('Servicio')).toHaveValue('otro');
  const send = screen.getByRole('button', { name: 'Enviar solicitud', exact: true });
  expect(send).toBeDisabled();
  await user.type(screen.getByLabelText('¿Qué software o servicio necesitás?'), 'Libro virtual');
  await user.type(screen.getByLabelText('Nombre de la solicitud'), 'Apuntes de Bases de Datos');
  await user.type(screen.getByLabelText('Justificación pedagógica'), 'Publicar apuntes y ejercicios para 40 estudiantes.');
  await user.click(screen.getByRole('button', { name: 'Rango Personalizado' }));
  await user.type(screen.getByLabelText('Fecha desde'), '2027-03-01');
  await user.type(screen.getByLabelText('Fecha hasta'), '2027-06-30');
  await user.click(send);
  await waitFor(() => expect(onCreated).toHaveBeenCalled());
  expect(api.createPedido.mock.calls[0][0]).toEqual({ modelo_servicio: 'saas', template_id: null, catedra_id: 1,
    descripcion_requerimientos: 'Publicar apuntes y ejercicios para 40 estudiantes.', vigencia: dates,
    parametros_extra: { titulo: 'Apuntes de Bases de Datos', software_solicitado: 'Libro virtual' } });
});

test('cambiar de Otro a catálogo no arrastra el software solicitado', async () => {
  const user = userEvent.setup();
  render(<NuevoPedidoModal open user={teacher} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Plantilla')).toHaveValue('1'));
  await user.click(screen.getByRole('button', { name: /PaaS/ }));
  await user.selectOptions(screen.getByLabelText('Servicio'), 'otro');
  await user.type(screen.getByLabelText('¿Qué software o servicio necesitás?'), 'Otro motor');
  await user.selectOptions(screen.getByLabelText('Servicio'), '2');
  expect(screen.queryByLabelText('¿Qué software o servicio necesitás?')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /IaaS/ }));
  expect(screen.queryByRole('option', { name: 'Otro', exact: true })).not.toBeInTheDocument();
});

test('la solicitud sólo consulta años lectivos desde 2026 y bloquea fechas anteriores', async () => {
  const user = userEvent.setup();
  api.getCalendario.mockImplementation(async (year) => ({ data: { anio: Number(year),
    periodos: [{ tipo: 'primer_cuatrimestre', desde: `${year}-03-01`, hasta: `${year}-06-30` }] } }));
  render(<NuevoPedidoModal open user={teacher} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Plantilla')).toHaveValue('1'));
  await user.type(screen.getByLabelText('Nombre de la solicitud'), 'Prácticas');
  await user.type(screen.getByLabelText('Justificación pedagógica'), 'Resolver ejercicios.');
  const year = screen.getByLabelText('Año lectivo');
  expect(year).toHaveAttribute('min', '2026');
  await user.clear(year); await user.type(year, '2025');
  expect(await screen.findByText('Elegí un año lectivo entre 2026 y 9998.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Enviar solicitud', exact: true })).toBeDisabled();
  expect(api.getCalendario.mock.calls.some(([value]) => String(value) === '2025')).toBe(false);
  await user.clear(year); await user.type(year, '2026');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar solicitud', exact: true })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Rango Personalizado' }));
  expect(screen.getByLabelText('Fecha desde')).toHaveAttribute('min', '2026-01-01');
  await user.type(screen.getByLabelText('Fecha desde'), '2025-12-31');
  await user.type(screen.getByLabelText('Fecha hasta'), '2026-03-01');
  expect(await screen.findByText('Las fechas deben corresponder a 2026 o un año posterior.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Enviar solicitud', exact: true })).toBeDisabled();
});


test('una respuesta anterior no habilita aprobar el tamaño equivocado', async () => {
  const user = userEvent.setup();
  let resolveFirst;
  api.evaluarPedido.mockImplementation(async (_id, seleccion) => {
    const response = { data: { seleccion, capacidad_token: 'token-' + seleccion.asignacion.ram_mb,
      justificacion_requerida: false, restricciones_fisicas: [], costo_incremental: seleccion.asignacion } };
    if (seleccion.asignacion.ram_mb === 512) return new Promise((resolve) => { resolveFirst = () => resolve(response); });
    return response;
  });
  render(<AprobarPedidoModal open pedido={{ id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates }} templates={templates} onClose={vi.fn()}/>);
  await waitFor(() => expect(resolveFirst).toBeTypeOf('function'));
  await user.click(screen.getByRole('radio', { name: /^Medium/ }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Aprobar pedido' })).toBeEnabled());
  resolveFirst();
  await user.click(screen.getByRole('button', { name: 'Aprobar pedido' }));
  await waitFor(() => expect(api.aprobarPedido).toHaveBeenCalledOnce());
  expect(api.aprobarPedido.mock.calls[0][1]).toMatchObject({ capacidad_token: 'token-1024', asignacion: { tamano: 'medium', ram_mb: 1024 } });
});

test('actualizaciones del listado no borran las fechas editadas ni el tamaño', async () => {
  const user = userEvent.setup();
  api.evaluarPedido.mockImplementation(async (_id, seleccion) => ({ data: {
    seleccion, capacidad_token: 'token', justificacion_requerida: false, restricciones_fisicas: [], costo_incremental: seleccion.asignacion,
  } }));
  const pedido = { id: 1, template_id: 1, modelo_servicio: 'iaas', vigencia: dates };
  const props = { open: true, pedido, templates, onClose: vi.fn() };
  const { rerender } = render(<AprobarPedidoModal {...props}/>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Aprobar pedido' })).toBeEnabled());
  await user.click(screen.getByRole('radio', { name: /^Medium/ }));
  await user.click(screen.getByRole('button', { name: 'Cambiar fechas' }));
  await user.clear(screen.getByLabelText('Fecha hasta'));
  await user.type(screen.getByLabelText('Fecha hasta'), '2027-07-15');
  rerender(<AprobarPedidoModal {...props} pedido={{ ...pedido }} templates={templates.map(row => ({ ...row }))}/>);
  expect(screen.getByRole('radio', { name: /^Medium/ })).toBeChecked();
  expect(screen.getByLabelText('Fecha hasta')).toHaveValue('2027-07-15');
});
