import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ProgresoDespliegue from '../src/components/ProgresoDespliegue';
import { DetalleDialog } from '../src/pages/Pedidos';
import Servicios from '../src/pages/Servicios';
import * as api from '../src/services/api';
import { textoOperacion, operacionAbierta } from '../src/hooks/useOperacion';

vi.mock('../src/services/api', () => ({
  listarServicios: vi.fn(),
  listarOperaciones: vi.fn(),
  getStatusServicio: vi.fn(),
  iniciarServicio: vi.fn(),
  detenerServicio: vi.fn(),
  reiniciarServicio: vi.fn(),
  eliminarServicio: vi.fn(),
  getCatedras: vi.fn(),
  getCatedrasMias: vi.fn(),
  getPedidos: vi.fn(),
  obtenerOperacion: vi.fn(),
  reintentarPedido: vi.fn(),
  desplegarPedido: vi.fn(),
  obtenerConsolaOperacion: vi.fn(),
  obtenerAccesoServicio: vi.fn(),
  getTemplates: vi.fn(),
  getTamanos: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  api.listarServicios.mockResolvedValue({ data: [] });
  api.listarOperaciones.mockResolvedValue({ data: [] });
  api.getCatedras.mockResolvedValue({ data: [] });
  api.getCatedrasMias.mockResolvedValue({ data: [] });
  api.getPedidos.mockResolvedValue({ data: [] });
  api.getTemplates.mockResolvedValue({ data: [] });
  api.obtenerOperacion.mockResolvedValue({ data: { id: 'op-1', estado: 'confirmada' } });
});

test('fallo confirmado muestra botón Reintentar en el detalle del pedido', () => {
  const onReintentar = vi.fn();
  const pedido = {
    id: 10,
    estado: 'error',
    tipo: 'alta',
    servicio_solicitado: 'Draw.io',
    catedra_nombre: 'Algoritmos',
    created_at: '2026-10-28T09:00:00Z',
    despliegue_habilitado: true,
  };

  render(
    <MemoryRouter>
      <DetalleDialog
        detalle={pedido}
        onClose={vi.fn()}
        onReintentar={onReintentar}
        isAdmin={true}
        motivoRechazo=""
        setMotivoRechazo={vi.fn()}
        templateDe={() => ({ nombre: 'Draw.io' })}
        templateNombre={() => 'Draw.io'}
        catedraNombre={() => 'Algoritmos'}
        formatDate={(d) => d}
      />
    </MemoryRouter>
  );

  const botonReintentar = screen.getByRole('button', { name: /Reintentar despliegue/i });
  expect(botonReintentar).toBeVisible();
  expect(botonReintentar).not.toBeDisabled();
});

test('estado incierto no muestra Reintentar masivo y visibiliza estado de verificación', () => {
  const pedido = {
    id: 12,
    estado: 'en_despliegue',
    tipo: 'alta',
    servicio_solicitado: 'Jupyter',
  };
  const operacion = {
    operation_id: 'op-incierta-1',
    estado: 'incierta',
    fase: 'tarea',
  };

  // En ProgresoDespliegue
  render(
    <MemoryRouter>
      <ProgresoDespliegue pedido={pedido} operacion={operacion} isAdmin={true} />
    </MemoryRouter>
  );

  expect(screen.getByText('Comprobando el estado de la instancia')).toBeVisible();
  expect(screen.getByText(/NAP está verificando el resultado\. No hace falta volver a pedir el despliegue\./i)).toBeVisible();

  // En DetalleDialog con estado incierto no debe mostrar botón Reintentar
  const { unmount } = render(
    <MemoryRouter>
      <DetalleDialog
        detalle={pedido}
        operacion={operacion}
        onClose={vi.fn()}
        onReintentar={vi.fn()}
        isAdmin={true}
        motivoRechazo=""
        setMotivoRechazo={vi.fn()}
        templateDe={() => ({ nombre: 'Jupyter' })}
        templateNombre={() => 'Jupyter'}
        catedraNombre={() => 'Redes'}
        formatDate={(d) => d}
      />
    </MemoryRouter>
  );

  expect(screen.queryByRole('button', { name: /Reintentar despliegue/i })).not.toBeInTheDocument();
  unmount();
});

test('limpieza pendiente y textoOperacion visible cuando falla la eliminación', () => {
  const opEliminarIncierta = {
    tipo: 'eliminar',
    estado: 'incierta',
  };
  const opEliminarFallida = {
    tipo: 'eliminar',
    estado: 'fallida',
  };

  expect(textoOperacion(opEliminarIncierta)).toBe('Resultado incierto. Estamos comprobando el recurso.');
  expect(textoOperacion(opEliminarFallida)).toBe('Operación fallida. Revisá el diagnóstico antes de reintentar.');
  expect(operacionAbierta(opEliminarIncierta)).toBe(true);
  expect(operacionAbierta(opEliminarFallida)).toBe(false);
});

test('confirmación destructiva requerida antes de solicitar baja de servicio', async () => {
  const user = userEvent.setup();
  const confirmSpy = vi.spyOn(window, 'confirm');

  const servicio = {
    id: 101,
    nombre_snapshot: 'Draw.io Lab',
    estado: 'running',
    disponibilidad_aplicacion: 'utilizable',
    catedra_id: 1,
    catedra_nombre: 'Sistemas',
    proxmox_vmid: 105,
    tipo: 'lxc',
    existe_en_proxmox: true,
    acciones_habilitadas: ['delete', 'stop', 'restart'],
  };

  api.listarServicios.mockResolvedValue({ data: [servicio] });
  api.eliminarServicio.mockResolvedValue({ status: 202, data: { operacion_id: 'op-del' } });

  render(
    <MemoryRouter>
      <Servicios user={{ rol: 'admin' }} />
    </MemoryRouter>
  );

  const botonOpciones = await screen.findByTitle('Opciones del servicio');
  await user.click(botonOpciones);

  const botonBaja = await screen.findByRole('button', { name: /Dar de baja/i });
  expect(botonBaja).toBeVisible();

  // 1. Cancelar la confirmación
  confirmSpy.mockReturnValueOnce(false);
  await user.click(botonBaja);

  expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('¿Dar de baja el servicio y eliminar el contenedor 105 en Proxmox?'));
  expect(api.eliminarServicio).not.toHaveBeenCalled();

  // 2. Reabrir menú y aceptar la confirmación
  await user.click(botonOpciones);
  const botonBaja2 = await screen.findByRole('button', { name: /Dar de baja/i });
  confirmSpy.mockReturnValueOnce(true);
  await user.click(botonBaja2);

  expect(confirmSpy).toHaveBeenCalledTimes(2);
  await waitFor(() => {
    expect(api.eliminarServicio).toHaveBeenCalledWith(101, expect.any(String));
  });

  confirmSpy.mockRestore();
});

