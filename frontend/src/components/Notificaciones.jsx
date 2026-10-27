import { useState } from 'react';
import { Bell, CheckCheck, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import useRemoteData from '../hooks/useRemoteData';
import { getAvisos } from '../services/api';
import { Dialog } from './ui';

function readSeen(key) {
  try { const data = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(data) ? data : []; }
  catch { return []; }
}

export default function Notificaciones({ user }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const storageKey = `nap:avisos-vistos:${user.id}`;
  const [seen, setSeen] = useState(() => readSeen(storageKey));
  const remote = useRemoteData((options) => getAvisos({ limit: 20 }, options), {
    key: `avisos:${user.id}:${user.rol}`, refreshMs: 15000, errorMessage: 'No se pudieron consultar las notificaciones.' });
  const rows = remote.data || [];
  const unread = rows.filter((row) => !seen.includes(row.id)).length;
  const markSeen = (ids = rows.map((row) => row.id)) => {
    const values = [...new Set([...ids, ...seen])].slice(0, 200);
    setSeen(values);
    try { localStorage.setItem(storageKey, JSON.stringify(values)); } catch { /* conserva lectura durante esta sesión */ }
  };
  const visit = (row) => {
    markSeen([row.id]); setOpen(false);
    navigate(row.pedido_id ? `/pedidos?pedido=${row.pedido_id}` : row.servicio_id ? '/servicios' : '/catalogo');
  };
  return <>
    <button type="button" className="btn-icon notifications-trigger" aria-label={`Notificaciones${unread ? ` (${unread} nuevas)` : ''}`} onClick={() => { setOpen(true); remote.reload(); }}>
      <Bell size={19}/>{unread > 0 && <span className="notifications-badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
    </button>
    {open && <Dialog title="Notificaciones" onClose={() => setOpen(false)} className="notifications-dialog">
      {remote.error && <div role="alert" className="callout warn">{remote.error}<button className="btn btn-secondary" onClick={remote.reload}>Volver a consultar</button></div>}
      {remote.loading && !remote.data && <p role="status">Consultando notificaciones…</p>}
      {!remote.loading && !remote.error && !rows.length && <p className="notifications-empty">No tenés notificaciones por ahora.</p>}
      {rows.length > 0 && <><div className="notifications-toolbar"><span>{unread ? `${unread} sin leer` : 'Estás al día'}</span>
        <button type="button" className="btn btn-ghost" onClick={() => markSeen()} disabled={!unread}><CheckCheck size={16}/>Marcar como leídas</button></div>
        <ul className="notifications-list">{rows.map((row) => <li key={row.id}><button type="button" className={`notification-item ${seen.includes(row.id) ? '' : 'is-unread'}`} onClick={() => visit(row)}>
          <span><strong>{row.asunto || 'Nuevo aviso'}</strong><p>{row.texto}</p><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></span><ChevronRight size={16}/>
        </button></li>)}</ul></>}
    </Dialog>}
  </>;
}
