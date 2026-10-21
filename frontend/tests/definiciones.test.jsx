import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import Definiciones from '../src/pages/Definiciones';
import TemplatesAdmin from '../src/components/TemplatesAdmin';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({ getDefiniciones: vi.fn(), crearDefinicion: vi.fn(), guardarManifest: vi.fn(),
  validarDefinicion: vi.fn(), publicarDefinicion: vi.fn(), retirarDefinicion: vi.fn(), registrarEvidencia: vi.fn(),
  createTemplate: vi.fn(), updateTemplate: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

test('crear una versión básica conserva el modelo propio sin publicarla', async () => {
  const user = userEvent.setup();
  api.getDefiniciones.mockResolvedValue({ data: [] });
  api.crearDefinicion.mockResolvedValue({ data: { id: 'new-version', codigo: 'base-docente', version: '1.0.0',
    producto: 'postgresql', modelo_servicio: 'paas', estado: 'borrador', manifest: {} } });
  render(<Definiciones />);
  await user.type(screen.getByLabelText('Código'), 'base-docente');
  await user.selectOptions(screen.getByLabelText('Producto'), 'postgresql');
  await user.click(screen.getByRole('button', { name: 'Crear borrador' }));
  await waitFor(() => expect(api.crearDefinicion).toHaveBeenCalledWith({ codigo: 'base-docente', version: '1.0.0',
    producto: 'postgresql', modelo_servicio: 'paas' }, expect.any(String)));
  expect(await screen.findByText('Versión seleccionada: base-docente 1.0.0')).toBeVisible();
  expect(api.publicarDefinicion).not.toHaveBeenCalled();
});

test('una versión validada es inmutable y publicar requiere acción explícita', async () => {
  const user = userEvent.setup();
  const row = { id: 'validated', codigo: 'linux-curso', version: '1.0.0', producto: 'linux',
    modelo_servicio: 'iaas', estado: 'validada', manifest: { definition_key: 'linux-curso' } };
  api.getDefiniciones.mockResolvedValue({ data: [row] });
  api.publicarDefinicion.mockResolvedValue({ data: { ...row, estado: 'publicada' } });
  render(<Definiciones />);
  await user.click(await screen.findByRole('button', { name: /linux-curso 1.0.0/ }));
  expect(screen.getByLabelText('Manifiesto JSON')).toHaveAttribute('readOnly');
  expect(api.publicarDefinicion).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Publicar versión' }));
  await waitFor(() => expect(api.publicarDefinicion).toHaveBeenCalledWith('validated', expect.any(String)));
});

test('el perfil solo elige definiciones publicadas compatibles y respeta sus mínimos', async () => {
  const user = userEvent.setup();
  api.getDefiniciones.mockResolvedValue({ data: [
    { id: 'linux', codigo: 'linux', version: '1.0.0', modelo_servicio: 'iaas', estado: 'publicada' },
    { id: 'pg', codigo: 'base', version: '1.0.0', modelo_servicio: 'paas', estado: 'publicada',
      minimum_resources: { vcpus: 2, ram_mb: 1024, disk_gb: 8 } },
    { id: 'draft', codigo: 'borrador', version: '1.0.0', modelo_servicio: 'paas', estado: 'borrador' },
  ] });
  api.createTemplate.mockResolvedValue({ data: { id: 1 } });
  render(<TemplatesAdmin open onClose={vi.fn()} onGuardado={vi.fn()} />);
  await user.type(screen.getByLabelText('Nombre del perfil'), 'Base de laboratorio');
  await user.selectOptions(screen.getByLabelText('Modelo de servicio'), 'paas');
  await user.selectOptions(await screen.findByLabelText('Definición publicada'), 'pg');
  expect(screen.queryByRole('option', { name: /borrador/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText('RAM (MB)')).toHaveValue(1024);
  await user.click(screen.getByRole('button', { name: 'Crear perfil' }));
  await waitFor(() => expect(api.createTemplate).toHaveBeenCalledWith(expect.objectContaining({
    definicion_version_id: 'pg', tipo: 'lxc', modelo_servicio: 'paas', default_vcpus: 2, default_ram_mb: 1024, default_disk_gb: 8 })));
});
