import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AplicacionPropiaForm from '../src/components/AplicacionPropiaForm';
import * as api from '../src/services/api';
vi.mock('../src/services/api', async (original) => ({ ...await original(), agregarAplicacionPropia: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
async function fill(user) {
  await user.type(screen.getByLabelText('Nombre del servicio'), 'Campus de prácticas');
  await user.type(screen.getByLabelText('Imagen Docker'), 'universidad/campus:curso');
  await user.type(screen.getByLabelText('Puerto de la aplicación'), '8080');
}
test('alta breve sin hardware, preparación ni publicación; muestra progreso hasta confirmar', async () => {
  const user = userEvent.setup(); let finish;
  api.agregarAplicacionPropia.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const added = vi.fn(); const busy = vi.fn();
  render(<AplicacionPropiaForm onAdded={added} onBusyChange={busy}/>);
  expect(screen.getByText('Opciones de la aplicación').parentElement).not.toHaveAttribute('open');
  await fill(user);
  expect(screen.queryByText(/VMID|Entorno de prueba|Publicar|vCPU/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Verificando la imagen');
  expect(screen.getByRole('button', { name: /Verificando imagen/ })).toBeDisabled();
  expect(api.agregarAplicacionPropia).toHaveBeenCalledWith(expect.objectContaining({ nombre: 'Campus de prácticas', imagen: 'universidad/campus:curso', puerto: 8080, origen: 'imagen_docker' }), expect.any(String));
  expect(added).not.toHaveBeenCalled();
  finish({ data: { id: 8, oferta_disponible: true } });
  await waitFor(() => expect(added).toHaveBeenCalledWith({ id: 8, oferta_disponible: true }));
});
test('error conserva los campos y repetir sin cambios conserva la clave idempotente', async () => {
  const user = userEvent.setup();
  api.agregarAplicacionPropia.mockRejectedValue({ response: { data: { detail: { mensaje: 'La imagen todavía no está disponible.' } } } });
  render(<AplicacionPropiaForm/>); await fill(user);
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La imagen todavía no está disponible.');
  expect(screen.getByLabelText('Imagen Docker')).toHaveValue('universidad/campus:curso');
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));
  await waitFor(() => expect(api.agregarAplicacionPropia).toHaveBeenCalledTimes(2));
  expect(api.agregarAplicacionPropia.mock.calls[0][1]).toBe(api.agregarAplicacionPropia.mock.calls[1][1]);
  await user.type(screen.getByLabelText('Nombre del servicio'), ' nueva');
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));
  await waitFor(() => expect(api.agregarAplicacionPropia).toHaveBeenCalledTimes(3));
  expect(api.agregarAplicacionPropia.mock.calls[2][1]).not.toBe(api.agregarAplicacionPropia.mock.calls[0][1]);
});
test('opciones declaran persistencia y secretos sin pedir valores privados al agregar', async () => {
  const user = userEvent.setup(); api.agregarAplicacionPropia.mockResolvedValue({ data: { id: 4 } });
  render(<AplicacionPropiaForm/>); await fill(user);
  await user.click(screen.getByText('Opciones de la aplicación'));
  await user.type(screen.getByLabelText('Carpetas que conservan datos'), '/data\n/uploads');
  await user.click(screen.getByRole('button', { name: 'Agregar dato privado' }));
  await user.type(screen.getByLabelText('Variable privada 1'), 'APP_PASSWORD');
  await user.type(screen.getByLabelText('Etiqueta del dato privado 1'), 'Contraseña inicial');
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));
  await waitFor(() => expect(api.agregarAplicacionPropia).toHaveBeenCalledWith(expect.objectContaining({ persistencia: ['/data', '/uploads'], secretos: [{ nombre: 'APP_PASSWORD', etiqueta: 'Contraseña inicial', modo: 'generado' }] }), expect.any(String)));
});
