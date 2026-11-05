import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, X } from 'lucide-react';
import { getResumenMetricas, capturarMetricas, getHistorialMetricas } from '../services/api';
import { PageHead, StatusPill, Meter, Empty } from '../components/ui';
import EstadoConsulta from '../components/EstadoConsulta';
const GraficasMetricas = lazy(() => import('../components/GraficasMetricas'));
import useRemoteData from '../hooks/useRemoteData';
import { mensajeError } from '../utils/errors';

const EMPTY = [];
const periods = { hora: 1, dia: 24, semana: 168, trimestre: 2160 };
const states = { running: 'En funcionamiento', stopped: 'Detenido' };
const observed = (sample) => sample?.calidad === 'confirmada';
const number = (value, digits = 1) => Number.isFinite(value) ? value.toFixed(digits) : 'Sin confirmación';
const date = (value) => value ? new Date(value).toLocaleString('es-AR') : 'Sin fecha';
const exactBytes = (value) => {
  if (value === null || value === undefined) return 'Sin intervalo completo';
  try { return `${BigInt(value).toLocaleString('es-AR')} bytes`; } catch { return 'Sin confirmación'; }
};

function Gauge({ value, max, label, unit, estimated }) {
  return <div className="mb-3"><p className="card-meta">{label}: {number(value)} {Number.isFinite(value) && unit}
    {Number.isFinite(max) && ` / ${number(max)} ${unit}${estimated ? ' (límite estimado)' : ''}`}</p>
    {Number.isFinite(value) && Number.isFinite(max) && max > 0 && <Meter value={value} max={max} />}
  </div>;
}

