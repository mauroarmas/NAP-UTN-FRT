import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import BibliotecaAplicaciones from '../src/components/BibliotecaAplicaciones';
import * as api from '../src/services/api';

vi.mock('../src/services/api', () => ({
  getCategoriasAplicaciones: vi.fn(),
  buscarAplicaciones: vi.fn(),
}));

const hubItem = {
  nombre: 'whoami',
  repositorio: 'traefik/whoami',
  referencia_sugerida: 'traefik/whoami:latest',
  descripcion: 'Tiny Go webserver that prints OS information and HTTP request to output',
  procedencia: 'comunidad',
  distintivos: ['verificado'],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getCategoriasAplicaciones.mockResolvedValue({
    data: { items: ['Databases', 'Web Servers'], fuente: { estado: 'disponible' } },
  });
});

test('busca por una categoría real y conserva los filtros tras un error de consulta', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones
    .mockResolvedValueOnce({ data: { items: [hubItem], next_cursor: null } })
    .mockRejectedValueOnce(new Error('red'));

  render(<BibliotecaAplicaciones />);
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Categoría' }), 'Databases');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));
  expect(await screen.findByText('whoami')).toBeVisible();
  expect(api.buscarAplicaciones).toHaveBeenCalledWith({ categoria: 'Databases' });

  await user.type(screen.getByLabelText('Nombre de aplicación'), 'postgres');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));
  expect(await screen.findByRole('alert')).toHaveFocus();
  expect(screen.getByLabelText('Categoría')).toHaveValue('Databases');
  expect(screen.getByLabelText('Nombre de aplicación')).toHaveValue('postgres');
});

test('Agregar servicio continúa directamente hacia el formulario sin fichas intermedias', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [hubItem], next_cursor: null } });
  const next = vi.fn();
  const selected = vi.fn();

  render(<BibliotecaAplicaciones onContinue={next} onSelected={selected} />);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'whoami');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));
  await user.click(await screen.findByRole('button', { name: 'Agregar whoami' }));

  expect(selected).toHaveBeenCalledWith(expect.objectContaining({ repositorio: 'traefik/whoami' }));
  expect(next).toHaveBeenCalledWith(expect.objectContaining({ repositorio: 'traefik/whoami' }));
  expect(screen.queryByText('Guardadas')).not.toBeInTheDocument();
});

test('muestra procedencia Oficial o Comunidad sin listar borradores guardados', async () => {
  const user = userEvent.setup();
  const officialItem = {
    nombre: 'nginx',
    repositorio: 'library/nginx',
    referencia_sugerida: 'nginx:latest',
    descripcion: 'Official build of Nginx.',
    procedencia: 'oficial',
    distintivos: ['oficial'],
  };
  api.buscarAplicaciones.mockResolvedValue({
    data: { items: [officialItem, hubItem], next_cursor: null },
  });

  render(<BibliotecaAplicaciones />);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'web');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));

  expect(await screen.findByText('Oficial')).toBeVisible();
  expect(screen.getByText('Comunidad')).toBeVisible();
  expect(screen.queryByText('Guardadas')).not.toBeInTheDocument();
});

test('permite paginar resultados con next_cursor y ofrece entrada manual ante fallo', async () => {
  const user = userEvent.setup();
  const secondItem = {
    nombre: 'redis',
    repositorio: 'library/redis',
    referencia_sugerida: 'redis:latest',
    procedencia: 'oficial',
  };
  api.buscarAplicaciones
    .mockResolvedValueOnce({ data: { items: [hubItem], next_cursor: 'page-2' } })
    .mockResolvedValueOnce({ data: { items: [secondItem], next_cursor: null } });
  const manual = vi.fn();

  render(<BibliotecaAplicaciones onManualEntry={manual} />);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'cache');
  await user.click(screen.getByRole('button', { name: 'Buscar' }));

  expect(await screen.findByText('whoami')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Más resultados' }));
  expect(await screen.findByText('redis')).toBeVisible();
  expect(api.buscarAplicaciones).toHaveBeenLastCalledWith({ q: 'cache', cursor: 'page-2' });
});

test('un fallo de categorías no bloquea la búsqueda por nombre en Docker Hub', async () => {
  const user = userEvent.setup();
  api.getCategoriasAplicaciones.mockRejectedValueOnce(new Error('red'));
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [hubItem], next_cursor: null } });

  render(<BibliotecaAplicaciones />);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'whoami');
  const searchBtn = screen.getByRole('button', { name: 'Buscar' });
  expect(searchBtn).toBeEnabled();
  await user.click(searchBtn);
  await waitFor(() => expect(api.buscarAplicaciones).toHaveBeenCalledWith({ q: 'whoami' }));
  expect(await screen.findByText('whoami')).toBeVisible();
});
