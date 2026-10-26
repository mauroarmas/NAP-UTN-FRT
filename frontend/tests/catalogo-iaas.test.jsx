import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import Definiciones from '../src/pages/Definiciones';
import Catalogo from '../src/pages/Catalogo';
import * as api from '../src/services/api';
import { sizes } from './fixtures/tamanos';
vi.mock('../src/services/api', async (original) => ({ ...await original(), getTemplates: vi.fn(), sincronizarIaas: vi.fn(), getTamanos: vi.fn() }));
const offers = [['Ubuntu 24.04','iaas'],['Debian 13','iaas'],['Draw.io','saas']].map(([nombre,modelo_servicio],i)=>({id:i+1,nombre,modelo_servicio,tipo:'lxc',activo:true,oferta_disponible:true,tamanos_permitidos:['small','medium']}));
beforeEach(()=>{ api.getTemplates.mockResolvedValue({data:offers}); api.sincronizarIaas.mockResolvedValue({data:{disponibles:2}}); api.getTamanos.mockResolvedValue({data:sizes}); });
test('bases Linux aparecen como servicios solicitables sin otro formulario de preparación',async()=>{
 render(<MemoryRouter><Definiciones user={{rol:'admin'}}/></MemoryRouter>);
 expect(await screen.findByRole('button',{name:'Solicitar Ubuntu 24.04'})).toBeVisible();
 expect(screen.getByRole('button',{name:'Solicitar Debian 13'})).toBeVisible();
 expect(api.sincronizarIaas).toHaveBeenCalledOnce();
 const filter=screen.getByRole('combobox',{name:'Tipo de servicio'});
 expect(within(filter).getAllByRole('option').map(row=>row.textContent)).toEqual(['Todos los tipos','IaaS','PaaS','SaaS']);
 await userEvent.selectOptions(filter,'iaas');
 expect(screen.queryByRole('button',{name:'Solicitar Draw.io'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Solicitar Ubuntu 24.04'})).toBeVisible();
});
test('un fallo de sincronización conserva el catálogo y permite actualizar',async()=>{
 api.sincronizarIaas.mockRejectedValueOnce(new Error('Nodo inaccesible'));
 render(<MemoryRouter><Definiciones user={{rol:'admin'}}/></MemoryRouter>);
 expect(await screen.findByRole('alert')).toBeVisible();
 expect(screen.getByRole('button',{name:'Solicitar Draw.io'})).toBeVisible();
 await userEvent.click(screen.getAllByRole('button',{name:'Actualizar catálogo'})[0]);
 expect(await screen.findByRole('button',{name:'Solicitar Debian 13'})).toBeVisible();
});
test('la cátedra consulta sólo ofertas y no sincroniza infraestructura',async()=>{
 render(<MemoryRouter><Catalogo user={{rol:'catedra_admin'}}/></MemoryRouter>);
 expect(await screen.findByRole('button',{name:'Solicitar Ubuntu 24.04'})).toBeVisible();
 expect(api.sincronizarIaas).not.toHaveBeenCalled();
 for(const name of ['IaaS','PaaS','SaaS']) expect(screen.getByRole('button',{name,exact:true})).toBeVisible();
});
