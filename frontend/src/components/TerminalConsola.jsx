import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

const CODIGO_ABIERTA = 'abierta';

function urlTerminal(servicioId) {
  const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocolo}://${window.location.host}/api/v1/servicios/${servicioId}/terminal`;
}

/**
 * Terminal de la consola dentro del portal. No guarda ni registra lo que se escribe o se ve.
 * Todo el estado de la sesión lo manda el portal (abierta / aviso / cierre); la persona nunca ve la infraestructura.
 */
export default function TerminalConsola({ servicioId, onCerrar }) {
  const contenedor = useRef(null);
  const [estado, setEstado] = useState('conectando');
  const [aviso, setAviso] = useState('');
  const [cierre, setCierre] = useState('');

  useEffect(() => {
    const term = new Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      convertEol: false, scrollback: 2000, theme: { background: '#0b0d12' } });
    const ajuste = new FitAddon();
    term.loadAddon(ajuste);
    term.open(contenedor.current);
    let cerrada = false;
    const ws = new WebSocket(urlTerminal(servicioId));
    ws.binaryType = 'arraybuffer';
    const enviarTamano = () => {
      try { ajuste.fit(); } catch { /* el contenedor aún no tiene tamaño */ }
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: 'resize', cols: term.cols, rows: term.rows }));
    };
    ws.onmessage = (evento) => {
      if (typeof evento.data === 'string') {
        let mensaje;
        try { mensaje = JSON.parse(evento.data); } catch { return; }
        if (mensaje.t === 'estado' && mensaje.e === CODIGO_ABIERTA) { setEstado('abierta'); enviarTamano(); term.focus(); }
        else if (mensaje.t === 'aviso') setAviso(mensaje.mensaje || '');
        else if (mensaje.t === 'cierre') { cerrada = true; setEstado('cerrada'); setCierre(mensaje.mensaje || 'La terminal se cerró.'); setAviso(''); }
        return;
      }
      term.write(new Uint8Array(evento.data));
    };
    ws.onclose = () => {
      if (!cerrada) { cerrada = true; setEstado('cerrada'); setCierre('Se perdió la conexión con el servicio. Podés abrir otra terminal.'); }
    };
    ws.onerror = () => { /* el cierre informa el resultado */ };
    const teclas = term.onData((datos) => { if (ws.readyState === WebSocket.OPEN) { setAviso(''); ws.send(new TextEncoder().encode(datos)); } });
    const observador = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(enviarTamano) : null;
    observador?.observe(contenedor.current);
    window.addEventListener('resize', enviarTamano);
    return () => {
      window.removeEventListener('resize', enviarTamano);
      observador?.disconnect();
      teclas.dispose();
      cerrada = true;
      try { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: 'cerrar' })); ws.close(); } catch { /* ya cerrada */ }
      term.dispose();
    };
  }, [servicioId]);

  return <section aria-label="Terminal del servicio" className="stack gap-2">
    <div className="row wrap gap-2">
      <strong>Terminal</strong>
      <span role="status">{estado === 'conectando' ? 'Conectando…' : estado === 'abierta' ? 'Conectada' : 'Cerrada'}</span>
      <button type="button" className="btn btn-secondary" onClick={onCerrar}>Cerrar terminal</button>
    </div>
    {estado === 'abierta' && <p className="muted">Iniciá sesión con el usuario <strong>nap</strong> y la contraseña de «Revelar acceso inicial».</p>}
    {aviso && <p role="alert">{aviso}</p>}
    {cierre && <p role="alert">{cierre}</p>}
    <div ref={contenedor} data-testid="terminal" style={{ height: 380, width: '100%' }} />
  </section>;
}
