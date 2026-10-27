import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import App from '../src/App';
import Seguridad, { CodigosRecuperacion } from '../src/pages/Seguridad';
import useSession from '../src/hooks/useSession';
import { getMe, preparar2FA, cancelarSetup2FA, logout } from '../src/services/api';

vi.mock('../src/services/api', () => ({ getMe: vi.fn(), login: vi.fn(), getCsrf: vi.fn(), preparar2FA: vi.fn(), cancelarSetup2FA: vi.fn(), logout: vi.fn() }));
vi.mock('../src/pages/Dashboard', () => ({ default: () => <p>Portal operativo</p> }));
vi.mock('../src/components/TopNav', () => ({ default: () => <nav>Menú del portal</nav> }));
beforeEach(() => { vi.resetAllMocks(); });

test('perfil local dañado no autoriza ni impide restaurar la sesión del servidor', async () => {
  localStorage.setItem('user', '{malformed');
  localStorage.setItem('token', 'legacy');
  getMe.mockResolvedValue({ data: { estado: 'operativo', usuario: { id: 1, nombre: 'Titular', rol: 'admin' } } });
  render(<App />);
  expect(await screen.findByText('Portal operativo')).toBeVisible();
  expect(localStorage.getItem('token')).toBeNull();
  expect(localStorage.getItem('user')).toBeNull();
});

test.each(['onboarding', 'mfa_pending', 'recovery'])('etapa %s no monta el portal detrás', async (estado) => {
  getMe.mockResolvedValue({ data: { estado, usuario: { id: 1, nombre: 'Titular', rol: 'admin', debe_cambiar_password: estado === 'onboarding' }, desafio: { id: 'fixture' } } });
  render(<App />);
  expect(await screen.findByText(/Completar acceso|Cambiar contraseña inicial|Recuperar segundo factor/)).toBeVisible();
  expect(screen.queryByText('Portal operativo')).not.toBeInTheDocument();
  expect(screen.queryByText('Menú del portal')).not.toBeInTheDocument();
});

test('2FA desactivado permite operar y una configuración cancelada conserva esa elección', async () => {
  preparar2FA.mockResolvedValue({ data: { desafio_id: 'pending', secret: 'FIXTURE-NOT-REAL', provisioning_uri: 'otpauth://fixture' } });
  cancelarSetup2FA.mockResolvedValue({ status: 204 });
  const onRefresh = vi.fn();
  render(<Seguridad user={{ totp_habilitado: false }} onRefresh={onRefresh} />);
  expect(screen.getByText(/El segundo factor es opcional.*desactivado/)).toBeVisible();
  await userEvent.type(screen.getByLabelText('Contraseña actual'), 'secreto123');
  await userEvent.click(screen.getByRole('button', { name: 'Activar segundo factor opcional' }));
  expect(await screen.findByLabelText('Clave del autenticador')).toHaveValue('FIXTURE-NOT-REAL');
  await userEvent.click(screen.getByRole('button', { name: 'Cancelar configuración' }));
  await waitFor(() => expect(cancelarSetup2FA).toHaveBeenCalledWith('pending'));
  expect(onRefresh).not.toHaveBeenCalled();
});

test('los códigos se muestran en memoria para guardarlos y se cierran explícitamente', async () => {
  const onClose = vi.fn();
  render(<CodigosRecuperacion codes={['one-use-fixture-code']} onClose={onClose} />);
  expect(screen.getByLabelText('Códigos de recuperación')).toHaveValue('one-use-fixture-code');
  expect(localStorage.getItem('codigos_recuperacion')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Ya guardé los códigos' }));
  expect(onClose).toHaveBeenCalledOnce();
});

test('cerrar sesión llama al servidor antes de retirar el estado de acceso', async () => {
  getMe.mockResolvedValue({ data: { estado: 'operativo', usuario: { id: 1 } } });
  logout.mockResolvedValue({ status: 204 });
  const { result } = renderHook(() => useSession());
  await waitFor(() => expect(result.current.session?.estado).toBe('operativo'));
  await act(async () => { await result.current.logout(); });
  expect(logout).toHaveBeenCalledOnce();
  expect(result.current.session).toBeNull();
});