test('polling de estado no dispara reinstalación ni duplicación de vistas', async () => {
  const servicio = {
    id: 202,
    nombre_snapshot: 'App Test',
    estado: 'running',
    disponibilidad_aplicacion: 'utilizable',
    catedra_id: 1,
    operation_id: 'op-poll-1',
    proxmox_vmid: 110,
    tipo: 'lxc',
  };

  api.listarServicios.mockResolvedValue({ data: [servicio] });
  api.listarOperaciones.mockResolvedValue({
    data: [
      {
        operation_id: 'op-poll-1',
        servicio_id: 202,
        estado: 'en_curso',
        fase: 'tarea',
      },
    ],
  });
  api.obtenerOperacion.mockResolvedValue({
    data: {
      operation_id: 'op-poll-1',
      servicio_id: 202,
      estado: 'en_curso',
      fase: 'tarea',
    },
  });

  render(
    <MemoryRouter>
      <Servicios user={{ rol: 'admin' }} />
    </MemoryRouter>
  );

  // Esperar a que se renderice el servicio
  expect(await screen.findByText('App Test')).toBeVisible();

  // Comprobar que obtenerOperacion se llamó para consultar el estado
  await waitFor(() => {
    expect(api.obtenerOperacion).toHaveBeenCalledWith('op-poll-1', expect.any(Object));
  });

  // Asegurar que no se llamó a endpoints de mutación (desplegar, reintentar, iniciar)
  expect(api.desplegarPedido).not.toHaveBeenCalled();
  expect(api.reintentarPedido).not.toHaveBeenCalled();
  expect(api.iniciarServicio).not.toHaveBeenCalled();
});
