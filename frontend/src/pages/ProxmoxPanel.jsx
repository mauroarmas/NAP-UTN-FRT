import { useState, useEffect } from 'react';
import { getProxmoxStatus, getProxmoxResources } from '../services/api';

export default function ProxmoxPanel() {
  const [status, setStatus] = useState(null);
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, resourcesRes] = await Promise.allSettled([
          getProxmoxStatus(),
          getProxmoxResources(),
        ]);
        if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data);
        if (resourcesRes.status === 'fulfilled') setResources(resourcesRes.value.data);
      } catch (err) {
        setError('No se pudo conectar con Proxmox VE');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const gb = bytes / (1024 * 1024 * 1024);
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  };

  if (loading) return <div className="empty-state loading-pulse"><p>Conectando con Proxmox VE...</p></div>;

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Proxmox VE</h1>
        <p className="page-subtitle">Estado del clúster y recursos</p>
      </div>

      {/* Connection Status */}
      <div className="cards-grid">
        <div className="stat-card">
          <div className="stat-icon green">🔗</div>
          <div className="stat-value">
            {status?.status === 'connected' ? (
              <span className="badge success"><span className="badge-dot"></span>Conectado</span>
            ) : (
              <span className="badge error"><span className="badge-dot"></span>Desconectado</span>
            )}
          </div>
          <div className="stat-label">Estado de conexión</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon blue">🖥️</div>
          <div className="stat-value">{status?.nodes?.length || 0}</div>
          <div className="stat-label">Nodos en el clúster</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon purple">📦</div>
          <div className="stat-value">{resources.filter(r => r.type === 'lxc' || r.type === 'qemu').length}</div>
          <div className="stat-label">VMs / Contenedores</div>
        </div>
      </div>

      {/* Nodes */}
      {status?.nodes?.map((node) => (
        <div className="card" key={node.node} style={{ marginBottom: 20 }}>
          <div className="card-header">
            <h3 className="card-title">Nodo: {node.node}</h3>
            <span className={`badge ${node.status === 'online' ? 'success' : 'error'}`}>
              <span className="badge-dot"></span>
              {node.status}
            </span>
          </div>
          <div className="cards-grid" style={{ marginBottom: 0 }}>
            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>CPU ({node.maxcpu} cores)</div>
              <div className="progress-bar">
                <div className={`progress-fill ${node.cpu > 0.8 ? 'red' : 'green'}`} style={{ width: `${(node.cpu * 100)}%` }} />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>{(node.cpu * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>RAM ({formatBytes(node.maxmem)})</div>
              <div className="progress-bar">
                <div className="progress-fill blue" style={{ width: `${(node.mem / node.maxmem * 100)}%` }} />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>{formatBytes(node.mem)} usados</div>
            </div>
            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>Disco ({formatBytes(node.maxdisk)})</div>
              <div className="progress-bar">
                <div className="progress-fill purple" style={{ width: `${(node.disk / node.maxdisk * 100)}%` }} />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>{formatBytes(node.disk)} usados</div>
            </div>
          </div>
        </div>
      ))}

      {error && (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">⚠️</div>
            <p className="empty-state-text">{error}</p>
            <p className="stat-label">Verificá que la VM de Proxmox esté encendida</p>
          </div>
        </div>
      )}
    </div>
  );
}
