import { useEffect, useRef, useState } from 'react';
import { solicitarAjustePedido } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import { Dialog } from './ui';

export default function AjustePedidoModal({ open, pedido, user, onClose, onAjusteSolicitado }) {
  const [observations, setObservations] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  useEffect(() => {
    if (open) { setObservations(''); setError(''); setBusy(false); key.current = crypto.randomUUID(); submitting.current = false; }
  }, [open, pedido?.id]);
  if (!open || !pedido || user?.rol !== 'admin') return null;
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !observations.trim()) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const { data } = await solicitarAjustePedido(pedido.id, observations.trim(), key.current);
      onAjusteSolicitado?.(data); onClose();
    } catch (err) { setError(err); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title={`Registrar ajustes del pedido #${pedido.id}`} onClose={onClose} closeDisabled={busy}>
    <form onSubmit={submit} className="col gap-3">
      <ErrorFormulario error={error} />
      <p>Administración registra las observaciones y realiza la corrección tras revisarlas con la cátedra.</p>
      {pedido.estado === 'aprobado' && <p>Si todavía no comenzó el envío a infraestructura, se revocará la aprobación y se liberará su reserva.</p>}
      <label htmlFor="request-adjustments">Observaciones</label>
      <textarea id="request-adjustments" value={observations} maxLength={2000} required disabled={busy}
        onChange={(e) => { setObservations(e.target.value); key.current = crypto.randomUUID(); }} />
      <div className="row gap-2"><button type="button" onClick={onClose} disabled={busy}>Cerrar</button>
        <button type="submit" className="btn btn-primary" disabled={busy || !observations.trim()}>{busy ? 'Guardando…' : 'Registrar ajuste'}</button></div>
    </form>
  </Dialog>;
}
