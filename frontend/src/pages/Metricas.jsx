import { useState, useEffect, useCallback } from 'react';
import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { RefreshCw, Activity, Cpu, MemoryStick, HardDrive, Boxes, X } from 'lucide-react';
import { getResumenMetricas, capturarMetricas, getHistorialMetricas } from '../services/api';
import { PageHead, StatusPill, Meter, Empty } from '../components/ui';

const fmtTime = (iso) => {
  if (!iso) return '';
  const norm = typeof iso === 'string' && !iso.endsWith('Z') && !iso.includes('+') ? iso + 'Z' : iso;
  const d = new Date(norm);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
};

const fmtBytes = (b) => {
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  if (b >= 1e3) return `${(b / 1e3).toFixed(0)} KB`;
  return `${b} B`;
};

const GaugeBar = ({ value, max, label }) => {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ marginBottom: 'var(--space-3)' }}>
      <div className="row between" style={{ marginBottom: 5 }}>
        <span className="card-meta">{label}</span>
        <span className="tabnum" style={{ fontSize: 12, fontWeight: 600 }}>{pct.toFixed(1)} %</span>
      </div>
      <Meter value={value} max={max} />
    </div>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--color-surface)', border: '1px solid var(--color-divider)',
      borderRadius: 'var(--radius-md)', padding: '9px 12px', fontSize: 12,
    }}>
      <p style={{ color: 'var(--text-soft)', marginBottom: 4 }}>{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color, margin: '2px 0' }}>
          {p.name}: <strong>{p.value?.toFixed(2)}{p.unit || ''}</strong>
        </p>
      ))}
    </div>
  );
};

