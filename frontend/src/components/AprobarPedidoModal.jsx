import { useState, useEffect } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, Settings, Server, HardDrive, Network, Zap } from 'lucide-react';
import { aprobarPedido } from '../services/api';
import PanelCapacidad from './PanelCapacidad';
import { Dialog } from './ui';

export default function AprobarPedidoModal({
  open,
  pedido,
  evaluacion,
  templates = [],
  onClose,
  onAprobado,
  onRecargarCapacidad,
}) {
  const [templateId, setTemplateId] = useState('');
  const [desplegarInmediatamente, setDesplegarInmediatamente] = useState(true);
  const [mostrarAvanzadas, setMostrarAvanzadas] = useState(false);
  const [nodoDestino, setNodoDestino] = useState('');
  const [storagePool, setStoragePool] = useState('local-lvm');
  const [vlanTag, setVlanTag] = useState('');
  const [overrideVcpus, setOverrideVcpus] = useState('');
  const [overrideRamMb, setOverrideRamMb] = useState('');
  const [overrideDiskGb, setOverrideDiskGb] = useState('');
  const [justificacion, setJustificacion] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !pedido) return;
    setError(null);
    setJustificacion('');
    setTemplateId(pedido.template_id ? String(pedido.template_id) : (templates.length > 0 ? String(templates[0].id) : ''));
    setDesplegarInmediatamente(true);
    setMostrarAvanzadas(false);
    setNodoDestino('');
    setStoragePool('local-lvm');
    setVlanTag('');
    setOverrideVcpus('');
    setOverrideRamMb('');
    setOverrideDiskGb('');
  }, [open, pedido, templates]);

  if (!open || !pedido) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!templateId) {
      setError('Debes seleccionar una plantilla para aprobar el pedido.');
      return;
    }

    if (evaluacion?.excede_capacidad && !justificacion.trim()) {
      setError('Aprobar por encima de la capacidad libre requiere una justificación.');
      return;
    }

    setEnviando(true);
    try {
      const opcionesAvanzadas = {};
      if (nodoDestino.trim()) opcionesAvanzadas.nodo_destino = nodoDestino.trim();
      if (storagePool.trim() && storagePool !== 'local-lvm') opcionesAvanzadas.storage_pool = storagePool.trim();
      if (vlanTag) opcionesAvanzadas.vlan_tag = parseInt(vlanTag);
      if (overrideVcpus) opcionesAvanzadas.override_vcpus = parseInt(overrideVcpus);
      if (overrideRamMb) opcionesAvanzadas.override_ram_mb = parseInt(overrideRamMb);
      if (overrideDiskGb) opcionesAvanzadas.override_disk_gb = parseInt(overrideDiskGb);

      const payload = {
        capacidad_token: evaluacion?.capacidad_token || null,
        justificacion_capacidad: justificacion.trim() || null,
        template_id: parseInt(templateId),
        desplegar_inmediatamente: desplegarInmediatamente,
        opciones_avanzadas: Object.keys(opcionesAvanzadas).length > 0 ? opcionesAvanzadas : null,
      };

      const { data } = await aprobarPedido(pedido.id, payload);
      if (onAprobado) onAprobado(data);
      onClose();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'token_desactualizado') {
        setError('La capacidad del clúster cambió mientras evaluabas. Actualizá la capacidad y reconfirmá.');
        if (onRecargarCapacidad) onRecargarCapacidad();
      } else if (d?.codigo === 'excede_capacidad') {
        setError(d.mensaje);
        if (onRecargarCapacidad) onRecargarCapacidad();
      } else {
        setError(typeof d === 'string' ? d : err.message || 'Error al aprobar el pedido');
      }
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog wide title={`Aprobar Pedido #${pedido.id}`} onClose={onClose}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && (
          <div className="callout bad">
            <span>{error}</span>
          </div>
        )}

        {/* Resumen del pedido */}
        <div style={{ background: 'var(--color-surface)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-divider)' }}>
          <div style={{ fontSize: 13, color: 'var(--text-soft)' }}>
            <strong>Modelo:</strong> {(pedido.modelo_servicio || 'iaas').toUpperCase()} · <strong>Cátedra:</strong> {pedido.catedra?.nombre || `#${pedido.catedra_id}`}
          </div>
          {pedido.descripcion_requerimientos && (
            <div style={{ fontSize: 13, marginTop: 4, fontStyle: 'italic' }}>
              “{pedido.descripcion_requerimientos}”
            </div>
          )}
        </div>

        {/* 1. Selección de plantilla homologada */}
        <div>
          <label className="label" style={{ fontWeight: 600 }}>
            1. Plantilla de Recursos Asignada
          </label>
          <select
            className="input select"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            required
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre} ({t.default_vcpus} vCPU · {t.default_ram_mb} MB RAM · {t.default_disk_gb} GB Disco)
              </option>
            ))}
          </select>
        </div>

        {/* 2. Capacidad del Clúster */}
        {evaluacion && <PanelCapacidad evaluacion={evaluacion} />}

        {evaluacion?.excede_capacidad && (
          <div className="field">
            <label className="label" style={{ fontWeight: 600 }}>
              Justificación obligatoria (por exceder capacidad libre)
            </label>
            <input
              className="input"
              placeholder="Ej: Aprobado para curso intensivo con apagado de laboratorios"
              value={justificacion}
              onChange={(e) => setJustificacion(e.target.value)}
              required
            />
          </div>
        )}

        {/* 3. Despliegue automático o solo reserva */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            padding: 'var(--space-3)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--color-divider)',
            background: desplegarInmediatamente ? 'var(--accent-tint)' : 'transparent',
          }}
        >
          <input
            type="checkbox"
            id="desplegar_inmediatamente"
            checked={desplegarInmediatamente}
            onChange={(e) => setDesplegarInmediatamente(e.target.checked)}
            style={{ width: 18, height: 18, cursor: 'pointer' }}
          />
          <label htmlFor="desplegar_inmediatamente" style={{ cursor: 'pointer', fontSize: 13 }}>
            <strong>Desplegar inmediatamente en Proxmox</strong> (Aprovisionamiento 100% automático tras aprobación).
          </label>
        </div>

        {/* 4. Opciones Avanzadas (Acordeón colapsable) */}
        <div style={{ border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)' }}>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'space-between', padding: '10px 14px' }}
            onClick={() => setMostrarAvanzadas(!mostrarAvanzadas)}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
              <Settings size={15} />
              Opciones Avanzadas (Nodo, Red VLAN, Storage, Overrides)
            </span>
            {mostrarAvanzadas ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>

          {mostrarAvanzadas && (
            <div style={{ padding: '14px', borderTop: '1px solid var(--color-divider)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
                <div>
                  <label className="label" style={{ fontSize: 12 }}>Nodo Proxmox</label>
                  <input
                    className="input"
                    placeholder="Automático (menor carga)"
                    value={nodoDestino}
                    onChange={(e) => setNodoDestino(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label" style={{ fontSize: 12 }}>Storage Pool</label>
                  <input
                    className="input"
                    placeholder="local-lvm"
                    value={storagePool}
                    onChange={(e) => setStoragePool(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label" style={{ fontSize: 12 }}>VLAN Tag</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="Ej. 100"
                    value={vlanTag}
                    onChange={(e) => setVlanTag(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="label" style={{ fontSize: 12, fontWeight: 600 }}>
                  Ajustes manuales de capacidad (Overrides de plantilla)
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
                  <div>
                    <label className="label" style={{ fontSize: 11 }}>vCPUs</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="Ej. 2"
                      value={overrideVcpus}
                      onChange={(e) => setOverrideVcpus(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="label" style={{ fontSize: 11 }}>RAM (MB)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="Ej. 1024"
                      value={overrideRamMb}
                      onChange={(e) => setOverrideRamMb(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="label" style={{ fontSize: 11 }}>Disco (GB)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="Ej. 8"
                      value={overrideDiskGb}
                      onChange={(e) => setOverrideDiskGb(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Botones de acción */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={enviando}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando
              ? 'Procesando...'
              : desplegarInmediatamente
              ? 'Aprobar y Desplegar'
              : 'Solo Aprobar y Reservar'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

