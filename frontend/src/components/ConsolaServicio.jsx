import { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { obtenerTicketConsola } from '../services/api';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ⚠️ EN PAUSA (2026-08-15) — este componente NO se usa hoy. Ningún import lo
// referencia; queda en el repo a la espera de definir con la cátedra cómo debe
// gestionarse el acceso al contenedor (ver DUDAS-ENTREVISTA.md). El relay del
// backend conecta y autentica bien contra Proxmox pero la sesión muere sin
// transmitir; la hipótesis sin confirmar es que Proxmox no acepta API tokens
// para el websocket de consola y hace falta un ticket de sesión.
//
// Terminal interactiva de un servicio, proxeada por el backend: el navegador
// solo habla con nuestro WebSocket (nunca con Proxmox directo — Principio I
// de la constitución). Pide un ticket de un solo uso por cada apertura, así
// que salir de esta vista y volver a entrar siempre abre una sesión nueva
// (FR-009), nunca reconecta una anterior.
export default function ConsolaServicio({ servicioId, onClose }) {
  const containerRef = useRef(null);

  useEffect(() => {
    let terminal;
    let socket;
    let fitAddon;
    let desmontado = false;

    const conectar = async () => {
      let ticket;
      try {
        const { data } = await obtenerTicketConsola(servicioId);
        ticket = data.ticket;
      } catch (err) {
        alert(`❌ ${err.response?.data?.detail || err.message}`);
        onClose?.();
        return;
      }
      if (desmontado || !containerRef.current) return;

      terminal = new Terminal({
        cursorBlink: true,
        convertEol: true,
        fontSize: 13,
        theme: { background: '#0b0e1a' },
      });
      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);
      terminal.open(containerRef.current);
      fitAddon.fit();

      const wsBase = API_BASE.replace(/^http/, 'ws');
      socket = new WebSocket(
        `${wsBase}/api/v1/servicios/${servicioId}/console?ticket=${encodeURIComponent(ticket)}`
      );
      // El subprotocolo negociado del lado de Proxmox es "binary": todo lo que
      // se manda y se recibe tiene que viajar como frame binario, no de texto
      // (un `socket.send(string)` común manda un frame de texto igual).
      socket.binaryType = 'arraybuffer';
      const encoder = new TextEncoder();

      // Proxmox espera este mensaje de tamaño ("1:cols:rows:") apenas se abre
      // la conexión para terminar de levantar la terminal del lado del
      // contenedor; sin él, cierra la conexión a los pocos segundos.
      const enviarTamano = () => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(encoder.encode(`1:${terminal.cols}:${terminal.rows}:`));
        }
      };

      socket.onopen = enviarTamano;
      socket.onmessage = (evt) => terminal.write(new Uint8Array(evt.data));
      socket.onerror = () => terminal.writeln('\r\n⚠️ Error de conexión con la consola.');
      socket.onclose = () => terminal.writeln('\r\n— Consola desconectada —');

      terminal.onData((chunk) => {
        if (socket.readyState === WebSocket.OPEN) socket.send(encoder.encode(chunk));
      });
      terminal.onResize(enviarTamano);
    };

    conectar();

    const handleResize = () => fitAddon?.fit();
    window.addEventListener('resize', handleResize);

    return () => {
      desmontado = true;
      window.removeEventListener('resize', handleResize);
      socket?.close();
      terminal?.dispose();
    };
  }, [servicioId]);

  return (
    <div className="card fade-in" style={{ marginBottom: 24, borderColor: 'var(--accent)', borderWidth: 2 }}>
      <div className="card-header">
        <h3 className="card-title">🖥️ Consola</h3>
        <button className="btn btn-secondary btn-sm" onClick={onClose}>✕ Cerrar</button>
      </div>
      <div
        ref={containerRef}
        style={{ height: 400, background: '#0b0e1a', borderRadius: 'var(--radius-sm)', padding: 8 }}
      />
    </div>
  );
}
