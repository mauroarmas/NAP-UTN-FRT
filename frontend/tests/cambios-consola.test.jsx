import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import CambiosConsola from '../src/pages/CambiosConsola.jsx';
import RegistroEvidencia from '../src/components/RegistroEvidencia.jsx';
import { listarCambiosConsola, obtenerCambioConsola, registrarEvidencia, confirmarRevocacionConsola } from '../src/services/api.js';

vi.mock('../src/services/api.js', () => ({
  listarCambiosConsola: vi.fn(), obtenerCambioConsola: vi.fn(), registrarEvidencia: vi.fn(),
  confirmarRevocacionConsola: vi.fn(), registrarFalloConsola: vi.fn(),
}));

test('docente no recibe controles ni consultas del trámite administrativo', () => {
  render(<CambiosConsola user={{ rol: 'catedra_admin' }} />);
  expect(screen.getByText('Acceso reservado a administración')).toBeVisible();
  expect(listarCambiosConsola).not.toHaveBeenCalled();
});

test('importar evidencia devuelve referencia y no completa el cambio por sí solo', async () => {
  registrarEvidencia.mockResolvedValue({ data: { evidencia_ref: 'proof-uuid', sha256: 'checksum' } });
  const onRegistered = vi.fn();
  render(<RegistroEvidencia onRegistered={onRegistered} />);
  const user = userEvent.setup();
  await user.click(screen.getByLabelText('Documento de evidencia'));
  await user.paste('{"tipo":"revocacion_consola"}');
  await user.click(screen.getByRole('button', { name: 'Registrar evidencia' }));
  expect(await screen.findByText('proof-uuid')).toBeVisible();
  expect(onRegistered).toHaveBeenCalledWith({ evidencia_ref: 'proof-uuid', sha256: 'checksum' });
  expect(confirmarRevocacionConsola).not.toHaveBeenCalled();
});

test('el trámite pendiente no muestra confirmación terminada antes de la respuesta', async () => {
  const change = { id: 'change-uuid', estado: 'pendiente', accion: 'reasignar', usuario_id: 1,
    catedra_id: 2, revision_esperada: 1, identidad_nativa: 'docente@pve',
    scopes_anteriores: ['/pool/catedra-2'], scopes_propuestos: [], cambio_propuesto: { titular_id: 3 } };
  listarCambiosConsola.mockResolvedValue({ data: [change] });
  obtenerCambioConsola.mockResolvedValue({ data: change });
  render(<CambiosConsola user={{ rol: 'admin' }} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Ver trámite' }));
  expect(screen.queryByText('Cambio completado')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Confirmar revocación' })).toBeDisabled();
  expect(confirmarRevocacionConsola).not.toHaveBeenCalled();
});
