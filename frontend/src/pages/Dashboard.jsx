import { useState, useEffect } from 'react';
import { getCatedras, getProxmoxStatus } from '../services/api';

export default function Dashboard({ user }) {
  const [catedras, setCatedras] = useState([]);
  const [proxmox, setProxmox] = useState(null);
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.rol === 'admin';

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [catRes] = await Promise.allSettled([
          getCatedras(),
          isAdmin ? getProxmoxStatus().then(r => setProxmox(r.data)) : Promise.resolve(),
        ]);
        if (catRes.status === 'fulfilled') setCatedras(catRes.value.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [isAdmin]);

  const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const gb = bytes / (1024 * 1024 * 1024);
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  };

  const node = proxmox?.nodes?.[0];

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Bienvenido, {user?.nombre}. {isAdmin ? 'Vista de administrador.' : 'Vista de cátedra.'}
        </p>
      </div>

      {/* Stats */}
      <div className="cards-grid">
        <div className="stat-card">
          <div className="stat-icon purple">🏛️</div>
          <div className="stat-value">{loading ? '—' : catedras.length}</div>
          <div className="stat-label">Cátedras registradas</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon green">🖥️</div>
          <div className="stat-value">0</div>
          <div className="stat-label">Servicios activos</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon blue">📋</div>
          <div className="stat-value">0</div>
          <div className="stat-label">Pedidos pendientes</div>
        </div>

        {isAdmin && (
          <div className="stat-card">
            <div className="stat-icon orange">⚡</div>
            <div className="stat-value">
              {proxmox?.status === 'connected' ? (
                <span className="badge success">
                  <span className="badge-dot"></span>
                  Conectado
                </span>
              ) : (
                <span className="badge error">
                  <span className="badge-dot"></span>
                  Desconectado
                </span>
              )}
            </div>
            <div className="stat-label">Proxmox VE</div>
          </div>
        )}
      </div>

      {/* Proxmox Node Info (admin only) */}
      {isAdmin && node && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3 className="card-title">Nodo: {node.node}</h3>
            <span className="badge success">
              <span className="badge-dot"></span>
              {node.status}
            </span>
          </div>

          <div className="cards-grid" style={{ marginBottom: 0 }}>
            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>
                CPU ({node.maxcpu} cores)
              </div>
              <div className="progress-bar">
                <div
                  className={`progress-fill ${node.cpu > 0.8 ? 'red' : node.cpu > 0.5 ? 'orange' : 'green'}`}
                  style={{ width: `${(node.cpu * 100).toFixed(0)}%` }}
                />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>
                {(node.cpu * 100).toFixed(1)}% en uso
              </div>
            </div>

            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>
                RAM ({formatBytes(node.maxmem)})
              </div>
              <div className="progress-bar">
                <div
                  className={`progress-fill ${node.mem / node.maxmem > 0.8 ? 'red' : 'blue'}`}
                  style={{ width: `${((node.mem / node.maxmem) * 100).toFixed(0)}%` }}
                />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>
                {formatBytes(node.mem)} en uso
              </div>
            </div>

            <div>
              <div className="stat-label" style={{ marginBottom: 8 }}>
                Disco ({formatBytes(node.maxdisk)})
              </div>
              <div className="progress-bar">
                <div
                  className={`progress-fill ${node.disk / node.maxdisk > 0.8 ? 'red' : 'purple'}`}
                  style={{ width: `${((node.disk / node.maxdisk) * 100).toFixed(0)}%` }}
                />
              </div>
              <div className="stat-label" style={{ marginTop: 4 }}>
                {formatBytes(node.disk)} en uso
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cátedras Table */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Cátedras</h3>
        </div>

        {catedras.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>vCPUs</th>
                  <th>RAM</th>
                  <th>Disco</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {catedras.map((c) => (
                  <tr key={c.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{c.nombre}</td>
                    <td>{c.cuota_vcpus} cores</td>
                    <td>{c.cuota_ram_mb} MB</td>
                    <td>{c.cuota_storage_gb} GB</td>
                    <td>
                      <span className={`badge ${c.activa ? 'success' : 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {c.activa ? 'Activa' : 'Inactiva'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🏛️</div>
            <p className="empty-state-text">
              {loading ? 'Cargando cátedras...' : 'No hay cátedras registradas aún'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
