import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { expect, test, vi } from 'vitest';
import Login from '../src/pages/Login.jsx';
import { login, getMe } from '../src/services/api.js';

vi.mock('../src/services/api.js', () => ({ login: vi.fn(), getMe: vi.fn() }));

test.each(['Credenciales inválidas', {
  codigo: 'sesion_invalida', mensaje: 'Credenciales inválidas', reintentable: false,
}])('un ingreso rechazado informa el error y permite reintentar sin abrir el portal (%j)', async (detail) => {
  login.mockRejectedValueOnce({ response: { data: { detail } } });
  const onLogin = vi.fn();
  render(<MemoryRouter><Login onLogin={onLogin} /></MemoryRouter>);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Usuario o Correo'), 'docente');
  await user.type(screen.getByLabelText('Contraseña'), 'contraseña-de-prueba');
  await user.click(screen.getByRole('button', { name: 'Ingresar', exact: true }));
  expect(await screen.findByText('Credenciales inválidas')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Ingresar', exact: true })).toBeEnabled();
  expect(onLogin).not.toHaveBeenCalled();
  expect(getMe).not.toHaveBeenCalled();
});

test('el botón con icono de ojo conmuta la visibilidad de la contraseña', async () => {
  render(<MemoryRouter><Login onLogin={vi.fn()} /></MemoryRouter>);
  const user = userEvent.setup();
  const inputPass = screen.getByLabelText('Contraseña');
  expect(inputPass).toHaveAttribute('type', 'password');

  const toggleBtn = screen.getByRole('button', { name: /mostrar clave/i });
  await user.click(toggleBtn);
  expect(inputPass).toHaveAttribute('type', 'text');

  const hideBtn = screen.getByRole('button', { name: /ocultar clave/i });
  await user.click(hideBtn);
  expect(inputPass).toHaveAttribute('type', 'password');
});
