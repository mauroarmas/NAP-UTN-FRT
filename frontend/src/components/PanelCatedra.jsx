import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPedidos, listarServicios, getCatedra, getTemplates } from '../services/api';
import { ESTADO_PEDIDO_CONFIG, ESTADO_SERVICIO_SIMPLE } from '../constants/estados';

export default function PanelCatedra({ user }) {
  const navigate = useNavigate();
  const [pedidos, setPedidos]     = useState([]);
  const [servicios, setServicios] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [catedra, setCatedra]     = useState(null);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const results = await Promise.allSettled([
          getPedidos(),
          listarServicios(),
          getTemplates(),
          user?.catedra_id ? getCatedra(user.catedra_id) : Promise.resolve(null),
        ]);
        if (results[0].status === 'fulfilled') setPedidos(results[0].value.data);
        if (results[1].status === 'fulfilled') setServicios(results[1].value.data);
        if (results[2].status === 'fulfilled') setTemplates(results[2].value.data);
        if (results[3].status === 'fulfilled' && results[3].value) setCatedra(results[3].value.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [user?.catedra_id]);

  const pedidosRecientes = [...pedidos]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5);

  const templateNombre = (id) => templates.find(t => t.id === id)?.nombre || `Template #${id}`;

  const formatDate = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  const irANuevoPedido = () => navigate('/pedidos', { state: { abrirNuevo: true } });

  const sinDatos = !loading && pedidos.length === 0 && servicios.length === 0;

  const cuotaItems = catedra ? [
    { label: 'vCPUs', enUso: catedra.vcpus_en_uso, cuota: catedra.cuota_vcpus, unidad: '' },
    { label: 'RAM',   enUso: catedra.ram_en_uso_mb, cuota: catedra.cuota_ram_mb, unidad: ' MB' },
    { label: 'Disco', enUso: catedra.storage_en_uso_gb, cuota: catedra.cuota_storage_gb, unidad: ' GB' },
  ] : [];

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Mi Panel</h1>
          <p className="page-subtitle">Bienvenido, {user?.nombre}.</p>
        </div>
        <button className="btn btn-primary" onClick={irANuevoPedido}>
          + Nuevo Pedido
        </button>
      </div>

      {loading ? (
        <p className="stat-label">Cargando...</p>
      ) : sinDatos ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <p className="empty-state-text">Todavía no pediste ningún servicio.</p>
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={irANuevoPedido}>
              + Crear mi primer pedido
            </button>
          </div>
        </div>
      ) : (
        <>
          {catedra && (
            <div className="cards-grid">
              {cuotaItems.map((item) => {
                const pct = item.cuota > 0 ? Math.min(100, (item.enUso / item.cuota) * 100) : 0;
                return (
                  <div className="card" key={item.label}>
                    <div className="stat-label" style={{ marginBottom: 8 }}>{item.label}</div>
                    <div className="progress-bar">
                      <div
                        className={`progress-fill ${pct > 80 ? 'red' : pct > 50 ? 'orange' : 'green'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="stat-label" style={{ marginTop: 4 }}>
                      {item.enUso}{item.unidad} de {item.cuota}{item.unidad} en uso
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="card" style={{ marginBottom: 24 }}>
            <div className="card-header">
              <h3 className="card-title">Mis Servicios</h3>
            </div>
            {servicios.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Servicio</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {servicios.map((s) => {
                      const cfg = ESTADO_SERVICIO_SIMPLE[s.estado] || { label: s.estado, badge: 'neutral', icon: '•' };
                      return (
                        <tr key={s.id}>
                          <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                            {s.hostname || `Servicio #${s.id}`}
                          </td>
                          <td>
                            <span className={`badge ${cfg.badge}`}>
                              <span className="badge-dot"></span>
                              {cfg.icon} {cfg.label}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <p className="empty-state-text">Todavía no tenés servicios desplegados.</p>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Mis Pedidos Recientes</h3>
            </div>
            {pedidosRecientes.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Servicio pedido</th>
                      <th>Estado</th>
                      <th>Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pedidosRecientes.map((p) => {
                      const cfg = ESTADO_PEDIDO_CONFIG[p.estado] || { label: p.estado, badge: 'neutral', icon: '•' };
                      return (
                        <tr key={p.id}>
                          <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.id}</td>
                          <td>{templateNombre(p.template_id)}</td>
                          <td>
                            <span className={`badge ${cfg.badge}`}>
                              <span className="badge-dot"></span>
                              {cfg.icon} {cfg.label}
                            </span>
                          </td>
                          <td>{formatDate(p.created_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <p className="empty-state-text">No hay pedidos recientes.</p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
