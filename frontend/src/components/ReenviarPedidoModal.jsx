import { useState, useEffect } from 'react';
import { Send, Calendar, AlertCircle } from 'lucide-react';
import { getTemplates, reenviarPedido } from '../services/api';
import { Dialog } from './ui';

const VIGENCIAS = [
  { key: 'primer_cuatrimestre', label: '1° Cuatrimestre' },
  { key: 'segundo_cuatrimestre', label: '2° Cuatrimestre' },
  { key: 'anual', label: 'Ciclo Lectivo Anual' },
  { key: 'personalizado', label: 'Personalizado' },
];

export default function ReenviarPedidoModal({ open, pedido, onClose, onReenviado }) {
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [vigenciaTipo, setVigenciaTipo] = useState('primer_cuatrimestre');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !pedido) return;
    setError(null);
    setDescripcion(pedido.descripcion_requerimientos || '');
    setTemplateId(pedido.template_id ? String(pedido.template_id) : '');
    setVigenciaTipo(pedido.vigencia_tipo || 'primer_cuatrimestre');

    getTemplates()
      .then(({ data }) => {
        setTemplates(data.filter((t) => t.activo !== false));
      })
      .catch(console.error);
  }, [open, pedido]);

  if (!open || !pedido) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const payload = {
        template_id: templateId ? parseInt(templateId) : null,
        descripcion_requerimientos: descripcion.trim() || null,
        vigencia_tipo: vigenciaTipo,
      };
      const { data } = await reenviarPedido(pedido.id, payload);
      if (onReenviado) onReenviado(data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al reenviar la solicitud.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={`Modificar y Reenviar Pedido #${pedido.id}`}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && (
          <div className="callout bad">
            <span>{error}</span>
          </div>
        )}

        {pedido.observaciones_ajuste && (
          <div className="callout warn">
            <AlertCircle size={16} />
            <div>
              <strong>Observaciones del Administrador:</strong>
              <div style={{ marginTop: 4 }}>{pedido.observaciones_ajuste}</div>
            </div>
          </div>
        )}

        {templates.length > 0 && (
          <div>
            <label className="label" style={{ fontWeight: 600 }}>Plantilla de Recursos</label>
            <select
              className="input select"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              <option value="">Sin plantilla fija (Servicio a medida)</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre} ({t.default_vcpus} vCPU · {t.default_ram_mb} MB RAM · {t.default_disk_gb} GB Disco)
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="field">
          <label className="label" style={{ fontWeight: 600 }}>Descripción / Nuevos Requerimientos</label>
          <textarea
            className="input textarea"
            rows={4}
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            placeholder="Ajuste de requerimientos solicitados..."
          />
        </div>

        <div>
          <label className="label" style={{ fontWeight: 600 }}>
            <Calendar size={14} style={{ display: 'inline', marginRight: 4 }} />
            Vigencia Temporal
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-2)' }}>
            {VIGENCIAS.map((v) => (
              <button
                type="button"
                key={v.key}
                onClick={() => setVigenciaTipo(v.key)}
                className={`btn btn-sm ${vigenciaTipo === v.key ? 'btn-primary' : 'btn-ghost'}`}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={enviando}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            <Send size={15} style={{ marginRight: 6 }} />
            {enviando ? 'Reenviando...' : 'Reenviar Pedido'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

