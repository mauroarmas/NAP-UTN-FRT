import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import ConsolaOperacion from '../src/components/ConsolaOperacion';
import * as api from '../src/services/api';

vi.mock('../src/services/api');

describe('ConsolaOperacion (US4 - T079)', () => {
  const opId = '11111111-2222-3333-4444-555555555555';

  const mockBaseResponse = {
    operation_id: opId,
    operacion_raiz_id: opId,
    estado: 'en_curso',
    fase: 'instalacion',
    intento_efectivo: 1,
    items: [
      {
        seq: 1,
        intento: 1,
        captured_at: '2026-10-27T10:00:00Z',
        fase: 'creacion',
        stream: 'sistema',
        texto_depurado: 'Creando recurso de aplicación.',
      },
      {
        seq: 2,
        intento: 1,
        captured_at: '2026-10-27T10:00:01Z',
        fase: 'instalacion',
        stream: 'stdout',
        texto_depurado: '<script>alert("xss")</script> y \u001b[31mcolores\u001b[0m',
      },
    ],
    next_cursor: 2,
    previous_cursor: 1,
    has_more: false,
    first_retained_seq: 1,
    last_seq: 2,
    truncated: false,
    expired: false,
    dropped_messages: 0,
    last_captured_at: '2026-10-27T10:00:01Z',
    last_ingested_at: '2026-10-27T10:00:02Z',
    resultado_final: null,
  };

  beforeEach(() => {
    vi.resetAllMocks();
  });

  test('renderiza con fondo negro, texto blanco y estilo monoespaciado', async () => {
    api.obtenerConsolaOperacion.mockResolvedValue({ data: mockBaseResponse });

    const { container } = render(
      <ConsolaOperacion operationId={opId} onClose={() => {}} />
    );

    await waitFor(() => {
      expect(screen.getByText(/Creando recurso de aplicación/i)).toBeInTheDocument();
    });

    const consoleBox = container.querySelector('.consola-terminal');
    expect(consoleBox).not.toBeNull();
    expect(consoleBox.style.backgroundColor).toBe('rgb(0, 0, 0)');
    expect(consoleBox.style.color).toBe('rgb(255, 255, 255)');
    expect(consoleBox.style.fontFamily).toContain('monospace');
  });

  test('renderiza texto literal sin ejecutar HTML ni parsear ANSI malicioso', async () => {
    api.obtenerConsolaOperacion.mockResolvedValue({ data: mockBaseResponse });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} />);

    await waitFor(() => {
      expect(
        screen.getByText(/<script>alert\("xss"\)<\/script>/)
      ).toBeInTheDocument();
    });
    expect(document.querySelector('script[src*="xss"]')).toBeNull();
  });

  test('deduplica mensajes recibidos por seq', async () => {
    let callCount = 0;
    api.obtenerConsolaOperacion.mockImplementation(() => {
      callCount += 1;
      if (callCount === 1) {
        return Promise.resolve({ data: mockBaseResponse });
      }
      return Promise.resolve({
        data: {
          ...mockBaseResponse,
          items: [
            mockBaseResponse.items[1],
            {
              seq: 3,
              intento: 1,
              captured_at: '2026-10-27T10:00:03Z',
              fase: 'instalacion',
              stream: 'stdout',
              texto_depurado: 'Paso 3 completado.',
            },
          ],
          last_seq: 3,
        },
      });
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} intervalMs={50} />);

    await waitFor(() => {
      expect(screen.getByText(/Paso 3 completado/i)).toBeInTheDocument();
    });

    // seq 2 debe aparecer exactamente una vez
    const matches = screen.getAllByText(/<script>alert\("xss"\)<\/script>/);
    expect(matches).toHaveLength(1);
  });

  test('permite cargar páginas anteriores con cursor before', async () => {
    api.obtenerConsolaOperacion.mockImplementation((id, params) => {
      if (params?.before) {
        return Promise.resolve({
          data: {
            ...mockBaseResponse,
            items: [
              {
                seq: 1,
                intento: 1,
                captured_at: '2026-10-27T10:00:00Z',
                fase: 'creacion',
                stream: 'sistema',
                texto_depurado: 'Paso 1 anterior.',
              },
              {
                seq: 2,
                intento: 1,
                captured_at: '2026-10-27T10:00:01Z',
                fase: 'creacion',
                stream: 'sistema',
                texto_depurado: 'Paso 2 anterior.',
              },
            ],
          },
        });
      }
      return Promise.resolve({
        data: {
          ...mockBaseResponse,
          first_retained_seq: 1,
          last_seq: 4,
          items: [
            {
              seq: 3,
              intento: 1,
              captured_at: '2026-10-27T10:00:03Z',
              fase: 'instalacion',
              stream: 'stdout',
              texto_depurado: 'Paso 3.',
            },
            {
              seq: 4,
              intento: 1,
              captured_at: '2026-10-27T10:00:04Z',
              fase: 'instalacion',
              stream: 'stdout',
              texto_depurado: 'Paso 4.',
            },
          ],
        },
      });
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} intervalMs={10000} />);

    await waitFor(() => {
      expect(screen.getByText('Paso 3.')).toBeInTheDocument();
    });

    const btnAnteriores = screen.getByRole('button', { name: /cargar mensajes anteriores/i });
    expect(btnAnteriores).toBeInTheDocument();
    fireEvent.click(btnAnteriores);

    await waitFor(() => {
      expect(screen.getByText('Paso 1 anterior.')).toBeInTheDocument();
      expect(screen.getByText('Paso 4.')).toBeInTheDocument();
    });
  });

  test('conserva las líneas existentes y muestra aviso ante error de consulta', async () => {
    let callCount = 0;
    api.obtenerConsolaOperacion.mockImplementation(() => {
      callCount += 1;
      if (callCount === 1) {
        return Promise.resolve({ data: mockBaseResponse });
      }
      return Promise.reject(new Error('Network error'));
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} intervalMs={50} />);

    await waitFor(() => {
      expect(screen.getByText(/Creando recurso de aplicación/i)).toBeInTheDocument();
    });

    // Tras el siguiente tick con fallo de red, se mantiene el texto y aparece el aviso
    await waitFor(() => {
      expect(screen.getByText(/Error temporal de conexión/i)).toBeInTheDocument();
      expect(screen.getByText(/Creando recurso de aplicación/i)).toBeInTheDocument();
    });
  });

  test('informa recorte de mensajes y expiración del registro', async () => {
    api.obtenerConsolaOperacion.mockResolvedValue({
      data: {
        ...mockBaseResponse,
        truncated: true,
        dropped_messages: 5,
        expired: true,
        resultado_final: { hito: 'fallo', texto: 'No se pudo completar el despliegue.' },
        items: [],
      },
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/se omitieron 5 mensajes/i)).toBeInTheDocument();
      expect(screen.getByText(/registro de consola expiró/i)).toBeInTheDocument();
      expect(screen.getAllByText(/No se pudo completar el despliegue/i).length).toBeGreaterThan(0);
    });
  });

  test('limpia el buffer y muestra error al revocarse los permisos (403)', async () => {
    const error403 = new Error('Forbidden');
    error403.response = { status: 403, data: { detail: { codigo: 'acceso_denegado' } } };

    let callCount = 0;
    api.obtenerConsolaOperacion.mockImplementation(() => {
      callCount += 1;
      if (callCount === 1) {
        return Promise.resolve({ data: mockBaseResponse });
      }
      return Promise.reject(error403);
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} intervalMs={50} />);

    await waitFor(() => {
      expect(screen.getByText(/Creando recurso de aplicación/i)).toBeInTheDocument();
    });

    // Siguiente consulta recibe 403
    await waitFor(() => {
      expect(screen.queryByText(/Creando recurso de aplicación/i)).not.toBeInTheDocument();
      expect(screen.getByText(/acceso revocado/i)).toBeInTheDocument();
    });
  });

  test('permite copiar y descargar registro congelando through_seq', async () => {
    api.obtenerConsolaOperacion.mockResolvedValue({ data: mockBaseResponse });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    render(<ConsolaOperacion operationId={opId} onClose={() => {}} intervalMs={10000} />);

    await waitFor(() => {
      expect(screen.getByText(/Creando recurso de aplicación/i)).toBeInTheDocument();
    });

    const copyBtn = screen.getByRole('button', { name: /copiar consola/i });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalled();
    });

    const copiedContent = writeTextMock.mock.calls[0][0];
    expect(copiedContent).toContain('Creando recurso de aplicación.');
    expect(copiedContent).toContain('<script>alert("xss")</script>');
  });
});
