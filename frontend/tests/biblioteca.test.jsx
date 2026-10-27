import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import BibliotecaAplicaciones from '../src/components/BibliotecaAplicaciones';
import * as api from '../src/services/api';
vi.mock('../src/services/api', () => ({ getCategoriasAplicaciones: vi.fn(), buscarAplicaciones: vi.fn(), incorporarAplicacion: vi.fn(), listarIncorporaciones: vi.fn() }));
const source = { identidad_externa: 'ct/drawio.sh', nombre: 'Draw.io', revision_fuente: 'a'.repeat(40), compatibilidad: 'adaptador_disponible' };
beforeEach(() => {
  vi.clearAllMocks();
  api.getCategoriasAplicaciones.mockResolvedValue({ data: { items: ['Databases', 'Document Management'], fuente: { estado: 'disponible' } } });
  api.listarIncorporaciones.mockResolvedValue({ data: { items: [] } });
});

test('busca por una categoría real y conserva los filtros tras un error', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [source], fuente: { estado: 'desactualizada' } } });
  api.incorporarAplicacion.mockRejectedValue(new Error('red'));
  render(<BibliotecaAplicaciones />);
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Categoría de aplicación' }), 'Databases');
  await user.click(screen.getByRole('button', { name: 'Buscar aplicaciones' }));
  expect(await screen.findByText('Draw.io')).toBeVisible();
  expect(api.buscarAplicaciones).toHaveBeenCalledWith({ categoria: 'Databases' });
  expect(screen.getByText(/última copia disponible/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Agregar Draw.io' }));
  expect(await screen.findByRole('alert')).toHaveFocus();
  expect(screen.getByRole('article')).toContainElement(screen.getByRole('alert'));
  expect(screen.getByLabelText('Categoría de aplicación')).toHaveValue('Databases');
});

test('Agregar servicio continúa directamente sin fichas intermedias', async () => {
  const user = userEvent.setup();
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [source], fuente: { estado: 'disponible' } } });
  let finish;
  api.incorporarAplicacion.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const next = vi.fn();
  render(<BibliotecaAplicaciones onContinue={next}/>);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'drawio');
  await user.click(screen.getByRole('button', { name: 'Buscar aplicaciones' }));
  await user.click(await screen.findByRole('button', { name: 'Agregar Draw.io' }));
  expect(screen.getByRole('button', { name: 'Cargando servicio…' })).toBeDisabled();
  await act(async () => finish({ data: { ...source, id: 'ficha', revision: 1 } }));
  expect(next).toHaveBeenCalledWith(expect.objectContaining({ id: 'ficha' }));
  expect(screen.queryByText('Guardadas')).not.toBeInTheDocument();
});

test('una ficha guardada no convierte MariaDB en instalable ni muestra un botón bloqueado', async () => {
  const user = userEvent.setup();
  const maria = { ...source, identidad_externa: 'ct/mariadb.sh', nombre: 'MariaDB', compatibilidad: 'sin_comprobar' };
  api.listarIncorporaciones.mockResolvedValue({ data: { items: [{ ...maria, id: 'guardada' }] } });
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [maria], fuente: { estado: 'disponible' } } });
  const next = vi.fn();
  render(<BibliotecaAplicaciones onContinue={next}/>);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'mariadb');
  await user.click(screen.getByRole('button', { name: 'Buscar aplicaciones' }));
  await user.click(await screen.findByRole('button', { name: 'Ver disponibilidad de MariaDB' }));
  expect(await screen.findByText(/NAP todavía no tiene su instalación automática/)).toBeVisible();
  expect(screen.queryByText('Guardadas')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Agregar/ })).not.toBeInTheDocument();
  expect(api.incorporarAplicacion).not.toHaveBeenCalled();
  expect(next).not.toHaveBeenCalled();
});

test('retoma la misma alta al elegir un resultado sin listar borradores duplicados', async () => {
  const user = userEvent.setup();
  api.listarIncorporaciones.mockResolvedValue({ data: { items: [{ ...source, id: 'existente' }] } });
  api.buscarAplicaciones.mockResolvedValue({ data: { items: [source], fuente: { estado: 'disponible' } } });
  const next = vi.fn();
  render(<BibliotecaAplicaciones onContinue={next}/>);
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'drawio');
  await user.click(screen.getByRole('button', { name: 'Buscar aplicaciones' }));
  await user.click(await screen.findByRole('button', { name: 'Agregar Draw.io' }));
  await waitFor(() => expect(next).toHaveBeenCalledWith(expect.objectContaining({ id: 'existente' })));
  expect(api.incorporarAplicacion).not.toHaveBeenCalled();
});

test('un fallo de categorías permite buscar por nombre y reintentar la carga', async () => {
  const user = userEvent.setup();
  api.getCategoriasAplicaciones.mockRejectedValueOnce(new Error('red'));
  render(<BibliotecaAplicaciones/>);
  expect(await screen.findByText(/No se pudieron cargar las categorías/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(await screen.findByRole('option', { name: 'Databases' })).toBeInTheDocument();
  await user.type(screen.getByLabelText('Nombre de aplicación'), 'drawio');
  expect(screen.getByRole('button', { name: 'Buscar aplicaciones' })).toBeEnabled();
});
