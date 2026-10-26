import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import EnsayoPreparacion from '../src/components/EnsayoPreparacion';
import * as api from '../src/services/api';
import { sizes } from './fixtures/tamanos';
vi.mock('../src/services/api',()=>({consultarPreparacion:vi.fn(),prepararAplicacion:vi.fn(),confirmarFuncionamiento:vi.fn(),publicarAplicacion:vi.fn(),eliminarPreparacion:vi.fn(),revelarAccesoEnsayo:vi.fn(),getTamanos:vi.fn()}));
const app={id:'inc',nombre:'Draw.io',compatibilidad:'adaptador_disponible'};
const idle={estado:'sin_preparar',puede_preparar:true,mensaje:'',preparacion_id:null,minimum_resources:null,recursos:[]};
beforeEach(()=>{vi.clearAllMocks();api.getTamanos.mockResolvedValue({data:sizes});api.consultarPreparacion.mockResolvedValue({data:idle});});

test('sin conexión informa qué falta sin pedir códigos, plazos ni entorno',async()=>{
  api.consultarPreparacion.mockResolvedValue({data:{...idle,puede_preparar:false,mensaje:'Falta completar la conexión con Proxmox.'}});
  render(<EnsayoPreparacion incorporacion={app}/>);
  expect(await screen.findByText('Falta completar la conexión con Proxmox.')).toBeVisible();
  expect(screen.getByRole('button',{name:'Preparar aplicación'})).toBeDisabled();
  expect(screen.queryByLabelText(/Entorno|Versión|SHA|UUID|horas/)).not.toBeInTheDocument();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
});

test('preparar conserva nombre ante error y reintenta con la misma clave, sin plazo',async()=>{
  const user=userEvent.setup();api.prepararAplicacion.mockRejectedValue(new Error('red'));
  render(<EnsayoPreparacion incorporacion={app}/>);
  await user.clear(await screen.findByLabelText('Nombre del servicio'));await user.type(screen.getByLabelText('Nombre del servicio'),'Diagramas');
  await user.click(screen.getByRole('button',{name:'Preparar aplicación'}));
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.getByLabelText('Nombre del servicio')).toHaveValue('Diagramas');
  api.prepararAplicacion.mockResolvedValue({data:{...idle,estado:'preparando',preparacion_id:'preparacion'}});
  await user.click(screen.getByRole('button',{name:'Preparar aplicación'}));
  expect(api.prepararAplicacion.mock.calls[0]).toEqual(api.prepararAplicacion.mock.calls[1]);
  expect(await screen.findByText('Preparando aplicación…')).toBeVisible();
  expect(screen.queryByText(/Vence:|24 horas|Vencimiento/)).not.toBeInTheDocument();
});

test('no funciona elimina la preparación sin pedir datos técnicos',async()=>{
  const user=userEvent.setup();
  api.consultarPreparacion.mockResolvedValue({data:{...idle,estado:'lista_para_probar',preparacion_id:'preparacion',recursos:[{id:'recurso'}]}});
  api.confirmarFuncionamiento.mockResolvedValue({data:{...idle,estado:'eliminando',preparacion_id:'preparacion'}});
  render(<EnsayoPreparacion incorporacion={app}/>);
  await user.click(await screen.findByRole('button',{name:'No funciona, eliminar'}));
  expect(api.confirmarFuncionamiento).toHaveBeenCalledWith('inc',false,expect.any(String));
  expect(await screen.findByText('Eliminando preparación…')).toBeVisible();
});

test('publicar usa nombre y tamaño sin exigir evidencia ni una validación separada',async()=>{
  const user=userEvent.setup();const published=vi.fn();
  api.consultarPreparacion.mockResolvedValue({data:{...idle,estado:'lista_para_publicar',preparacion_id:'preparacion',minimum_resources:{vcpus:1,ram_mb:512,disk_gb:4}}});
  api.publicarAplicacion.mockResolvedValue({data:{estado:'publicada'}});
  render(<EnsayoPreparacion incorporacion={app} onPublished={published}/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Publicar servicio'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Publicar servicio'}));
  expect(api.publicarAplicacion).toHaveBeenCalledWith('inc',{nombre:'Draw.io',descripcion:'',tamano:'small'},expect.any(String));
  expect(published).toHaveBeenCalledOnce();
});
