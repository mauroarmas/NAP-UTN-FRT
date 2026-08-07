import { useState, useEffect, useCallback } from 'react';
import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import {
  getResumenMetricas, capturarMetricas,
  getHistorialMetricas, capturarServicio,
} from '../services/api';

// ── Helpers ──────────────────────────────────────────────────────
// fmtTime: convierte a hora local. Si el string no tiene 'Z' ni offset
// (como los timestamps de PostgreSQL sin zona horaria), le agrega 'Z'
// para que el navegador lo interprete como UTC y no como hora local.
const fmtTime = (iso) => {
  if (!iso) return '';
  const normalized = typeof iso === 'string' && !iso.endsWith('Z') && !iso.includes('+') ? iso + 'Z' : iso;
  const d = new Date(normalized);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;
};

const fmtBytes = (bytes) => {
  if (bytes >= 1e9) return `${(bytes/1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes/1e6).toFixed(1)} MB`;
  if (bytes >= 1e3) return `${(bytes/1e3).toFixed(0)} KB`;
  return `${bytes} B`;
};

const GaugeBar = ({ value, max, color, label, icon }) => {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const colorClass = pct > 85 ? 'red' : pct > 60 ? 'orange' : color;
  
  const glowColorMap = {
    'green': 'var(--success)',
    'blue': 'var(--info)',
    'purple': 'var(--accent)',
    'orange': 'var(--warning)',
    'red': 'var(--error)'
  };
  
  const activeColor = glowColorMap[colorClass] || glowColorMap[color];

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, alignItems: 'center' }}>
        <span className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 500, fontSize: 13 }}>
          {icon && <span style={{ display: 'flex', alignItems: 'center' }}>{icon}</span>}
          {label}
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600, fontFamily: 'monospace' }}>
          {pct.toFixed(2)}%
        </span>
      </div>
      <div className="progress-bar" style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'visible', position: 'relative' }}>
        <div 
          className={`progress-fill ${colorClass}`} 
          style={{ 
            width: `${pct}%`, 
            height: '100%',
            borderRadius: 3,
            transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)', 
            position: 'relative',
            boxShadow: `0 0 8px ${activeColor}`,
            opacity: 0.9
          }} 
        >
          {pct > 0 && (
            <div style={{
              position: 'absolute',
              right: 0,
              top: '50%',
              transform: 'translate(50%, -50%)',
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#fff',
              boxShadow: `0 0 10px ${activeColor}, 0 0 4px #fff`
            }} />
          )}
        </div>
      </div>
    </div>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-sm)', padding: '10px 14px', fontSize: 12,
    }}>
      <p style={{ color: 'var(--text-muted)', marginBottom: 6 }}>{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color, margin: '2px 0' }}>
          {p.name}: <strong>{p.value?.toFixed(2)}{p.unit || ''}</strong>
        </p>
      ))}
    </div>
  );
};

