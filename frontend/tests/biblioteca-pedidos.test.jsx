import { render,screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { test,expect,vi } from 'vitest';
import Catalogo from '../src/pages/Catalogo';
import * as api from '../src/services/api';
vi.mock('../src/services/api',()=>({getTemplates:vi.fn(),getCatedras:vi.fn(),getCatedrasMias:vi.fn(),getCalendario:vi.fn(),createPedido:vi.fn()}));

test('catálogo muestra versión y conserva oferta al solicitar sin hardware',async()=>{
  api.getTemplates.mockResolvedValue({data:[{id:4,nombre:'Draw.io',modelo_servicio:'saas',tipo:'lxc',activo:true,oferta_disponible:true,origen_biblioteca:true,version_ofrecida:'2.0.0',revision:2}]});
  api.getCatedrasMias.mockResolvedValue({data:[{id:1,nombre:'Propia'}]});
  api.getCalendario.mockResolvedValue({data:{anio:2026,periodos:[]}});
  const user=userEvent.setup();
  render(<MemoryRouter><Catalogo user={{rol:'catedra_admin'}}/></MemoryRouter>);
  expect(await screen.findByText('Versión ofrecida: 2.0.0')).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Solicitar Draw.io'}));
  expect(await screen.findByLabelText('Servicio',{exact:true})).toHaveValue('4');
  expect(screen.queryByLabelText('vCPU')).not.toBeInTheDocument();
});
