import { useState, useEffect } from 'react';
import { AlertCircle } from 'lucide-react';
import { solicitarAjustePedido } from '../services/api';
import { Dialog } from './ui';

export default function AjustePedidoModal({ open, pedido, onClose, onAjusteSolicitado }) {
  const [observaciones, setObservaciones] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setObservaciones('');
    setError(null);
  }, [open]);

  if (!open || !pedido) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!observaciones.trim()) {
      setError('Debes ingresar las observaciones o cambios solicitados a la cátedra.');
      return;
    }

    setEnviando(true);
    setError(null);
    try {
      const { data } = await solicitarAjustePedido(pedido.id, observaciones.trim());
      if (onAjusteSolicitado) onAjusteSolicitado(data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al solicitar ajuste.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={`Solicitar Ajuste en Pedido #${pedido.id}`}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && (
          <div className="callout bad">
            <span>{error}</span>
          </div>
        )}

        <div className="callout warn">
          <AlertCircle size={16} />
          <span>
            Al solicitar un ajuste, el pedido volverá al panel de la cátedra en estado{' '}
            <strong>Requiere Ajuste</strong>. La cátedra podrá modificar su solicitud según tus observaciones y reenviarla.
          </span>
        </div>

        <div className="field">
          <label className="label" style={{ fontWeight: 600 }}>
            Observaciones y Cambios Requeridos
          </label>
          <textarea
            className="input textarea"
            rows={4}
            placeholder="Ej: El clúster no dispone de 16 GB de RAM para esta cátedra en este período. Por favor ajustá a 8 GB o dividí el recurso en dos comisiones..."
            value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)}
            required
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={enviando}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? 'Enviando...' : 'Devolver a la Cátedra para Ajuste'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