export default function Metricas({ user }) {
  const [resumen, setResumen] = useState([]);
  const [seleccionado, setSeleccionado] = useState(null);
  const [historial, setHistorial] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [capturando, setCapturando] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

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

  const fetchHistorial = useCallback(async (id) => {
    try {
      const { data } = await getHistorialMetricas(id, 60);
      setHistorial(data.map((s) => ({ ...s, time: fmtTime(s.timestamp) })));
    } catch {
      setHistorial([]);
    }
  }, []);

  useEffect(() => {
    fetchResumen();
    if (!autoRefresh) return;
    const id = setInterval(fetchResumen, 30000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchResumen]);

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

  // KPIs derivados de los snapshots por servicio (no hay serie agregada de clúster).
  const conSnap = resumen.filter((s) => s.ultimo_snapshot);
  const cpuAvg = conSnap.length ? conSnap.reduce((a, s) => a + s.ultimo_snapshot.cpu_usage_percent, 0) / conSnap.length : 0;
  const ramUso = conSnap.reduce((a, s) => a + s.ultimo_snapshot.ram_usage_mb, 0);
  const ramMax = resumen.reduce((a, s) => a + (s.ram_max_mb || 0), 0);
  const diskUso = conSnap.reduce((a, s) => a + s.ultimo_snapshot.disk_usage_gb, 0);
  const activos = resumen.filter((s) => s.estado === 'RUNNING').length;

  const KPIS = [
    { label: 'CPU promedio', valor: `${cpuAvg.toFixed(0)} %`, icon: Cpu, tone: 'accent' },
    { label: 'RAM en uso', valor: `${(ramUso / 1024).toFixed(1)} / ${(ramMax / 1024).toFixed(1)} GB`, icon: MemoryStick, tone: 'ok' },
    { label: 'Disco en uso', valor: `${diskUso.toFixed(1)} GB`, icon: HardDrive, tone: 'warn' },
    { label: 'Servicios activos', valor: `${activos} / ${resumen.length}`, icon: Boxes, tone: 'accent' },
  ];

  return (
    <div className="fade-in">
      <PageHead
        title="Métricas"
        subtitle={`Observabilidad de recursos y servicios en uso.${lastUpdate ? ` · Actualizado ${fmtTime(lastUpdate.toISOString())}` : ''}`}
      >
        <label className="row gap-2" style={{ fontSize: 13, color: 'var(--text-soft)', cursor: 'pointer' }}>
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} style={{ accentColor: 'var(--color-accent)' }} />
          Auto-refresh (30s)
        </label>
        {isAdmin && (
          <button className="btn btn-secondary" onClick={handleCapturar} disabled={capturando}>
            <RefreshCw size={15} /> {capturando ? 'Actualizando…' : 'Actualizar'}
          </button>
        )}
      </PageHead>

      {cargando ? (
        <div className="card"><Empty icon={<Activity size={22} />}>Cargando métricas…</Empty></div>
      ) : resumen.length === 0 ? (
        <div className="card">
          <Empty icon={<Activity size={22} />}>
            No hay servicios con métricas disponibles.
            {isAdmin && (
              <div style={{ marginTop: 'var(--space-3)' }}>
                <button className="btn btn-primary" onClick={handleCapturar}>Capturar primera métrica</button>
              </div>
            )}
          </Empty>
        </div>
      ) : (
        <>
          <div className="grid cols-4 mb-6">
            {KPIS.map((k) => (
              <div className={`stat stat--${k.tone}`} key={k.label}>
                <div className="stat__kicker">
                  <span className={`stat__glyph ${k.tone === 'ok' ? 'ok' : k.tone === 'warn' ? 'warn' : ''}`}><k.icon size={16} /></span> {k.label}
                </div>
                <div className="stat__value tabnum">{k.valor}</div>
              </div>
            ))}
          </div>

          <div className="grid auto top mb-6">
            {resumen.map((srv) => {
              const snap = srv.ultimo_snapshot;
              const sel = seleccionado?.servicio_id === srv.servicio_id;
              const running = srv.estado === 'RUNNING';
              return (
                <div
                  key={srv.servicio_id}
                  className="card"
                  style={{ cursor: 'pointer', borderColor: sel ? 'var(--color-accent)' : undefined }}
                  onClick={() => setSeleccionado(srv)}
                >
                  <div className="row between" style={{ alignItems: 'flex-start' }}>
                    <div className="col" style={{ minWidth: 0 }}>
                      <div className="row gap-2">
                        <span className="cell-strong">{srv.hostname}</span>
                        <span className="tag neutral">CT {srv.vmid}</span>
                      </div>
                      <span className="card-meta">{srv.ip_address} · {srv.node}</span>
                    </div>
                    <StatusPill kind={running ? 'ok' : 'off'}>{running ? 'Running' : srv.estado.toLowerCase()}</StatusPill>
                  </div>

                  {snap ? (
                    <div style={{ marginTop: 'var(--space-3)' }}>
                      <GaugeBar value={snap.cpu_usage_percent} max={100} label={`CPU · ${snap.cpu_usage_percent.toFixed(1)}% / ${srv.vcpus} vCPU`} />
                      <GaugeBar value={snap.ram_usage_mb} max={srv.ram_max_mb} label={`RAM · ${snap.ram_usage_mb.toFixed(0)} / ${srv.ram_max_mb} MB`} />
                      <GaugeBar value={snap.disk_usage_gb} max={srv.disk_max_real_gb || srv.disk_max_gb} label={`Disco · ${snap.disk_usage_gb.toFixed(1)} / ${(srv.disk_max_real_gb || srv.disk_max_gb).toFixed(1)} GB`} />
                      <div className="row between card-meta" style={{ marginTop: 'var(--space-2)', paddingTop: 'var(--space-2)', borderTop: '1px solid var(--color-divider)' }}>
                        <span>↑ {fmtBytes(snap.net_out_bytes)} · ↓ {fmtBytes(snap.net_in_bytes)}</span>
                        <span>{fmtTime(snap.timestamp)}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="card-meta" style={{ marginTop: 'var(--space-2)' }}>Sin datos — capturá una métrica.</div>
                  )}
                </div>
              );
            })}
          </div>

          {seleccionado && (
            <div className="card fade-in">
              <div className="card-header">
                <div className="card-title">
                  Historial — {seleccionado.hostname || `VMID ${seleccionado.vmid}`}
                  <span className="card-meta" style={{ marginLeft: 8 }}>(últimos {historial.length} puntos)</span>
                </div>
                <button className="btn-icon" onClick={() => setSeleccionado(null)} aria-label="Cerrar"><X size={16} /></button>
              </div>

              {historial.length < 2 ? (
                <Empty icon={<Activity size={20} />}>
                  Se necesitan al menos 2 capturas para mostrar el gráfico.
                  {isAdmin && ' Hacé clic en "Actualizar" algunas veces.'}
                </Empty>
              ) : (
                <div className="grid cols-2">
                  <Grafico titulo="CPU (%)" data={historial} dataKey="cpu_usage_percent" name="CPU" unit="%" color="var(--st-ok)" domain={[0, 100]} />
                  <Grafico titulo="RAM (MB)" data={historial} dataKey="ram_usage_mb" name="RAM" unit=" MB" color="var(--color-accent)" domain={[0, seleccionado.ram_max_mb]} />
                  <Grafico titulo="Disco (GB)" data={historial} dataKey="disk_usage_gb" name="Disco" unit=" GB" color="var(--st-warn)" domain={[0, seleccionado.disk_max_gb]} />
                  <div>
                    <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Red (bytes acumulados)</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={historial}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-divider)" />
                        <XAxis dataKey="time" tick={{ fill: 'var(--text-faint)', fontSize: 10 }} />
                        <YAxis tick={{ fill: 'var(--text-faint)', fontSize: 10 }} tickFormatter={fmtBytes} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line type="monotone" dataKey="net_in_bytes" name="Entrada" stroke="var(--st-warn)" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="net_out_bytes" name="Salida" stroke="var(--color-accent)" strokeWidth={2} dot={false} />
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

function Grafico({ titulo, data, dataKey, name, unit, color, domain }) {
  return (
    <div>
      <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>{titulo}</div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-divider)" />
          <XAxis dataKey="time" tick={{ fill: 'var(--text-faint)', fontSize: 10 }} />
          <YAxis domain={domain} tick={{ fill: 'var(--text-faint)', fontSize: 10 }} unit={unit} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey={dataKey} name={name} stroke={color} fill={color} fillOpacity={0.12} strokeWidth={2} dot={false} unit={unit} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
