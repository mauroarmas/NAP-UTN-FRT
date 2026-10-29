import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AgregarServicioModal from '../src/components/AgregarServicioModal';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({
  getCategoriasAplicaciones: vi.fn(),
  buscarAplicaciones: vi.fn(),
  agregarAplicacionPropia: vi.fn(),
  listarIncorporaciones: vi.fn(),
}));

const HUB_ITEMS = [
  {
    nombre: 'traefik/whoami',
    repositorio: 'traefik/whoami',
    referencia: 'traefik/whoami:latest',
    descripcion: 'Tiny Go webserver that prints OS information and HTTP request to output',
    procedencia: 'comunidad',
    distintivos: [],
    estrellas: 72,
    descargas: 45000000,
    categorias: [],
  },
  {
    nombre: 'library/ubuntu',
    repositorio: 'library/ubuntu',
    referencia: 'library/ubuntu:latest',
    descripcion: 'Ubuntu base OS image',
    procedencia: 'oficial',
    distintivos: ['oficial'],
    estrellas: 16000,
    descargas: 1000000000,
    categorias: [],
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  api.getCategoriasAplicaciones.mockResolvedValue({ data: { items: [], fuente: { proveedor: 'docker_hub' } } });
  api.listarIncorporaciones.mockResolvedValue({ data: { items: [] } });
});

test('Docker Hub como biblioteca: busca por nombre, muestra procedencia y distintivos', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockResolvedValue({
    data: { items: HUB_ITEMS, next_cursor: null, total: 2, fuente: { proveedor: 'docker_hub' } },
  });

  render(<AgregarServicioModal onClose={vi.fn()} onGuardado={vi.fn()} />);

  // Verificar pestañas de origen
  expect(screen.getByRole('button', { name: 'Imagen propia' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Docker Hub' })).toHaveAttribute('aria-pressed', 'false');
  expect(screen.getByLabelText('Imagen Docker')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Docker Hub' }));
  expect(screen.getByText('Encontrar una imagen no garantiza que NAP pueda instalarla.')).toBeVisible();

  // No debe existir preparación, publicación manual ni "Guardadas"
  expect(screen.queryByText(/Guardadas|Preparar|Publicar/)).not.toBeInTheDocument();

  // Buscar por nombre
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'whoami');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));

  expect(api.buscarAplicaciones).toHaveBeenCalledWith(expect.objectContaining({ q: 'whoami' }));
  expect(await screen.findByText('traefik/whoami')).toBeVisible();
  expect(screen.getByText('library/ubuntu')).toBeVisible();
  expect(screen.getByText('Oficial')).toBeVisible();
});

test('selección de resultado precarga formulario OCI común y permite agregar servicio', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockResolvedValue({
    data: { items: HUB_ITEMS, next_cursor: null, total: 2, fuente: { proveedor: 'docker_hub' } },
  });
  api.agregarAplicacionPropia.mockResolvedValue({ data: { id: 10, oferta_disponible: true } });

  const onGuardado = vi.fn();
  render(<AgregarServicioModal onClose={vi.fn()} onGuardado={onGuardado} />);
  await user.click(screen.getByRole('button', { name: 'Docker Hub' }));

  await user.type(screen.getByLabelText('Nombre de aplicación'), 'whoami');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));

  // Seleccionar la aplicación
  await user.click(await screen.findByRole('button', { name: 'Agregar traefik/whoami' }));

  // El formulario precargado debe mostrar la referencia y nombre
  expect(await screen.findByLabelText('Imagen Docker')).toHaveValue('traefik/whoami:latest');
  expect(screen.getByLabelText('Nombre del servicio')).toHaveValue('whoami');

  // Completar el puerto y enviar
  await user.clear(screen.getByLabelText('Puerto de la aplicación'));
  await user.type(screen.getByLabelText('Puerto de la aplicación'), '80');
  await user.click(screen.getByRole('button', { name: 'Agregar al catálogo' }));

  await waitFor(() => {
    expect(api.agregarAplicacionPropia).toHaveBeenCalledWith(
      expect.objectContaining({
        origen: 'imagen_docker',
        nombre: 'whoami',
        imagen: 'traefik/whoami:latest',
        puerto: 80,
      }),
      expect.any(String)
    );
    expect(onGuardado).toHaveBeenCalled();
  });
});

test('fallo de búsqueda ofrece reintento y alternativa de ingresar referencia manual', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockRejectedValue({
    response: { data: { detail: { mensaje: 'No se pudo consultar Docker Hub. Podés reintentar o ingresar la referencia manualmente.' } } },
  });

  render(<AgregarServicioModal onClose={vi.fn()} onGuardado={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Docker Hub' }));

  await user.type(screen.getByLabelText('Nombre de aplicación'), 'whoami');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo consultar Docker Hub');

  // Enlace o botón para ingresar manualmente
  const manualBtn = screen.getByRole('button', { name: /Ingresar referencia manualmente/i });
  expect(manualBtn).toBeVisible();

  // Al hacer clic, pasa al formulario de imagen propia
  await user.click(manualBtn);
  expect(screen.getByLabelText('Imagen Docker')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Imagen propia' })).toHaveAttribute('aria-pressed', 'true');
});

