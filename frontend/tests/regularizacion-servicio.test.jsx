import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import RegularizarServicioModal from '../src/components/RegularizarServicioModal';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({ evaluarRegularizacion: vi.fn(), confirmarRegularizacion: vi.fn(), archivarDuplicadoLegacy: vi.fn() }));
const preview = { servicio_id: 7, fuente_sha256: 'a'.repeat(64), puede_regularizar: true, puede_archivar_duplicado: false,
  motivos: [], nombre: 'Servicio histórico #7', modelo_servicio: 'iaas', desde: null, hasta: null,
  zona_horaria: 'America/Argentina/Tucuman', conflictos: [], asignacion_observada: { vcpus: 2, ram_mb: 1024, disk_gb: 20 }, estado_observado: 'stopped' };
beforeEach(() => { vi.clearAllMocks(); api.evaluarRegularizacion.mockResolvedValue({ data: preview }); });
const show = (props = {}) => render(<RegularizarServicioModal servicio={{ id: 7 }} user={{ rol: 'admin' }} onClose={vi.fn()} {...props} />);
async function fill(user) {
  await screen.findByText(/Configuración comprobada/);
  fireEvent.change(screen.getByLabelText('Fecha inicial respaldada'), { target: { value: '2026-10-21' } });
  fireEvent.change(screen.getByLabelText('Fecha final respaldada'), { target: { value: '2026-11-21' } });
  await user.type(screen.getByLabelText('Referencia del respaldo'), 'ACTA-009');
  await user.type(screen.getByLabelText('Motivo de la decisión'), 'Fechas corroboradas');
}

test('conserva fechas desconocidas vacías y no habilita ninguna gestión docente', async () => {
  const view = show();
  await screen.findByText(/Configuración comprobada/);
  expect(screen.getByLabelText('Fecha inicial respaldada')).toHaveValue('');
  expect(screen.getByLabelText('Fecha final respaldada')).toHaveValue('');
  expect(api.confirmarRegularizacion).not.toHaveBeenCalled();
  view.unmount(); vi.clearAllMocks();
  show({ user: { rol: 'catedra_admin' } });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(api.evaluarRegularizacion).not.toHaveBeenCalled();
});

test('doble envío y Escape durante confirmación no duplican ni cierran la decisión', async () => {
  const user = userEvent.setup(); const onClose = vi.fn(); const onConfirmed = vi.fn();
  let finish;
  api.confirmarRegularizacion.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  show({ onClose, onConfirmed }); await fill(user);
  const form = screen.getByRole('button', { name: 'Confirmar regularización' }).closest('form');
  fireEvent.submit(form); fireEvent.submit(form);
  expect(api.confirmarRegularizacion).toHaveBeenCalledTimes(1);
  expect(api.confirmarRegularizacion.mock.calls[0][1]).toMatchObject({ desde: '2026-10-21', hasta: '2026-11-21', asignacion: preview.asignacion_observada });
  expect(screen.getByLabelText('Fecha inicial respaldada')).toBeDisabled();
  await user.keyboard('{Escape}'); expect(onClose).not.toHaveBeenCalled();
  await act(async () => finish({ data: { servicio_id: 7, disponibilidad_aplicacion: 'no_verificada' } }));
  expect(onConfirmed).toHaveBeenCalledWith({ servicio_id: 7, disponibilidad_aplicacion: 'no_verificada' });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('conflicto conserva campos, permite reevaluar y no anuncia éxito', async () => {
  const user = userEvent.setup(); const onClose = vi.fn(); const onConfirmed = vi.fn();
  api.confirmarRegularizacion.mockRejectedValue({ response: { status: 409, data: { detail: { mensaje: 'La propiedad cambió; volvé a evaluar' } } } });
  show({ onClose, onConfirmed }); await fill(user);
  await user.click(screen.getByRole('button', { name: 'Confirmar regularización' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La propiedad cambió');
  expect(screen.getByLabelText('Fecha inicial respaldada')).toHaveValue('2026-10-21');
  expect(screen.getByLabelText('Referencia del respaldo')).toHaveValue('ACTA-009');
  expect(onClose).not.toHaveBeenCalled(); expect(onConfirmed).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Volver a evaluar' }));
  await waitFor(() => expect(api.evaluarRegularizacion).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText('Fecha inicial respaldada')).toHaveValue('2026-10-21');
});

test('duplicado requiere selección explícita del principal y comprobación antes de archivar', async () => {
  const user = userEvent.setup(); const onConfirmed = vi.fn();
  const conflict = { ...preview, puede_regularizar: false, conflictos: [{ id: 2, nombre: 'Principal', misma_catedra: true }], motivos: ['Duplicado pendiente'] };
  api.evaluarRegularizacion.mockImplementation((_id, data) => Promise.resolve({ data: { ...conflict, puede_archivar_duplicado: data.canonico_id === 2 } }));
  api.archivarDuplicadoLegacy.mockResolvedValue({ data: { estado: 'registro_duplicado_archivado', principal_id: 2 } });
  show({ onConfirmed });
  await user.selectOptions(await screen.findByLabelText('Registro principal comprobado'), '2');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Archivar registro duplicado' })).toBeEnabled());
  await user.type(screen.getByLabelText('Referencia del respaldo'), 'ACTA-DUP');
  await user.type(screen.getByLabelText('Motivo de la decisión'), 'Duplicado corroborado');
  await user.click(screen.getByRole('button', { name: 'Archivar registro duplicado' }));
  await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
  expect(api.archivarDuplicadoLegacy).toHaveBeenCalledWith(7, { fuente_sha256: preview.fuente_sha256,
    canonico_id: 2, referencia: 'ACTA-DUP', motivo: 'Duplicado corroborado' }, expect.any(String));
  expect(api.confirmarRegularizacion).not.toHaveBeenCalled();
});
