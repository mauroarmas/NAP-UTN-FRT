import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi, beforeEach, afterEach } from 'vitest';

const estado = vi.hoisted(() => ({ terminales: [], sockets: [] }));

vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    constructor() { this.cols = 80; this.rows = 24; this.escrito = []; this.disposed = false; estado.terminales.push(this); }
    loadAddon() {}
    open() {}
    onData(cb) { this.alTeclear = cb; return { dispose() {} }; }
    write(datos) { this.escrito.push(datos); }
    focus() {}
    dispose() { this.disposed = true; }
  },
}));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }));
vi.mock('@xterm/xterm/css/xterm.css', () => ({}));

import TerminalConsola from '../src/components/TerminalConsola';

class SocketFalso {
  static OPEN = 1;
  constructor(url) { this.url = url; this.readyState = 1; this.enviados = []; this.cerrado = false; estado.sockets.push(this); }
  send(datos) { this.enviados.push(datos); }
  close() { this.cerrado = true; this.readyState = 3; }
  recibir(datos) { this.onmessage({ data: datos }); }
}

beforeEach(() => { estado.terminales.length = 0; estado.sockets.length = 0; vi.stubGlobal('WebSocket', SocketFalso); });
afterEach(() => { vi.unstubAllGlobals(); });

const ultimo = () => estado.sockets[estado.sockets.length - 1];
const texto = (bytes) => new TextDecoder().decode(bytes);

test('se conecta al portal (nunca a la infraestructura) y avisa cuando está abierta', async () => {
  render(<TerminalConsola servicioId={7} onCerrar={() => {}} />);
  expect(ultimo().url).toMatch(/^wss?:\/\/[^/]+\/api\/v1\/servicios\/7\/terminal$/);
  expect(screen.getByRole('status')).toHaveTextContent('Conectando…');
  act(() => ultimo().recibir(JSON.stringify({ t: 'estado', e: 'abierta' })));
  expect(screen.getByRole('status')).toHaveTextContent('Conectada');
  expect(JSON.parse(ultimo().enviados.at(-1))).toEqual({ t: 'resize', cols: 80, rows: 24 });
  expect(screen.getByText(/contraseña de «Revelar acceso inicial»/)).toBeVisible();
});

test('lo que llega del portal se escribe en la terminal y lo que se teclea viaja como bytes', () => {
  render(<TerminalConsola servicioId={7} onCerrar={() => {}} />);
  act(() => ultimo().recibir(new TextEncoder().encode('nap@host:~$ ').buffer));
  expect(texto(estado.terminales[0].escrito[0])).toBe('nap@host:~$ ');
  act(() => estado.terminales[0].alTeclear('ls\r'));
  expect(ArrayBuffer.isView(ultimo().enviados.at(-1))).toBe(true);      // bytes, no texto
  expect(texto(ultimo().enviados.at(-1))).toBe('ls\r');
});

test('un aviso del portal se muestra y desaparece cuando la persona vuelve a escribir', () => {
  render(<TerminalConsola servicioId={7} onCerrar={() => {}} />);
  act(() => ultimo().recibir(JSON.stringify({ t: 'aviso', mensaje: 'La terminal se cerrará en 1 minuto por inactividad.' })));
  expect(screen.getByRole('alert')).toHaveTextContent('se cerrará en 1 minuto');
  act(() => estado.terminales[0].alTeclear('a'));
  expect(screen.queryByRole('alert')).toBeNull();
});

test('el cierre indicado por el portal se muestra en lenguaje llano', () => {
  render(<TerminalConsola servicioId={7} onCerrar={() => {}} />);
  act(() => ultimo().recibir(JSON.stringify({ t: 'estado', e: 'abierta' })));
  act(() => ultimo().recibir(JSON.stringify({ t: 'cierre', motivo: 'retiro', mensaje: 'Se retiró tu acceso a este servicio, por eso se cerró la terminal.' })));
  expect(screen.getByRole('status')).toHaveTextContent('Cerrada');
  expect(screen.getByRole('alert')).toHaveTextContent('Se retiró tu acceso');
  act(() => ultimo().onclose());
  expect(screen.queryByText(/Se perdió la conexión/)).toBeNull();      // el cierre ya explicó el motivo
});

test('si se corta la conexión sin aviso del portal, la persona lo ve', () => {
  render(<TerminalConsola servicioId={7} onCerrar={() => {}} />);
  act(() => ultimo().onclose());
  expect(screen.getByRole('alert')).toHaveTextContent('Se perdió la conexión');
});

test('al cerrar la terminal se avisa al portal, se corta el socket y se libera la terminal', async () => {
  const alCerrar = vi.fn();
  const { unmount } = render(<TerminalConsola servicioId={7} onCerrar={alCerrar} />);
  act(() => ultimo().recibir(JSON.stringify({ t: 'estado', e: 'abierta' })));
  await userEvent.click(screen.getByRole('button', { name: 'Cerrar terminal' }));
  expect(alCerrar).toHaveBeenCalled();
  unmount();
  expect(ultimo().enviados.some((m) => typeof m === 'string' && JSON.parse(m).t === 'cerrar')).toBe(true);
  expect(ultimo().cerrado).toBe(true);
  expect(estado.terminales[0].disposed).toBe(true);
});
