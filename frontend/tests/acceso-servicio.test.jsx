import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), verificarAccesoServicio: vi.fn(), registrarEvidencia: vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());

test('docente ve un estado simple sin recibir secretos antes de habilitar el acceso', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { servicio_id: 1, disponibilidad: 'no_verificada',
    puede_revelar_credenciales: false, estado_entrega: 'pendiente_verificacion', instrucciones: 'Falta comprobar acceso desde la red prevista.' } });
  render(<AccesoServicio servicio={{ id: 1 }} user={{ rol: 'catedra_admin' }} />);
  expect(await screen.findByText('El servicio se inició. El acceso todavía no está habilitado.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /Revelar/ })).not.toBeInTheDocument();
  expect(api.revelarAccesoServicio).not.toHaveBeenCalled();
});

test('administración consulta sus datos de acceso sin copiar contraseñas automáticamente', async () => {
  const user = userEvent.setup();
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  api.getAccesoServicio.mockResolvedValue({ data: { servicio_id: 1, disponibilidad: 'no_verificada',
    puede_revelar_credenciales: true, estado_entrega: 'solo_validacion', instrucciones: 'Preparación local confirmada.' } });
  api.revelarAccesoServicio.mockResolvedValue({ data: { servicio_id: 1, estado_entrega: 'solo_validacion',
    metodo: 'postgresql', credenciales: { usuario: 'nap_curso', password: 'test-private-access' } } });
  render(<AccesoServicio servicio={{ id: 1 }} user={{ rol: 'admin' }} />);
  const reveal = await screen.findByRole('button', { name: /Revelar acceso inicial/ });
  expect(api.revelarAccesoServicio).not.toHaveBeenCalled();
  await user.click(reveal);
  expect(await screen.findByText('test-private-access')).toBeVisible();
  expect(screen.getByText('El servicio se inició. Podés abrirlo y consultar sus datos de acceso.')).toBeVisible();
  expect(copy).not.toHaveBeenCalled();
});

test('el acceso de administración no requiere documentos ni confirmaciones técnicas', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { servicio_id: 1, estado_entrega: 'solo_validacion',
    puede_revelar_credenciales: true, metodo: 'https', producto: 'drawio', direccion: 'https://drawio.example.edu',
    verificacion_instancia: { resource_uuid: 'technical-resource-uuid', nonce_sha256: 'technical-hash' } } });
  render(<AccesoServicio servicio={{ id: 1 }} user={{ rol: 'admin' }} />);
  expect(await screen.findByRole('link', { name: 'Abrir aplicación', exact: true })).toHaveAttribute('href', 'https://drawio.example.edu/');
  expect(screen.queryByText(/Registrar evidencia|Confirmar prueba de acceso|Identidad para la evidencia/)).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.queryByText(/technical-resource-uuid|technical-hash/)).not.toBeInTheDocument();
  expect(api.registrarEvidencia).not.toHaveBeenCalled();
  expect(api.verificarAccesoServicio).not.toHaveBeenCalled();
});
