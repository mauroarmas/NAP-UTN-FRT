import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import AccesoServicio from '../src/components/AccesoServicio';
import * as api from '../src/services/api';
vi.mock('../src/services/api', () => ({ getAccesoServicio: vi.fn(), getConsolaServicio: vi.fn(), revelarAccesoServicio: vi.fn(), verificarAccesoServicio: vi.fn(), abrirAplicacionServicio: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
test('abre Draw.io con la sesión por POST sin mostrar contraseñas ni referencias técnicas', async () => {
  api.getAccesoServicio.mockResolvedValue({data:{producto:'drawio',acceso_con_nap:true,puede_abrir_con_nap:true,instrucciones:'Abrí la aplicación con tu sesión de NAP.'}});
  api.abrirAplicacionServicio.mockResolvedValue({data:{destino:'https://app-18.example.edu/_nap/entrar',codigo:'one-use-private-code'}});
  const submit=vi.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(function(){
    expect(this.method).toBe('post');expect(this.target).toBe('_blank');expect(this.rel).toContain('noopener');
    expect(this.action).toBe('https://app-18.example.edu/_nap/entrar');
    expect(this.elements.namedItem('codigo').value).toBe('one-use-private-code');
  });
  const user=userEvent.setup();render(<AccesoServicio servicio={{id:18}} user={{rol:'catedra_admin'}}/>);
  await user.click(await screen.findByRole('button',{name:'Abrir aplicación'}));
  await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1));
  expect(api.abrirAplicacionServicio).toHaveBeenCalledWith(18);
  expect(screen.queryByText(/BookStack/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Revelar acceso/)).not.toBeInTheDocument();
  expect(document.querySelector('input[name=codigo]')).toBeNull();
  submit.mockRestore();
});
test('un fallo de apertura muestra un mensaje y permite reintentar',async()=>{
  api.getAccesoServicio.mockResolvedValue({data:{producto:'drawio',acceso_con_nap:true,puede_abrir_con_nap:true}});
  api.abrirAplicacionServicio.mockRejectedValue(new Error('fallo'));
  const user=userEvent.setup();render(<AccesoServicio servicio={{id:18}} user={{rol:'catedra_admin'}}/>);
  await user.click(await screen.findByRole('button',{name:'Abrir aplicación'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('No se confirmó');
  expect(screen.getByRole('button',{name:'Abrir aplicación'})).toBeEnabled();
});
test('BookStack conserva su propia orientación y Draw.io nunca la muestra',async()=>{
  api.getAccesoServicio.mockResolvedValue({data:{producto:'bookstack',metodo:'https'}});
  render(<AccesoServicio servicio={{id:19}} user={{rol:'catedra_admin'}}/>);
  expect(await screen.findByText(/El docente administra esta instancia BookStack/)).toBeVisible();
});
