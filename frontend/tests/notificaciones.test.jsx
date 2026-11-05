import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import Notificaciones from '../src/components/Notificaciones';
import * as api from '../src/services/api';
vi.mock('../src/services/api', () => ({ getAvisos: vi.fn() }));
const rows = [
 { id: 'aviso-33', pedido_id: 33, asunto: 'Pedido #33: servicio iniciado', texto: 'Falta verificar el acceso.', created_at: '2026-10-26T15:00:00Z' },
 { id: 'aviso-34', pedido_id: 34, asunto: 'Pedido #34 aprobado', texto: 'Los recursos quedaron reservados.', created_at: '2026-10-26T14:00:00Z' },
];
beforeEach(() => { api.getAvisos.mockResolvedValue({ data: rows }); });
function Location() { const location = useLocation(); return <output aria-label="Destino">{location.pathname}{location.search}</output>; }
function view(user = { id: 1, rol: 'admin' }) { return <MemoryRouter><Notificaciones key={user.id} user={user}/><Location/></MemoryRouter>; }

test('muestra avisos, abre el pedido y marca sólo el aviso visitado', async () => {
 const user = userEvent.setup();
 render(view());
 await user.click(await screen.findByRole('button', { name: 'Notificaciones (2 nuevas)' }));
 await user.click(await screen.findByRole('button', { name: /Pedido #33: servicio iniciado/ }));
 expect(screen.getByLabelText('Destino')).toHaveTextContent('/pedidos?pedido=33');
 expect(screen.getByRole('button', { name: 'Notificaciones (1 nuevas)' })).toBeVisible();
 expect(JSON.parse(localStorage.getItem('nap:avisos-vistos:1'))).toEqual(['aviso-33']);
});
test('marcar todo respeta el usuario de la sesión', async () => {
 const user = userEvent.setup();
 const { rerender } = render(view());
 await user.click(await screen.findByRole('button', { name: 'Notificaciones (2 nuevas)' }));
 await user.click(await screen.findByRole('button', { name: 'Marcar como leídas' }));
 expect(screen.getByText('Estás al día')).toBeVisible();
 rerender(view({ id: 2, rol: 'catedra_admin' }));
 expect(await screen.findByRole('button', { name: 'Notificaciones (2 nuevas)' })).toBeVisible();
 expect(localStorage.getItem('nap:avisos-vistos:2')).toBeNull();
});
test('un error de consulta no se presenta como bandeja vacía', async () => {
 api.getAvisos.mockRejectedValue(new Error('Consulta fallida'));
 render(view());
 await userEvent.click(screen.getByRole('button', { name: 'Notificaciones' }));
 expect(await screen.findByRole('alert')).toBeVisible();
 expect(screen.queryByText('No tenés notificaciones por ahora.')).not.toBeInTheDocument();
});
