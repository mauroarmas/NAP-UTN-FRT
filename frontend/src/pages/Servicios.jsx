import { useState, useEffect } from 'react';
import { getPedidos, listarServicios, desplegarPedido, iniciarServicio, detenerServicio, getStatusServicio, getCatedras } from '../services/api';

const ESTADO_SERVICIO_CONFIG = {
  running:  { label: 'Corriendo',  badge: 'success', icon: '🟢' },
  stopped:  { label: 'Detenido',  badge: 'neutral',  icon: '⏹️' },
  paused:   { label: 'Pausado',   badge: 'warning',  icon: '⏸️' },
  error:    { label: 'Error',     badge: 'error',    icon: '⚠️' },
};

export default function Servicios({ user }) {
  const [servicios, setServicios] = useState([]);
  const [pedidosAprobados, setPedidosAprobados] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accionando, setAccionando] = useState(null); // ID del servicio/pedido en acción
  const [statusDetalle, setStatusDetalle] = useState(null);

  const isAdmin = user?.rol === 'admin';

  const fetchData = async () => {
    try {
      const [srvRes, pedRes, catRes] = await Promise.allSettled([
        listarServicios(),
        isAdmin ? getPedidos('aprobado') : Promise.resolve({ data: [] }),
        isAdmin ? getCatedras() : Promise.resolve({ data: [] }),
      ]);
      if (srvRes.status === 'fulfilled') setServicios(srvRes.value.data);
      if (pedRes.status === 'fulfilled') setPedidosAprobados(pedRes.value.data);
      if (catRes.status === 'fulfilled') setCatedras(catRes.value.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const catedraNombre = (id) => catedras.find(c => c.id === id)?.nombre || `Cátedra #${id}`;

  useEffect(() => { fetchData(); }, []);

  const handleDesplegar = async (pedidoId) => {
    if (!confirm(`¿Desplegar pedido #${pedidoId} en Proxmox?`)) return;
    setAccionando(`deploy-${pedidoId}`);
    try {
      await desplegarPedido(pedidoId);
      await fetchData();
      alert(`✅ Pedido #${pedidoId} desplegado exitosamente`);
    } catch (err) {
      alert(`❌ Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setAccionando(null);
    }
  };

  const handleStart = async (id) => {
    setAccionando(`start-${id}`);
    try {
      await iniciarServicio(id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
    } finally {
      setAccionando(null);
    }
  };

  const handleStop = async (id) => {
    if (!confirm('¿Detener el servicio?')) return;
    setAccionando(`stop-${id}`);
    try {
      await detenerServicio(id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
    } finally {
      setAccionando(null);
    }
  };

  const handleStatus = async (id) => {
    try {
      const { data } = await getStatusServicio(id);
      setStatusDetalle(data);
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Servicios</h1>
        <p className="page-subtitle">Contenedores desplegados en Proxmox VE</p>
      </div>

      {/* Stats rápidas */}
      <div className="cards-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-icon green">🟢</div>
          <div className="stat-value">{servicios.filter(s => s.estado === 'running').length}</div>
          <div className="stat-label">Corriendo</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon orange">⏹️</div>
          <div className="stat-value">{servicios.filter(s => s.estado === 'stopped').length}</div>
          <div className="stat-label">Detenidos</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon purple">📦</div>
          <div className="stat-value">{servicios.length}</div>
          <div className="stat-label">Total desplegados</div>
        </div>
      </div>

      {/* Pedidos aprobados esperando despliegue — solo admin */}
      {isAdmin && pedidosAprobados.length > 0 && (
        <div className="card" style={{ marginBottom: 24, borderColor: 'var(--accent)' }}>
          <div className="card-header">
            <h3 className="card-title">🚀 Pedidos listos para desplegar</h3>
            <span className="badge info">
              <span className="badge-dot"></span>
              {pedidosAprobados.length} pendiente{pedidosAprobados.length > 1 ? 's' : ''}
            </span>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Pedido</th>
                  <th>Cátedra</th>
                  <th>Template</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {pedidosAprobados.map(p => (
                  <tr key={p.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>#{p.id}</td>
                    <td>{catedraNombre(p.catedra_id)}</td>
                    <td>Template #{p.template_id}</td>
                    <td>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleDesplegar(p.id)}
                        disabled={accionando === `deploy-${p.id}`}
                      >
                        {accionando === `deploy-${p.id}` ? '⏳ Desplegando...' : '🚀 Desplegar'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detalle de status Proxmox */}
      {statusDetalle && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3 className="card-title">Estado en Proxmox — VMID {statusDetalle.vmid}</h3>
            <button className="btn btn-secondary btn-sm" onClick={() => setStatusDetalle(null)}>✕</button>
          </div>
          <pre style={{ fontSize: 12, color: 'var(--text-secondary)', overflowX: 'auto', background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-sm)' }}>
            {JSON.stringify(statusDetalle.proxmox_status, null, 2)}
          </pre>
        </div>
      )}

      {/* Lista de servicios */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Contenedores ({servicios.length})</h3>
        </div>

        {servicios.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>VMID</th>
                  <th>Hostname</th>
                  <th>Nodo</th>
                  <th>Recursos</th>
                  <th>Estado</th>
                  <th>Desplegado</th>
                  {isAdmin && <th>Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {servicios.map(s => (
                  <tr key={s.id}>
                    <td style={{ color: 'var(--accent)', fontWeight: 600, fontFamily: 'monospace' }}>
                      {s.proxmox_vmid || '—'}
                    </td>
                    <td style={{ color: 'var(--text-primary)' }}>{s.hostname || '—'}</td>
                    <td>{s.proxmox_node || '—'}</td>
                    <td style={{ fontSize: 12 }}>
                      ⚡{s.vcpus_asignados}v · 💾{s.ram_asignada_mb}MB · 💿{s.disk_asignado_gb}GB
                    </td>
                    <td>
                      <span className={`badge ${ESTADO_SERVICIO_CONFIG[s.estado]?.badge || 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {ESTADO_SERVICIO_CONFIG[s.estado]?.icon} {ESTADO_SERVICIO_CONFIG[s.estado]?.label || s.estado}
                      </span>
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {s.deployed_at ? new Date(s.deployed_at).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    {isAdmin && (
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleStatus(s.id)}
                            title="Ver estado en Proxmox"
                          >📊</button>
                          {s.estado === 'running' && (
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleStop(s.id)}
                              disabled={accionando === `stop-${s.id}`}
                            >
                              {accionando === `stop-${s.id}` ? '⏳' : '⏹ Stop'}
                            </button>
                          )}
                          {s.estado === 'stopped' && (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleStart(s.id)}
                              disabled={accionando === `start-${s.id}`}
                            >
                              {accionando === `start-${s.id}` ? '⏳' : '▶ Start'}
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🖥️</div>
            <p className="empty-state-text">
              {loading ? 'Cargando...' : 'No hay servicios desplegados aún'}
            </p>
            {isAdmin && !loading && (
              <p className="stat-label">Aprobá un pedido y desplegalo desde esta vista</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
