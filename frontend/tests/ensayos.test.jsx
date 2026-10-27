import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import EnsayoPreparacion from '../src/components/EnsayoPreparacion';
import * as api from '../src/services/api';
vi.mock('../src/services/api',()=>({consultarPreparacion:vi.fn(),agregarAplicacion:vi.fn(),eliminarPreparacion:vi.fn()}));
const app={id:'inc',nombre:'Draw.io'};
const idle={estado:'sin_preparar',puede_preparar:true,mensaje:'',preparacion_id:null};
beforeEach(()=>{vi.clearAllMocks();api.consultarPreparacion.mockResolvedValue({data:idle});});

test('sin conexión informa qué falta sin pedir códigos, plazos ni entorno',async()=>{
  api.consultarPreparacion.mockResolvedValue({data:{...idle,puede_preparar:false,mensaje:'Falta completar la conexión con Proxmox.'}});
  render(<EnsayoPreparacion incorporacion={app}/>);
  expect(await screen.findByText('Falta completar la conexión con Proxmox.')).toBeVisible();
  expect(screen.getByRole('button',{name:'Agregar al catálogo'})).toBeDisabled();
  expect(screen.queryByLabelText(/Entorno|Versión|SHA|UUID|horas/)).not.toBeInTheDocument();
});

test('agregar conserva los datos ante error y reintenta la misma intención',async()=>{
  const user=userEvent.setup();api.agregarAplicacion.mockRejectedValue(new Error('red'));
  render(<EnsayoPreparacion incorporacion={app}/>);
  await user.clear(await screen.findByLabelText('Nombre del servicio'));await user.type(screen.getByLabelText('Nombre del servicio'),'Diagramas');
  await user.click(screen.getByRole('button',{name:'Agregar al catálogo'}));
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.getByLabelText('Nombre del servicio')).toHaveValue('Diagramas');
  api.agregarAplicacion.mockResolvedValue({data:{...idle,alta_automatica:true,estado:'preparando',preparacion_id:'preparacion'}});
  await user.click(screen.getByRole('button',{name:'Agregar al catálogo'}));
  expect(api.agregarAplicacion.mock.calls[0]).toEqual(api.agregarAplicacion.mock.calls[1]);
  expect(await screen.findByText('Agregando servicio…')).toBeVisible();
  expect(screen.queryByRole('button',{name:/Preparar|Publicar|Funciona correctamente/})).not.toBeInTheDocument();
});

test('retoma un alta anterior comprobada sin pedir otra prueba ni publicación',async()=>{
  api.consultarPreparacion.mockResolvedValue({data:{...idle,estado:'lista_para_publicar',preparacion_id:'anterior'}});
  api.agregarAplicacion.mockResolvedValue({data:{estado:'publicada'}});
  render(<EnsayoPreparacion incorporacion={app}/>);
  await userEvent.click(await screen.findByRole('button',{name:'Agregar al catálogo'}));
  expect(api.agregarAplicacion).toHaveBeenCalledWith('inc',{nombre:'Draw.io',descripcion:'',tamano:'small'},expect.any(String));
  expect(await screen.findByRole('heading',{name:'Servicio disponible'})).toBeVisible();
});

test('se puede cancelar el alta que sigue en segundo plano',async()=>{
  api.consultarPreparacion.mockResolvedValue({data:{...idle,alta_automatica:true,estado:'preparando',preparacion_id:'alta'}});
  api.eliminarPreparacion.mockResolvedValue({data:{estado:'eliminando'}});
  render(<EnsayoPreparacion incorporacion={app}/>);
  await userEvent.click(await screen.findByRole('button',{name:'Cancelar alta'}));
  expect(api.eliminarPreparacion).toHaveBeenCalledWith('inc',expect.any(String));
  expect(await screen.findByText('Eliminando…')).toBeVisible();
});
