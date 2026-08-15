import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { getPedidos, getPedido, createPedido, cambiarEstadoPedido, getTemplates, getCatedras } from '../services/api';
import { ESTADO_PEDIDO_CONFIG as ESTADO_CONFIG } from '../constants/estados';

const TRANSICIONES = {
  solicitado:    ['en_revision', 'rechazado'],
  en_revision:   ['aprobado', 'rechazado'],
  aprobado:      ['en_despliegue'],
  en_despliegue: ['activo', 'error'],
  activo:        ['suspendido'],
  error:         ['en_despliegue', 'rechazado'],
  suspendido:    ['activo'],
  rechazado:     [],
};

export default function Pedidos({ user }) {
  const location = useLocation();
  const [pedidos, setPedidos] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState('');
  // Llega abierto de una: acceso directo desde el panel de cátedra (FR-003).
  const [showNuevo, setShowNuevo] = useState(Boolean(location.state?.abrirNuevo));
  const [detalle, setDetalle] = useState(null);
  const [form, setForm] = useState({ template_id: '', parametros_extra: {} });
  const [saving, setSaving] = useState(false);
  const [transicionando, setTransicionando] = useState(false);
  const [comentario, setComentario] = useState('');
  const [motivoRechazo, setMotivoRechazo] = useState('');

  const isAdmin = user?.rol === 'admin';

  const fetchPedidos = async () => {
    try {
      const { data } = await getPedidos(filtroEstado || null);
      setPedidos(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplates = async () => {
    try {
      const { data } = await getTemplates();
      setTemplates(data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchCatedras = async () => {
    try {
      const { data } = await getCatedras();
      setCatedras(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => { fetchPedidos(); fetchTemplates(); if (isAdmin) fetchCatedras(); }, [filtroEstado]);

  const handleCrear = async (e) => {
    e.preventDefault();
    if (!form.template_id) return;
    setSaving(true);
    try {
      await createPedido({ template_id: parseInt(form.template_id), parametros_extra: form.parametros_extra || null });
      setShowNuevo(false);
      setForm({ template_id: '', parametros_extra: {} });
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al crear pedido');
    } finally {
      setSaving(false);
    }
  };

  const handleTransicion = async (pedidoId, nuevoEstado) => {
    if (nuevoEstado === 'rechazado' && !motivoRechazo) {
      alert('Ingresá un motivo de rechazo');
      return;
    }
    setTransicionando(true);
    try {
      const { data } = await cambiarEstadoPedido(pedidoId, {
        nuevo_estado: nuevoEstado,
        comentario: comentario || null,
        motivo_rechazo: nuevoEstado === 'rechazado' ? motivoRechazo : null,
      });
      setDetalle(data);
      setComentario('');
      setMotivoRechazo('');
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al cambiar estado');
    } finally {
      setTransicionando(false);
    }
  };

  const verDetalle = async (id) => {
    try {
      const { data } = await getPedido(id);
      setDetalle(data);
    } catch (err) {
      alert('Error al cargar detalle');
    }
  };

  const templateNombre = (id) => templates.find(t => t.id === id)?.nombre || `#${id}`;
  const catedraNombre = (id) => catedras.find(c => c.id === id)?.nombre || `Cátedra #${id}`;

  const formatDate = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Pedidos</h1>
          <p className="page-subtitle">Gestión de solicitudes de servicios</p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            className="form-input"
            style={{ width: 180 }}
            value={filtroEstado}
            onChange={e => setFiltroEstado(e.target.value)}
          >
            <option value="">Todos los estados</option>
            {Object.entries(ESTADO_CONFIG).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.icon} {cfg.label}</option>
            ))}
          </select>
          {!isAdmin && (
            <button className="btn btn-primary" onClick={() => setShowNuevo(!showNuevo)}>
              {showNuevo ? 'Cancelar' : '+ Nuevo Pedido'}
            </button>
          )}
        </div>
      </div>

      {/* Formulario nuevo pedido */}
      {showNuevo && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Nuevo Pedido de Servicio</h3>
          {templates.length === 0 ? (
            <div className="empty-state" style={{ padding: 20 }}>
              <p className="empty-state-text">No hay templates disponibles. Un administrador debe crearlos primero.</p>
            </div>
          ) : (
            <form onSubmit={handleCrear}>
              <div className="form-group">
                <label className="form-label">Template de Recurso</label>
                <select
                  className="form-input"
                  value={form.template_id}
                  onChange={e => setForm({ ...form, template_id: e.target.value })}
                  required
                >
                  <option value="">Seleccionar template...</option>
                  {templates.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.nombre} — {t.default_vcpus} vCPU, {t.default_ram_mb}MB RAM, {t.default_disk_gb}GB Disco ({t.tipo})
                    </option>
                  ))}
                </select>
              </div>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Enviando...' : 'Enviar Pedido'}
              </button>
            </form>
          )}
        </div>
      )}

      {/* Detalle del pedido (modal inline) */}
      {detalle && (
        <div className="card fade-in" style={{ marginBottom: 24, borderColor: 'var(--accent)', borderWidth: 2 }}>
          <div className="card-header">
            <h3 className="card-title">
              Pedido #{detalle.id} — {templateNombre(detalle.template_id)}
              {isAdmin && ` (${catedraNombre(detalle.catedra_id)})`}
            </h3>
            <button className="btn btn-secondary btn-sm" onClick={() => setDetalle(null)}>✕ Cerrar</button>
          </div>

          {/* Info del pedido */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div>
              <div className="stat-label">Estado actual</div>
              <span className={`badge ${ESTADO_CONFIG[detalle.estado]?.badge || 'neutral'}`} style={{ marginTop: 4 }}>
                <span className="badge-dot"></span>
                {ESTADO_CONFIG[detalle.estado]?.icon} {ESTADO_CONFIG[detalle.estado]?.label || detalle.estado}
              </span>
            </div>
            <div>
              <div className="stat-label">Creado</div>
              <div style={{ color: 'var(--text-primary)', marginTop: 4, fontSize: 14 }}>{formatDate(detalle.created_at)}</div>
            </div>
            <div>
              <div className="stat-label">Resuelto</div>
              <div style={{ color: 'var(--text-primary)', marginTop: 4, fontSize: 14 }}>{formatDate(detalle.resolved_at)}</div>
            </div>
          </div>

          {detalle.motivo_rechazo && (
            <div style={{ background: 'var(--error-bg)', padding: '12px 16px', borderRadius: 'var(--radius-sm)', marginBottom: 20, color: 'var(--error)', fontSize: 14 }}>
              <strong>Motivo de rechazo:</strong> {detalle.motivo_rechazo}
            </div>
          )}

          {/* Historial (timeline) */}
          <div style={{ marginBottom: 20 }}>
            <div className="stat-label" style={{ marginBottom: 12 }}>Historial de estados</div>
            {detalle.historial?.map((h, i) => (
              <div key={h.id} style={{ display: 'flex', gap: 12, marginBottom: 12, paddingLeft: 12, borderLeft: '2px solid var(--border-color)' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                    <span className={`badge ${ESTADO_CONFIG[h.estado_anterior]?.badge || 'neutral'}`} style={{ fontSize: 11 }}>
                      {h.estado_anterior}
                    </span>
                    {' → '}
                    <span className={`badge ${ESTADO_CONFIG[h.estado_nuevo]?.badge || 'neutral'}`} style={{ fontSize: 11 }}>
                      {h.estado_nuevo}
                    </span>
                  </div>
                  {h.comentario && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{h.comentario}</div>}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(h.created_at)}</div>
              </div>
            ))}
          </div>

          {/* Acciones de transición (admin) */}
          {isAdmin && TRANSICIONES[detalle.estado]?.length > 0 && (
            <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
              <div className="stat-label" style={{ marginBottom: 12 }}>Acciones</div>
              <div className="form-group">
                <input
                  className="form-input"
                  placeholder="Comentario (opcional)"
                  value={comentario}
                  onChange={e => setComentario(e.target.value)}
                />
              </div>
              {TRANSICIONES[detalle.estado].includes('rechazado') && (
                <div className="form-group">
                  <input
                    className="form-input"
                    placeholder="Motivo de rechazo (requerido si rechaza)"
                    value={motivoRechazo}
                    onChange={e => setMotivoRechazo(e.target.value)}
                  />
                </div>
              )}
              <div style={{ display: 'flex', gap: 8 }}>
                {TRANSICIONES[detalle.estado].map(est => (
                  <button
                    key={est}
                    className={`btn btn-sm ${est === 'rechazado' ? 'btn-danger' : 'btn-primary'}`}
                    onClick={() => handleTransicion(detalle.id, est)}
                    disabled={transicionando}
                  >
                    {ESTADO_CONFIG[est]?.icon} {ESTADO_CONFIG[est]?.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tabla de pedidos */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Listado ({pedidos.length})</h3>
        </div>

        {pedidos.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  {isAdmin && <th>Cátedra</th>}
                  <th>Template</th>
                  <th>Estado</th>
                  <th>Fecha</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {pedidos.map(p => (
                  <tr key={p.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.id}</td>
                    {isAdmin && <td>{catedraNombre(p.catedra_id)}</td>}
                    <td>{templateNombre(p.template_id)}</td>
                    <td>
                      <span className={`badge ${ESTADO_CONFIG[p.estado]?.badge || 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {ESTADO_CONFIG[p.estado]?.icon} {ESTADO_CONFIG[p.estado]?.label || p.estado}
                      </span>
                    </td>
                    <td>{formatDate(p.created_at)}</td>
                    <td>
                      <button className="btn btn-secondary btn-sm" onClick={() => verDetalle(p.id)}>
                        Ver detalle
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <p className="empty-state-text">{loading ? 'Cargando...' : 'No hay pedidos'}</p>
          </div>
        )}
      </div>
    </div>
  );
}
