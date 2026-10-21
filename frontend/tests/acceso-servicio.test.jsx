import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({
  getAccesoServicio: vi.fn(), revelarAccesoServicio: vi.fn(), verificarAccesoServicio: vi.fn(), registrarEvidencia: vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());

test('docente no recibe revelado prematuro ni secretos en la carga inicial', async () => {
  api.getAccesoServicio.mockResolvedValue({ data: { servicio_id: 1, disponibilidad: 'no_verificada',
    puede_revelar_credenciales: false, instrucciones: 'Falta comprobar acceso desde la red prevista.' } });
  render(<AccesoServicio servicio={{ id: 1 }} user={{ rol: 'catedra_admin' }} />);
  expect(await screen.findByText('Falta comprobar acceso desde la red prevista.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /Revelar/ })).not.toBeInTheDocument();
  expect(api.revelarAccesoServicio).not.toHaveBeenCalled();
});

test('administración revela deliberadamente solo para validar y sin copiar automáticamente', async () => {
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
  expect(screen.getByText(/Solo para validación/)).toBeVisible();
  expect(copy).not.toHaveBeenCalled();
});

test('registrar evidencia no confirma acceso hasta una segunda acción explícita', async () => {
  const user = userEvent.setup();
  const initial = { servicio_id: 1, estado_entrega: 'solo_validacion', disponibilidad: 'no_verificada',
    puede_revelar_credenciales: true, metodo: 'postgresql', direccion: 'postgresql://base.example.edu:5432/curso' };
  api.getAccesoServicio.mockResolvedValueOnce({ data: initial }).mockResolvedValue({ data: { ...initial,
    estado_entrega: 'entregado', disponibilidad: 'utilizable' } });
  api.registrarEvidencia.mockResolvedValue({ data: { evidencia_ref: 'proof-uuid', sha256: 'test-sha' } });
  api.verificarAccesoServicio.mockResolvedValue({ data: { disponibilidad: 'utilizable' } });
  render(<AccesoServicio servicio={{ id: 1 }} user={{ rol: 'admin' }} />);
  const document = await screen.findByLabelText('Documento de evidencia');
  await user.click(document);
  await user.paste('{"tipo":"acceso_instancia","observado_at":"2026-10-20T20:00:00Z"}');
  await user.click(screen.getByRole('button', { name: 'Registrar evidencia', exact: true }));
  await waitFor(() => expect(screen.getByLabelText('Referencia UUID de evidencia registrada')).toHaveValue('proof-uuid'));
  expect(api.verificarAccesoServicio).not.toHaveBeenCalled();
  expect(api.revelarAccesoServicio).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Confirmar verificación de acceso' }));
  await waitFor(() => expect(api.verificarAccesoServicio).toHaveBeenCalledWith(1, {
    evidencia_ref: 'proof-uuid', endpoint: initial.direccion, observado_at: '2026-10-20T20:00:00Z',
  }, expect.any(String)));
  expect(await screen.findByText('Acceso verificado. La entrega quedó registrada.')).toBeVisible();
});