export default function Metricas({ user }) {
  const [selectedId, setSelectedId] = useState(null);
  const [period, setPeriod] = useState('dia');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const submitting = useRef(false);
  const historySection = useRef(null);
  const scrollHistory = useRef(false);
  const scope = `${user?.id || ''}:${user?.rol || ''}`;
  const summary = useRemoteData((options) => getResumenMetricas(options), { key: `metricas:${scope}`,
    refreshMs: autoRefresh ? 30000 : 0, errorMessage: 'No se pudieron consultar las métricas.' });
  const rows = summary.data || EMPTY;
  const selected = rows.find((row) => row.servicio_id === selectedId);
  useEffect(() => {
    if (selectedId && historySection.current) {
      scrollHistory.current = true;
      historySection.current.focus({ preventScroll: true });
    }
  }, [selectedId]);
  const history = useRemoteData((options) => {
    const until = new Date();
    const since = new Date(until.getTime() - periods[period] * 3600000);
    return getHistorialMetricas(selectedId, 500, { desde: since.toISOString(), hasta: until.toISOString(), resolucion: 'auto' }, options);
  }, { key: `historial:${scope}:${selectedId}:${period}`, enabled: Boolean(selected),
    refreshMs: autoRefresh ? 30000 : 0, errorMessage: 'No se pudo consultar el historial de métricas.' });
  const points = history.data || EMPTY;
  useEffect(() => {
    // Esperar al resultado: antes, la sección corta hacía que el navegador
    // limitara el scroll y las gráficas quedaran por debajo de la pantalla.
    if (scrollHistory.current && !history.loading && (history.data !== null || history.error)) {
      scrollHistory.current = false;
      historySection.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' });
    }
  }, [history.loading, history.data, history.error]);
  const current = rows.filter((row) => row.observacion_reciente && observed(row.ultimo_snapshot));
  const cpu = current.map((row) => row.ultimo_snapshot.cpu_usage_percent).filter(Number.isFinite);
  const cpuAverage = cpu.length ? cpu.reduce((sum, value) => sum + value, 0) / cpu.length : null;
  const refresh = () => Promise.all([summary.reload(), history.reload()]);
  const capture = async () => {
    if (submitting.current) return;
    submitting.current = true; setCapturing(true); setActionError(''); setNotice('');
    try {
      const { data } = await capturarMetricas();
      setNotice(data.capturados > 0 ? 'Observaciones confirmadas. Cada minuto conserva una sola muestra por servicio.'
        : 'No se confirmaron observaciones. La falta de datos no significa consumo cero.');
      await refresh();
    } catch (error) { setActionError(mensajeError(error, 'No se pudo completar la captura.')); }
    finally { submitting.current = false; setCapturing(false); }
  };
  const accessibleSummary = useMemo(() => {
    const valid = points.filter(observed);
    const cpus = valid.map((row) => row.cpu_usage_percent).filter(Number.isFinite);
    return `${points.length} puntos seleccionados; ${valid.length} con observación confirmada. ` +
      (cpus.length ? `CPU máxima de los puntos mostrados: ${number(Math.max(...cpus))} %.` : 'CPU sin confirmar.');
  }, [points]);
  return <div className="fade-in">
    <PageHead title="Métricas" subtitle="Observaciones registradas del servicio y su fecha.">
      <label className="row gap-2"><input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />Actualizar vista cada 30 segundos</label>
      <button className="btn btn-secondary" onClick={refresh} disabled={summary.loading}><RefreshCw size={15} /> Actualizar</button>
      {user?.rol === 'admin' && <button className="btn btn-secondary" onClick={capture} disabled={capturing}>
        {capturing ? 'Capturando…' : 'Capturar ahora'}</button>}
    </PageHead>
    {summary.updatedAt && <p className="card-meta">Última consulta confirmada: {date(summary.updatedAt)}.</p>}
    {summary.loading && <p role="status">Cargando métricas…</p>}
    <EstadoConsulta remote={summary} nombre="métricas" />
    {actionError && <p role="alert" className="callout bad">{actionError}</p>}
    {notice && <p role="status">{notice}</p>}
    {summary.data !== null && !summary.loading && !summary.error && rows.length === 0 && <Empty icon={<Activity size={22} />}>No hay servicios con métricas disponibles.</Empty>}
    {rows.length > 0 && <>
      <div className="callout"><p>CPU promedio con observación reciente: <strong>{number(cpuAverage)} {Number.isFinite(cpuAverage) && '%'}</strong>.
        {' '}{current.length} de {rows.length} servicios con datos recientes. Los demás conservan su fecha y calidad de observación.</p></div>
      <div className="grid auto top mb-6">{rows.map((row) => {
        const sample = row.ultimo_snapshot;
        const confirmed = observed(sample);
        return <article className="card" key={row.servicio_id} data-servicio-id={row.servicio_id}>
          <div className="row between"><h2 className="card-title">{row.nombre || row.hostname || `Servicio #${row.servicio_id}`}</h2>
            <StatusPill kind={confirmed && row.observacion_reciente ? sample.aplicacion_saludable === false ? 'bad' : row.estado_observado === 'stopped' ? 'off' : 'ok' : 'warn'}>
              {confirmed ? row.observacion_reciente ? sample.aplicacion_saludable === false ? 'Fallo comprobado' : states[row.estado_observado] || 'Observado' : 'Datos anteriores' : 'Sin confirmar'}</StatusPill></div>
          <p className="card-meta">{sample ? `Último intento: ${date(sample.timestamp)}` : 'Todavía no hay observaciones.'}</p>
          {sample && !confirmed && <p>La última consulta no confirmó el estado ni el consumo del servicio.</p>}
          {confirmed && sample.aplicacion_saludable === false && <p>La comprobación local del servicio falló. Estado observado del recurso: {states[row.estado_observado] || 'sin confirmar'}.</p>}
          {confirmed && sample.aplicacion_saludable == null && <p className="card-meta">La salud del servicio no está confirmada.</p>}
          {sample && confirmed && <>
            <Gauge label="CPU" value={sample.cpu_usage_percent} max={100} unit="%" />
            <Gauge label="RAM" value={sample.ram_usage_mb} max={sample.ram_max_mb ?? row.ram_max_mb} unit="MiB" estimated={sample.ram_max_mb == null} />
            <Gauge label="Disco" value={sample.disk_usage_gb} max={sample.disk_max_bytes != null ? sample.disk_max_bytes / 1024**3 : row.disk_max_gb} unit="GiB" estimated={sample.disk_max_bytes == null} />
            <p className="card-meta">Tráfico del intervalo: entrada {exactBytes(sample.net_in_delta_exacto ?? sample.net_in_delta)}; salida {exactBytes(sample.net_out_delta_exacto ?? sample.net_out_delta)}.</p>
          </>}
          <button className="btn btn-secondary" onClick={() => setSelectedId(row.servicio_id)}>Ver historial de {row.nombre || row.hostname || `Servicio #${row.servicio_id}`}</button>
        </article>;
      })}</div>
    </>}
    {selected && <section className="card" ref={historySection} tabIndex={-1} aria-label="Historial de métricas" aria-busy={history.loading}
      data-servicio-id={selectedId} data-periodo={period}>
      <div className="row between"><h2>Historial · {selected.nombre || selected.hostname}</h2>
        <button className="btn-icon" aria-label="Cerrar historial" onClick={() => setSelectedId(null)}><X size={16} /></button></div>
      <label htmlFor="periodo-metricas">Período del historial</label>
      <select id="periodo-metricas" className="input" value={period} onChange={(e) => {
        scrollHistory.current = true; setPeriod(e.target.value);
      }}>
        <option value="hora">Última hora</option><option value="dia">Últimas 24 horas</option>
        <option value="semana">Últimos siete días</option><option value="trimestre">Últimos noventa días</option>
      </select>
      <EstadoConsulta remote={history} nombre="historial" mostrarCarga />
      {history.updatedAt && <p className="card-meta">Historial consultado: {date(history.updatedAt)}.</p>}
      <p>Se muestran hasta 500 muestras reales, seleccionadas por bloques. Los huecos no indican consumo cero. El detalle anterior a noventa días se conserva como resumen de consumo.</p>
      {points.length > 0 && <>
        <p role="status" aria-label="Resumen textual del historial">{accessibleSummary}</p>
        <p aria-label="Intervalo de observaciones">Desde {points[0].timestamp} hasta {points[points.length - 1].timestamp} (UTC).</p>
        <Suspense fallback={<p role="status">Preparando gráficas; la tabla y el resumen ya están disponibles.</p>}><GraficasMetricas points={points} /></Suspense>
        <details><summary>Consultar tabla de observaciones</summary><div style={{ overflowX: 'auto' }}>
          <table><caption>Observaciones y tráfico del intervalo, con instantes UTC</caption><thead><tr>
            <th>Instante UTC</th><th>Calidad</th><th>CPU %</th><th>RAM MiB</th><th>Entrada</th><th>Salida</th>
          </tr></thead><tbody>{points.map((row) => <tr key={row.id}>
            <td>{row.timestamp}</td><td>{observed(row) ? 'Confirmada' : 'Sin confirmar'}</td>
            <td>{number(row.cpu_usage_percent)}</td><td>{number(row.ram_usage_mb)}</td>
            <td>{exactBytes(row.net_in_delta_exacto ?? row.net_in_delta)}</td><td>{exactBytes(row.net_out_delta_exacto ?? row.net_out_delta)}</td>
          </tr>)}</tbody></table></div></details>
      </>}
      {history.data !== null && !history.loading && !history.error && !points.length && <p>No hay observaciones en este período.</p>}
    </section>}
  </div>;
}
