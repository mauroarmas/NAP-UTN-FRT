import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import Definiciones from '../src/pages/Definiciones';
import PublicarOfertaModal from '../src/components/PublicarOfertaModal';
import TemplatesAdmin from '../src/components/TemplatesAdmin';
import * as api from '../src/services/api';
import { sizes } from './fixtures/tamanos';

vi.mock('../src/services/api', () => ({ sincronizarIaas: vi.fn(), getTemplates: vi.fn(), getTamanos: vi.fn(), getDefiniciones: vi.fn(),
  retirarTemplate: vi.fn(), reactivarTemplate: vi.fn(), createTemplate: vi.fn(), updateTemplate: vi.fn(), listarIncorporaciones: vi.fn(), getCategoriasAplicaciones: vi.fn(), buscarAplicaciones: vi.fn(), incorporarAplicacion: vi.fn(), editarIncorporacion: vi.fn() }));
const minimum = { vcpus: 1, ram_mb: 512, disk_gb: 4 };
beforeEach(() => {
  vi.clearAllMocks();
  api.sincronizarIaas.mockResolvedValue({data:{disponibles:2}});
  api.getTamanos.mockResolvedValue({ data: sizes });
  api.getTemplates.mockResolvedValue({ data: [{ id: 1, nombre: 'Linux de prácticas', tipo: 'lxc', activo: true,
    modelo_servicio: 'iaas', oferta_disponible: true, tamanos_permitidos: ['small', 'medium'], tamano_recomendado: 'small' }] });
  api.getDefiniciones.mockResolvedValue({ data: [] });
  api.getCategoriasAplicaciones.mockResolvedValue({ data: { items: [], fuente: { estado: 'disponible' } } });
  api.listarIncorporaciones.mockResolvedValue({ data: { items: [] } });
});

test('reúne servicios y tamaños sin mostrar el editor técnico en la vista inicial', async () => {
  render(<Definiciones />);
  expect(await screen.findByRole('heading', { name: 'Linux de prácticas' })).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Catálogo de servicios' })).toBeVisible();
  expect(screen.getByLabelText('Tamaños compartidos')).toHaveTextContent('1 vCPU · 512 MB RAM · 4 GB disco');
  expect(screen.queryByLabelText('Manifiesto JSON')).not.toBeInTheDocument();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
});

test('el retiro requiere una confirmación y conserva la fila histórica', async () => {
  const user = userEvent.setup();
  render(<Definiciones />);
  await user.click(await screen.findByRole('button', { name: 'Retirar', exact: true }));
  expect(api.retirarTemplate).not.toHaveBeenCalled();
  api.retirarTemplate.mockResolvedValue({ data: {} });
  api.getTemplates.mockResolvedValue({ data: [{ id: 1, nombre: 'Linux de prácticas', activo: false, tamanos_permitidos: ['small'] }] });
  await user.click(screen.getByRole('button', { name: 'Retirar del catálogo' }));
  await waitFor(() => expect(api.retirarTemplate).toHaveBeenCalledWith(1));
  expect(screen.queryByRole('heading', { name: 'Linux de prácticas' })).not.toBeInTheDocument();
  await user.click(screen.getByLabelText('Mostrar retirados'));
  expect(screen.getByRole('heading', { name: 'Linux de prácticas' })).toBeVisible();
});

test('una preparación mayor que Medium impide ofrecerla sin bajar sus mínimos', async () => {
  const user = userEvent.setup();
  api.getDefiniciones.mockResolvedValue({ data: [{ id: 'draw', codigo: 'drawio', producto: 'drawio',
    estado: 'publicada', modelo_servicio: 'saas', minimum_resources: { ...minimum, ram_mb: 2048 } }] });
  render(<TemplatesAdmin open onClose={vi.fn()} />);
  await user.selectOptions(await screen.findByLabelText('Servicio'), 'draw');
  expect(await screen.findByRole('alert')).toHaveTextContent('más recursos');
  expect(screen.getByRole('radio', { name: /^Small/ })).toBeDisabled();
  expect(screen.getByRole('radio', { name: /^Medium/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Agregar servicio' })).toBeDisabled();
  expect(api.createTemplate).not.toHaveBeenCalled();
});

test('publicar una revisión elige el servicio existente sin pedir IDs ni recursos libres', async () => {
  const user = userEvent.setup();
  api.getTemplates.mockResolvedValue({ data: [{ id: 9, codigo_definicion: 'drawio', revision: 4, version_ofrecida: '1.0.0', nombre: 'Diagramas', descripcion: 'Prácticas', tamano_recomendado: 'medium' }] });
  const publish = vi.fn();
  render(<PublicarOfertaModal trial={{ id: 'trial', definicion: { codigo: 'drawio', revision: 2, minimum_resources: minimum } }} onPublish={publish} />);
  await user.selectOptions(await screen.findByLabelText('Servicio del catálogo'), '9');
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Publicar oferta' }));
  expect(publish).toHaveBeenCalledWith({ revision_esperada: 2, ensayo_id: 'trial', perfil: {
    nombre: 'Diagramas', descripcion: 'Prácticas', tamano: 'medium', default_vcpus: 2, default_ram_mb: 1024, default_disk_gb: 8,
    template_id: 9, revision_esperada: 4,
  } });
});


test('Agregar servicio integra la biblioteca dentro de un solo diálogo', async () => {
  const user = userEvent.setup();
  render(<Definiciones />);
  expect(screen.queryByRole('button', { name: 'Preparación y biblioteca' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Agregar servicio', exact: true }));
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'diagramas');
  expect(screen.getByLabelText('Nombre de aplicación')).toHaveValue('diagramas');
});
