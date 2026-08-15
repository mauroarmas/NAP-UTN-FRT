import { useState, useEffect } from 'react';
import { getCatedras, getProxmoxStatus, getProxmoxResources, getProxmoxStorage } from '../services/api';
import PanelCatedra from '../components/PanelCatedra';

export default function Dashboard({ user }) {
  const [catedras, setCatedras]   = useState([]);
  const [proxmox, setProxmox]     = useState(null);
  const [resources, setResources] = useState([]);
  const [storages, setStorages]   = useState([]);
  const [loading, setLoading]     = useState(true);

  const isAdmin = user?.rol === 'admin';

  useEffect(() => {
    if (!isAdmin) return;
    const fetchData = async () => {
      try {
        const results = await Promise.allSettled([
          getCatedras(),
          getProxmoxStatus(),
          getProxmoxResources(),
          getProxmoxStorage(),
        ]);
        if (results[0].status === 'fulfilled') setCatedras(results[0].value.data);
        if (results[1].status === 'fulfilled') setProxmox(results[1].value.data);
        if (results[2].status === 'fulfilled') setResources(results[2].value.data);
        if (results[3].status === 'fulfilled') setStorages(results[3].value.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [isAdmin]);

  if (!isAdmin) {
    return <PanelCatedra user={user} />;
  }

  // Proxmox informa en potencias de 1024 y rotula GiB/MiB: acá se hace igual,
  // porque decir "GB" sobre una división por 1024³ era justo lo que hacía que
  // los números del portal no cerraran con los de la interfaz de Proxmox.
  const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const gib = bytes / (1024 ** 3);
    return gib >= 1 ? `${gib.toFixed(2)} GiB` : `${(bytes / (1024 ** 2)).toFixed(0)} MiB`;
  };

  const porcentaje = (usado, total) => (total > 0 ? (usado / total) * 100 : 0);

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Bienvenido, {user?.nombre}. Vista de administrador.
        </p>
      </div>

      {/* Estado del clúster Proxmox */}
      <div className="cards-grid">
        <div className="stat-card">
          <div className="stat-icon green">🔗</div>
          <div className="stat-value">
            {proxmox?.status === 'connected' ? (
              <span className="badge success"><span className="badge-dot"></span>Conectado</span>
            ) : (
              <span className="badge error"><span className="badge-dot"></span>Desconectado</span>
            )}
          </div>
          <div className="stat-label">Proxmox VE</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon blue">🖥️</div>
          <div className="stat-value">{loading ? '—' : proxmox?.nodes?.length || 0}</div>
          <div className="stat-label">Nodos en el clúster</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon purple">📦</div>
          <div className="stat-value">{loading ? '—' : resources.filter(r => r.type === 'lxc' || r.type === 'qemu').length}</div>
          <div className="stat-label">VMs / Contenedores</div>
        </div>
      </div>

      {/* Info de los nodos Proxmox */}
      {proxmox?.nodes?.map((node) => (
        <div className="card" key={node.node} style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3 className="card-title">Nodo: {node.node}</h3>
            <span className={`badge ${node.status === 'online' ? 'success' : 'error'}`}>
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
              <div
                className="stat-label"
                style={{ marginBottom: 8 }}
                title="Sistema de archivos raíz del host. No es donde se crean los contenedores: eso se ve más abajo, en Almacenamiento."
              >
                Disco del sistema ({formatBytes(node.maxdisk)})
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
      ))}

      {/* Almacenamiento por storage.
          El "Disco del sistema" de arriba es solo la raíz del host; los
          contenedores se crean en el storage con contenido rootdir/images
          (local-lvm), así que ese es el que dice si entra un LXC más. */}
      {storages.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3 className="card-title">Almacenamiento</h3>
            <span className="stat-label" style={{ fontSize: 11 }}>
              Total del clúster: {formatBytes(storages.reduce((acc, s) => acc + s.usado_bytes, 0))}
              {' de '}
              {formatBytes(storages.reduce((acc, s) => acc + s.total_bytes, 0))}
            </span>
          </div>

          <div className="cards-grid" style={{ marginBottom: 0 }}>
            {storages.map((s) => {
              const pct = porcentaje(s.usado_bytes, s.total_bytes);
              return (
                <div key={`${s.node}-${s.storage}`}>
                  <div className="stat-label" style={{ marginBottom: 8 }}>
                    {s.storage}
                    {s.aloja_contenedores && (
                      <span
                        className="badge info"
                        style={{ marginLeft: 8, fontSize: 10 }}
                        title="Acá se crean los contenedores: este es el espacio que limita los despliegues"
                      >
                        contenedores
                      </span>
                    )}
                  </div>
                  <div className="progress-bar">
                    <div
                      className={`progress-fill ${pct > 80 ? 'red' : pct > 50 ? 'orange' : 'green'}`}
                      style={{ width: `${pct.toFixed(0)}%` }}
                    />
                  </div>
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    {formatBytes(s.usado_bytes)} de {formatBytes(s.total_bytes)} ({pct.toFixed(0)}%)
                  </div>
                  <div className="stat-label" style={{ marginTop: 2, fontSize: 11, opacity: 0.7 }}>
                    {s.tipo} · {s.contenido} · nodo {s.node}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && proxmox?.status !== 'connected' && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="empty-state">
            <div className="empty-state-icon">⚠️</div>
            <p className="empty-state-text">No se pudo conectar con Proxmox VE</p>
            <p className="stat-label">Verificá que la VM de Proxmox esté encendida</p>
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
