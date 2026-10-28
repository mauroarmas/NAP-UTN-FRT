import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, test } from 'vitest';
import ProgresoDespliegue from '../src/components/ProgresoDespliegue';
const pedido = { id: 33, tipo: 'alta', estado: 'en_despliegue', operation_id: 'operation' };
const view = (props) => <MemoryRouter><ProgresoDespliegue pedido={pedido} {...props}/></MemoryRouter>;

test('avanza por fases reales sin estimar el tiempo ni anunciar entrega antes de tiempo', () => {
  const { rerender } = render(view({ operacion: { estado: 'en_curso', fase: 'tarea' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
  expect(screen.getByText('Creando la instancia…')).toBeVisible();
  rerender(view({ operacion: { estado: 'en_curso', fase: 'bootstrap' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');
  expect(screen.getByText('Iniciando la aplicación…')).toBeVisible();
  rerender(view({ operacion: { estado: 'confirmada', fase: 'verificacion' }, isAdmin: true }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
  expect(screen.getByText('Servicio iniciado · acceso pendiente')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Revisar servicio' })).toHaveAttribute('href', '/servicios');
  expect(screen.queryByText('Servicio disponible')).not.toBeInTheDocument();
});
test('al recargar conserva el acceso pendiente aunque no haya operación abierta', () => {
  render(view({ pedido: { ...pedido, operation_id: null, servicio_id: 18 } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
  expect(screen.getByText(/Administración debe completar/)).toBeVisible();
});
test('una consulta fallida conserva la última fase y muestra incertidumbre', () => {
  render(view({ operacion: { estado: 'en_curso', fase: 'bootstrap', error_consulta: true } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');
  expect(screen.getByText('No se pudo actualizar el avance')).toBeVisible();
  expect(screen.queryByText('Servicio disponible')).not.toBeInTheDocument();
});
test('sólo un pedido activo completa las cuatro etapas', () => {
  render(view({ pedido: { ...pedido, estado: 'activo' }, operacion: { estado: 'confirmada' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');
  expect(screen.getByText('Servicio disponible')).toBeVisible();
});
test('un fallo se anuncia sin mantener una animación de trabajo', () => {
  const { container } = render(view({ pedido: { ...pedido, estado: 'error' }, operacion: { estado: 'fallida', fase: 'tarea' } }));
  expect(screen.getByText('El despliegue necesita revisión')).toBeVisible();
  expect(container.querySelector('.library-spinner')).toBeNull();
});

test('avanza por las fases de despliegue OCI (creacion, instalacion, comprobacion)', () => {
  const { rerender } = render(view({ operacion: { estado: 'en_curso', fase: 'creacion' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
  expect(screen.getByText('Creando la instancia…')).toBeVisible();

  rerender(view({ operacion: { estado: 'en_curso', fase: 'instalacion' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');
  expect(screen.getByText('Iniciando la aplicación…')).toBeVisible();

  rerender(view({ operacion: { estado: 'en_curso', fase: 'comprobacion' } }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');
});

