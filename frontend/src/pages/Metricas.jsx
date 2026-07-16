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

const GaugeBar = ({ value, max, color, label }) => {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const colorClass = pct > 85 ? 'red' : pct > 60 ? 'orange' : color;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span className="stat-label">{label}</span>
        <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>
          {pct.toFixed(2)}%
        </span>
      </div>
      <div className="progress-bar">
        <div className={`progress-fill ${colorClass}`} style={{ width: `${pct}%`, transition: 'width 0.5s ease' }} />
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
                    borderColor: isSelected ? 'var(--accent)' : undefined,
                    borderWidth: isSelected ? 2 : 1,
                    transition: 'border-color 0.2s',
                  }}
                  onClick={() => handleSeleccionar(srv)}
                >
                  {/* Header de la tarjeta */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                        {srv.hostname || `VMID ${srv.vmid}`}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                        CT {srv.vmid} · {srv.node}
                      </div>
                      <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: 12 }}>
                        <span style={{ color: 'var(--accent)' }}>
                          ⚡ {srv.vcpus} vCPU{srv.vcpus > 1 ? 's' : ''}
                        </span>
                        {srv.ip_address && (
                          <span style={{ color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                            🌐 {srv.ip_address}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className={`badge ${srv.estado === 'RUNNING' ? 'success' : 'neutral'}`}>
                      <span className="badge-dot"></span>
                      {srv.estado === 'RUNNING' ? 'running' : srv.estado.toLowerCase()}
                    </span>
                  </div>

                  {snap ? (
                    <>
                      <GaugeBar
                        value={snap.cpu_usage_percent}
                        max={100}
                        color="green"
                        label={`CPU · ${snap.cpu_usage_percent.toFixed(2)}%`}
                      />
                      <GaugeBar
                        value={snap.ram_usage_mb}
                        max={srv.ram_max_mb}
                        color="blue"
                        label={`RAM · ${snap.ram_usage_mb.toFixed(2)} / ${srv.ram_max_mb} MB`}
                      />
                      <GaugeBar
                        value={snap.disk_usage_gb}
                        max={srv.disk_max_real_gb || srv.disk_max_gb}
                        color="purple"
                        label={`Disco · ${snap.disk_usage_gb.toFixed(2)} / ${(srv.disk_max_real_gb || srv.disk_max_gb).toFixed(2)} GB`}
                      />
                      <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                        <span>↑ {fmtBytes(snap.net_out_bytes)}</span>
                        <span>↓ {fmtBytes(snap.net_in_bytes)}</span>
                        <span style={{ marginLeft: 'auto' }}>{fmtTime(snap.timestamp)}</span>
                      </div>
                    </>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '12px 0', color: 'var(--text-muted)', fontSize: 13 }}>
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
