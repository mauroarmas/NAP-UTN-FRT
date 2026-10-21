import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function GraficasMetricas({ points }) {
  const data = useMemo(() => {
    const intervals = points.slice(1).map((row, i) => new Date(row.timestamp) - new Date(points[i].timestamp));
    const positive = intervals.filter((value) => value > 0).sort((a, b) => a - b);
    const step = positive.length ? positive[Math.floor(positive.length / 2)] : 60000;
    return points.flatMap((row, i) => {
      const timestamp = new Date(row.timestamp).getTime();
      const normalized = { ...row, time: timestamp };
      if (row.calidad !== 'confirmada') for (const key of ['cpu_usage_percent','ram_usage_mb','net_in_delta','net_out_delta']) normalized[key] = null;
      return i && timestamp - new Date(points[i-1].timestamp).getTime() > step * 1.5
        ? [{ time: new Date(points[i-1].timestamp).getTime() + step }, normalized] : [normalized];
    });
  }, [points]);
  return <div className="grid cols-2" aria-label="Gráficas de observaciones">
    {[['CPU (%)', 'cpu_usage_percent'], ['RAM (MiB)', 'ram_usage_mb'], ['Entrada por intervalo (bytes aproximados)', 'net_in_delta'], ['Salida por intervalo (bytes aproximados)', 'net_out_delta']].map(([title, key]) => <section key={key}>
      <h3 className="section-label">{title}</h3>
      <ResponsiveContainer width="100%" height={180}><LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey="time" domain={['dataMin','dataMax']} tickFormatter={(value) => new Date(value).toLocaleTimeString('es-AR')} />
        <YAxis domain={key === 'cpu_usage_percent' ? [0,100] : [0,'auto']} tickFormatter={(value) =>
          key.startsWith('net_') ? new Intl.NumberFormat('es-AR', { notation: 'compact', maximumFractionDigits: 1 }).format(value) : value} />
        <Tooltip labelFormatter={(value) => new Date(value).toLocaleString('es-AR')} />
        <Line dataKey={key} name={title} type="linear" stroke="var(--color-accent)" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
      </LineChart></ResponsiveContainer>
    </section>)}
  </div>;
}
