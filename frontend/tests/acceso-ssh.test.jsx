import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';
import NuevoPedidoModal from '../src/components/NuevoPedidoModal.jsx';
import * as api from '../src/services/api';
import { sizes } from './fixtures/tamanos';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), getConsolaServicio: vi.fn(), abrirAplicacionServicio: vi.fn(),
  registrarAccesoSsh: vi.fn(), getTemplates: vi.fn(), getTamanos: vi.fn(), getCatedras: vi.fn(), getCatedrasMias: vi.fn(),
  createPedido: vi.fn(), getCalendario: vi.fn(), getPeriodosCalendario: vi.fn(),
}));

const CLAVE = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderClavePublicaDePrueba docente@equipo';
const linux = { id: 1, nombre: 'Ubuntu 24.04', modelo_servicio: 'iaas', tipo: 'lxc', activo: true, oferta_disponible: true,
  requiere_clave_ssh: true, default_vcpus: 1, default_ram_mb: 512, default_disk_gb: 4, minimum_resources: { vcpus: 1, ram_mb: 512, disk_gb: 4 } };
const base = { servicio_id: 7, modelo_servicio: 'iaas', producto: 'linux', disponibilidad: 'utilizable', metodo: 'consola',
  puede_revelar_credenciales: false, estado_entrega: 'entregado', instrucciones: 'Acceso inicial entregado.' };
const ssh = (extra) => ({ estado: 'aplicada', usuario: 'nap', direccion: '192.168.100.120', puerto: 22,
  comando: 'ssh nap@192.168.100.120', huella: 'SHA256:abc', verificado_at: null, puede_conectar: true, motivo: null, ...extra });

beforeEach(() => {
  vi.clearAllMocks();
  api.getTamanos.mockResolvedValue({ data: sizes });
  api.getTemplates.mockResolvedValue({ data: [linux] });
  api.getCatedras.mockResolvedValue({ data: [{ id: 1, nombre: 'Propia' }] });
  api.getCatedrasMias.mockResolvedValue({ data: [{ id: 1, nombre: 'Propia' }] });
  api.getCalendario.mockResolvedValue({ data: { anio: 2027, revision: 1, periodos: [] } });
  api.getPeriodosCalendario.mockResolvedValue({ data: { anio: 2027, periodos: [] } });
});

test('el pedido de un Linux exige la clave pública y la acepta pegada', async () => {
  const user = userEvent.setup();
  api.createPedido.mockResolvedValue({ data: { id: 1 } });
  render(<NuevoPedidoModal open onClose={vi.fn()} onCreated={vi.fn()} user={{ rol: 'catedra_admin' }} />);
  const campo = await screen.findByLabelText('Clave pública SSH');
  expect(campo).toBeRequired();
  expect(screen.getByText(/Nunca pegues la clave privada/)).toBeVisible();
  expect(screen.getByRole('button', { name: /Enviar solicitud/ })).toBeDisabled();
  await user.type(screen.getByLabelText('Nombre de la solicitud'), 'Práctica de redes');
  await user.type(screen.getByLabelText(/Justificación pedagógica/), 'Los estudiantes configuran servicios en Linux.');
  await user.click(campo);
  await user.paste(CLAVE);
  expect(campo).toHaveValue(CLAVE);
});

test('un servicio sin esa necesidad no muestra el campo de clave', async () => {
  api.getTemplates.mockResolvedValue({ data: [{ ...linux, requiere_clave_ssh: false }] });
  render(<NuevoPedidoModal open onClose={vi.fn()} user={{ rol: 'catedra_admin' }} />);
  await waitFor(() => expect(screen.getByRole('combobox', { name: /Plantilla/ })).toHaveValue('1'));
  expect(screen.queryByLabelText('Clave pública SSH')).not.toBeInTheDocument();
});

test('con el acceso aplicado se muestra el comando, la huella y se mantiene la consola', async () => {
  const user = userEvent.setup();
  const copiar = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, acceso_ssh: ssh() } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  expect(await screen.findByText('ssh nap@192.168.100.120')).toBeVisible();
  expect(screen.getByText('SHA256:abc')).toBeVisible();
  expect(screen.getByText(/No usa contraseña/)).toBeVisible();
  expect(screen.getByText(/terminal/i)).toBeVisible();      // la consola sigue ofreciéndose, ahora como terminal del portal
  await user.click(screen.getByRole('button', { name: 'Copiar comando' }));
  expect(copiar).toHaveBeenCalledWith('ssh nap@192.168.100.120');
});

test.each([
  ['pendiente', 'Estamos configurando el acceso.', 'Actualizar estado'],
  ['fallida', 'No se pudo configurar el acceso SSH.', 'Cambiar clave'],
  ['sin_clave', 'todavía no tiene una clave SSH', 'Agregar clave'],
])('estado %s: sin comando de conexión y con la acción que corresponde', async (estado, texto, boton) => {
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, acceso_ssh: ssh({ estado, puede_conectar: false, comando: null,
    direccion: null, motivo: texto + ' más detalle' }) } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  expect(await screen.findByText(new RegExp(texto))).toBeVisible();
  expect(screen.queryByText(/^ssh nap@/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: boton })).toBeVisible();
});

test('agregar una clave a un servicio existente la envía y vuelve a consultar el estado', async () => {
  const user = userEvent.setup();
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, acceso_ssh: ssh({ estado: 'sin_clave', puede_conectar: false,
    comando: null, direccion: null, huella: null, motivo: 'Este servicio todavía no tiene una clave SSH registrada.' }) } });
  api.registrarAccesoSsh.mockResolvedValue({ data: { estado: 'pendiente', huella: 'SHA256:nueva' } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  await user.click(await screen.findByRole('button', { name: 'Agregar clave' }));
  await user.click(screen.getByLabelText('Clave pública SSH'));
  await user.paste(CLAVE);
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, acceso_ssh: ssh({ estado: 'pendiente', puede_conectar: false, comando: null,
    direccion: null, motivo: 'Estamos configurando el acceso.' }) } });
  await user.click(screen.getByRole('button', { name: 'Agregar clave' }));
  await waitFor(() => expect(api.registrarAccesoSsh).toHaveBeenCalledWith(7, CLAVE, expect.any(String)));
  expect(await screen.findByText(/Estamos configurando el acceso/)).toBeVisible();
});

test('un rechazo de la clave se explica y conserva lo escrito', async () => {
  const user = userEvent.setup();
  api.getAccesoServicio.mockResolvedValue({ data: { ...base, acceso_ssh: ssh() } });
  api.registrarAccesoSsh.mockRejectedValue({ response: { status: 422, data: { detail: { codigo: 'clave_ssh_privada',
    mensaje: 'Pegaste una clave privada. Pegá solo la clave pública.' } } } });
  render(<AccesoServicio servicio={{ id: 7 }} user={{ rol: 'catedra_admin' }} />);
  await user.click(await screen.findByRole('button', { name: 'Cambiar clave' }));
  await user.click(screen.getByLabelText('Clave pública SSH'));
  await user.paste('-----BEGIN OPENSSH PRIVATE KEY-----');
  await user.click(screen.getByRole('button', { name: 'Cambiar clave', exact: true }));
  expect(await screen.findByText(/Pegaste una clave privada/)).toBeVisible();
  expect(screen.getByLabelText('Clave pública SSH')).toHaveValue('-----BEGIN OPENSSH PRIVATE KEY-----');
});