// ── Componente principal ──────────────────────────────────────────
export default function Metricas({ user }) {
  const [resumen, setResumen]         = useState([]);
  const [seleccionado, setSeleccionado] = useState(null);
  const [historial, setHistorial]     = useState([]);
  const [cargando, setCargando]       = useState(true);
  const [capturando, setCapturando]   = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastUpdate, setLastUpdate]   = useState(null);

  const isAdmin = user?.rol === 'admin';

  const fetchResumen = useCallback(async () => {
    try {
      const { data } = await getResumenMetricas();
      setResumen(data);
      setLastUpdate(new Date());
    } catch (e) {
      console.error(e);
    } finally {
      setCargando(false);
    }
  }, []);

  const fetchHistorial = useCallback(async (servicioId) => {
    try {
      const { data } = await getHistorialMetricas(servicioId, 60);
      setHistorial(data.map(s => ({
        ...s,
        time: fmtTime(s.timestamp),
      })));
    } catch (e) {
      setHistorial([]);
    }
  }, []);

  // Auto-refresh cada 30s
  useEffect(() => {
    fetchResumen();
    if (!autoRefresh) return;
    const id = setInterval(fetchResumen, 30000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchResumen]);

  // Recargar historial cuando cambia el seleccionado
  useEffect(() => {
    if (seleccionado) fetchHistorial(seleccionado.servicio_id);
  }, [seleccionado, fetchHistorial]);

  const handleCapturar = async () => {
    setCapturando(true);
    try {
      await capturarMetricas();
      await fetchResumen();
      if (seleccionado) await fetchHistorial(seleccionado.servicio_id);
    } catch (e) {
      alert(e.response?.data?.detail || 'Error al capturar métricas');
    } finally {
      setCapturando(false);
    }
  };

  const handleSeleccionar = (srv) => {
    setSeleccionado(srv);
    fetchHistorial(srv.servicio_id);
  };

  return (
    <div className="fade-in">
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Métricas</h1>
          <p className="page-subtitle">
            Observabilidad de recursos en tiempo real
            {lastUpdate && <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: 12 }}>
              · Actualizado: {fmtTime(lastUpdate.toISOString())}
            </span>}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Auto-refresh (30s)
          </label>
          {isAdmin && (
            <button
              className="btn btn-primary"
              onClick={handleCapturar}
              disabled={capturando}
            >
              {capturando ? '⏳ Actualizando...' : '🔄 Actualizar'}
            </button>
          )}
        </div>
      </div>

      {/* Cards de servicios */}
      {cargando ? (
        <div className="empty-state"><p className="empty-state-text">Cargando métricas...</p></div>
      ) : resumen.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">📊</div>
            <p className="empty-state-text">No hay servicios con métricas disponibles</p>
            {isAdmin && <button className="btn btn-primary" onClick={handleCapturar}>Capturar primera métrica</button>}
          </div>
        </div>
      ) : (
        <>
          {/* Grid de tarjetas — una por servicio */}
          <div className="cards-grid" style={{ marginBottom: 24 }}>
            {resumen.map(srv => {
              const snap = srv.ultimo_snapshot;
              const isSelected = seleccionado?.servicio_id === srv.servicio_id;
              return (
                <div
                  key={srv.servicio_id}
                  className="stat-card"
                  style={{
                    cursor: 'pointer',
                    borderColor: isSelected ? 'var(--accent)' : 'var(--border-color)',
                    borderWidth: 1,
                    boxShadow: isSelected ? '0 0 0 2px var(--accent)' : 'var(--shadow-sm)',
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                    position: 'relative',
                    overflow: 'hidden',
                    background: isSelected ? 'linear-gradient(180deg, var(--bg-card-hover) 0%, var(--bg-card) 100%)' : 'var(--bg-card)',
                    padding: '24px 24px 20px 24px'
                  }}
                  onClick={() => handleSeleccionar(srv)}
                >
                  {/* Subtly glow top border if running and selected */}
                  {isSelected && (
                    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: 'var(--accent-gradient)', transition: 'background 0.3s' }} />
                  )}

                  {/* Header de la tarjeta */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                    <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 12,
                        background: srv.estado === 'RUNNING' ? 'var(--success-bg)' : 'var(--border-color)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: srv.estado === 'RUNNING' ? 'var(--success)' : 'var(--text-muted)',
                        boxShadow: srv.estado === 'RUNNING' ? '0 0 15px var(--success-bg)' : 'none',
                        border: `1px solid ${srv.estado === 'RUNNING' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(255,255,255,0.05)'}`
                      }}>
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                          <line x1="6" y1="6" x2="6.01" y2="6"></line>
                          <line x1="6" y1="18" x2="6.01" y2="18"></line>
                        </svg>
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
                            {srv.hostname}
                          </span>
                          <span className="badge neutral" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', padding: '2px 8px', fontSize: 11 }}>
                            CT {srv.vmid}
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="2" y1="12" x2="22" y2="12"></line>
                            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                          </svg>
                          {srv.ip_address} <span style={{ opacity: 0.4 }}>•</span> {srv.node} 
                        </div>
                      </div>
                    </div>
                    
                    <span className={`badge ${srv.estado === 'RUNNING' ? 'success' : 'neutral'}`} style={{
                      padding: '6px 12px',
                      boxShadow: srv.estado === 'RUNNING' ? '0 0 10px var(--success-bg)' : 'none',
                      border: srv.estado === 'RUNNING' ? '1px solid rgba(34, 197, 94, 0.2)' : '1px solid var(--border-color)',
                      textTransform: 'capitalize'
                    }}>
                      <span className="badge-dot" style={{
                        boxShadow: srv.estado === 'RUNNING' ? '0 0 8px var(--success)' : 'none',
                        animation: srv.estado === 'RUNNING' ? 'pulse 2s infinite' : 'none'
                      }}></span>
                      {srv.estado === 'RUNNING' ? 'Running' : srv.estado.toLowerCase()}
                    </span>
                  </div>

                  {snap ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <GaugeBar
                        value={snap.cpu_usage_percent}
                        max={100}
                        color="green"
                        label={<>CPU <span style={{ opacity: 0.5, fontWeight: 400, fontSize: 12, marginLeft: 4 }}> {snap.cpu_usage_percent.toFixed(2)}% / {srv.vcpus} vCPU{srv.vcpus > 1 ? 's' : ''}</span></>}
                        icon={
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
                            <rect x="9" y="9" width="6" height="6"></rect>
                            <line x1="9" y1="1" x2="9" y2="4"></line>
                            <line x1="15" y1="1" x2="15" y2="4"></line>
                            <line x1="9" y1="20" x2="9" y2="23"></line>
                            <line x1="15" y1="20" x2="15" y2="23"></line>
                            <line x1="20" y1="9" x2="23" y2="9"></line>
                            <line x1="20" y1="14" x2="23" y2="14"></line>
                            <line x1="1" y1="9" x2="4" y2="9"></line>
                            <line x1="1" y1="14" x2="4" y2="14"></line>
                          </svg>
                        }
                      />
                      <GaugeBar
                        value={snap.ram_usage_mb}
                        max={srv.ram_max_mb}
                        color="blue"
                        label={<>RAM <span style={{ opacity: 0.5, fontWeight: 400, fontSize: 12, marginLeft: 4 }}> {snap.ram_usage_mb.toFixed(2)} / {srv.ram_max_mb} MB</span></>}
                        icon={
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--info)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="4" y1="9" x2="20" y2="9"></line>
                            <line x1="4" y1="15" x2="20" y2="15"></line>
                            <line x1="10" y1="3" x2="8" y2="21"></line>
                            <line x1="16" y1="3" x2="14" y2="21"></line>
                          </svg>
                        }
                      />
                      <GaugeBar
                        value={snap.disk_usage_gb}
                        max={srv.disk_max_real_gb || srv.disk_max_gb}
                        color="purple"
                        label={<>Disco <span style={{ opacity: 0.5, fontWeight: 400, fontSize: 12, marginLeft: 4 }}> {snap.disk_usage_gb.toFixed(2)} / {(srv.disk_max_real_gb || srv.disk_max_gb).toFixed(2)} GB</span></>}
                        icon={
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M22 12A10 10 0 1 1 12 2a10 10 0 0 1 10 10z"></path>
                            <path d="M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0 -6 0"></path>
                          </svg>
                        }
                      />
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center',
                        marginTop: 12, 
                        paddingTop: 16,
                        borderTop: '1px solid var(--border-color)',
                        fontSize: 12, 
                        color: 'var(--text-muted)' 
                      }}>
                        <div style={{ display: 'flex', gap: 16 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>
                            {fmtBytes(snap.net_out_bytes)}
                          </span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><polyline points="19 12 12 19 5 12"></polyline></svg>
                            {fmtBytes(snap.net_in_bytes)}
                          </span>
                        </div>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                          {fmtTime(snap.timestamp)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-muted)', fontSize: 13, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                      Sin datos — capturá una métrica
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Panel de historial — aparece al seleccionar un servicio */}
          {seleccionado && (
            <div className="card fade-in">
              <div className="card-header">
                <h3 className="card-title">
                  Historial — {seleccionado.hostname || `VMID ${seleccionado.vmid}`}
                  <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 8 }}>
                    (últimos {historial.length} puntos)
                  </span>
                </h3>
                <button className="btn btn-secondary btn-sm" onClick={() => setSeleccionado(null)}>✕</button>
              </div>

              {historial.length < 2 ? (
                <div className="empty-state" style={{ padding: 24 }}>
                  <p className="empty-state-text">
                    Se necesitan al menos 2 capturas para mostrar el gráfico.
                    {isAdmin && ' Hacé clic en "Actualizar" algunas veces.'}
                  </p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                  {/* CPU */}
                  <div>
                    <div className="stat-label" style={{ marginBottom: 12 }}>CPU (%)</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={historial}>
                        <defs>
                          <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                        <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                        <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} unit="%" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="cpu_usage_percent" name="CPU" stroke="#22c55e" fill="url(#cpuGrad)" strokeWidth={2} dot={false} unit="%" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  {/* RAM */}
                  <div>
                    <div className="stat-label" style={{ marginBottom: 12 }}>RAM (MB)</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={historial}>
                        <defs>
                          <linearGradient id="ramGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                        <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                        <YAxis domain={[0, seleccionado.ram_max_mb]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} unit=" MB" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="ram_usage_mb" name="RAM" stroke="#3b82f6" fill="url(#ramGrad)" strokeWidth={2} dot={false} unit=" MB" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Disco */}
                  <div>
                    <div className="stat-label" style={{ marginBottom: 12 }}>Disco (GB)</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={historial}>
                        <defs>
                          <linearGradient id="diskGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#a855f7" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                        <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                        <YAxis domain={[0, seleccionado.disk_max_gb]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} unit=" GB" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="disk_usage_gb" name="Disco" stroke="#a855f7" fill="url(#diskGrad)" strokeWidth={2} dot={false} unit=" GB" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Red */}
                  <div>
                    <div className="stat-label" style={{ marginBottom: 12 }}>Red (bytes acumulados)</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={historial}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                        <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                        <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickFormatter={v => fmtBytes(v)} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line type="monotone" dataKey="net_in_bytes"  name="Entrada" stroke="#f59e0b" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="net_out_bytes" name="Salida"  stroke="#ec4899" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
