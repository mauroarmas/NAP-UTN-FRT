import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import BibliotecaAplicaciones from '../src/components/BibliotecaAplicaciones';
import * as api from '../src/services/api';
vi.mock('../src/services/api', () => ({ buscarAplicaciones: vi.fn(), incorporarAplicacion: vi.fn(), editarIncorporacion: vi.fn(), listarIncorporaciones: vi.fn() }));

test('busca sólo por categoría y conserva ficha/datos tras error de incorporación', async () => {
  const user=userEvent.setup();
  api.listarIncorporaciones.mockResolvedValue({data:{items:[]}});
  api.buscarAplicaciones.mockResolvedValue({data:{items:[{identidad_externa:'ct/drawio.sh',nombre:'Draw.io',revision_fuente:'a'.repeat(40),comando_origen:'comando informativo',faltantes:['version'],compatibilidad:'adaptador_disponible'}],fuente:{estado:'desactualizada'}}});
  api.incorporarAplicacion.mockRejectedValue(new Error('red'));
  render(<BibliotecaAplicaciones />);
  await user.type(screen.getByLabelText('Categoría de aplicación'),'diagramas');
  await user.click(screen.getByRole('button',{name:'Buscar aplicaciones'}));
  expect(await screen.findByText('Draw.io')).toBeVisible();
  expect(screen.getByText(/desactualizada/i)).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Incorporar Draw.io'}));
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.getByRole('article')).toContainElement(screen.getByRole('alert'));
  expect(screen.getByRole('alert')).toHaveFocus();
  expect(screen.getByLabelText('Categoría de aplicación')).toHaveValue('diagramas');
  await user.click(screen.getByText('Información técnica de origen'));
  expect(screen.getByText('comando informativo')).toBeVisible();
});

test('incorporar muestra espera y lleva el foco a la ficha confirmada', async () => {
  const user=userEvent.setup();
  const source={identidad_externa:'ct/drawio.sh',nombre:'Draw.io',revision_fuente:'a'.repeat(40),compatibilidad:'adaptador_disponible'};
  api.listarIncorporaciones.mockResolvedValue({data:{items:[]}});
  api.buscarAplicaciones.mockResolvedValue({data:{items:[source],fuente:{estado:'disponible'}}});
  let finish;
  api.incorporarAplicacion.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  render(<BibliotecaAplicaciones />);
  await user.type(screen.getByLabelText('Nombre de aplicación'),'drawio');
  await user.click(screen.getByRole('button',{name:'Buscar aplicaciones'}));
  await user.click(await screen.findByRole('button',{name:'Incorporar Draw.io'}));
  expect(screen.getByRole('button',{name:'Incorporando…'})).toBeDisabled();
  await act(async()=>finish({data:{...source,id:'ficha',revision:1,descripcion:''}}));
  expect(screen.getByRole('heading',{name:'Borrador de Draw.io'})).toHaveFocus();
  expect(screen.getByRole('status')).toHaveTextContent('Draw.io se incorporó correctamente');
});
