import { useRef, useState } from 'react';
import { getCalendario, guardarCalendario } from '../services/api';
import { mensajeError } from '../utils/errors';
import { PageHead } from '../components/ui';

const MODALIDADES = [
  ['primer_cuatrimestre', 'primer cuatrimestre'],
  ['segundo_cuatrimestre', 'segundo cuatrimestre'],
  ['anual', 'ciclo anual'],
];
const emptyPeriods = () => Object.fromEntries(MODALIDADES.map(([type]) => [type, { desde: '', hasta: '' }]));

export default function Calendario() {
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [loadedYear, setLoadedYear] = useState(null);
  const [revision, setRevision] = useState(0);
  const [zone, setZone] = useState('');
  const [periods, setPeriods] = useState(emptyPeriods);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const key = useRef(crypto.randomUUID());
  const load = async () => {
    if (busy || !/^\d{4}$/.test(year) || Number(year) < 1900 || Number(year) > 9998) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const { data } = await getCalendario(year);
      const next = emptyPeriods();
      data.periodos.forEach((p) => { if (next[p.tipo]) next[p.tipo] = { desde: p.desde, hasta: p.hasta }; });
      setPeriods(next); setRevision(data.revision); setLoadedYear(Number(year)); setZone(data.zona_horaria); setStale(false);
      key.current = crypto.randomUUID();
    } catch (err) {
      if (err.response?.status === 404) {
        setPeriods(emptyPeriods()); setRevision(0); setLoadedYear(Number(year)); setStale(false);
        setNotice('Este año no tiene calendario. Completá las modalidades que corresponden.');
        key.current = crypto.randomUUID();
      } else setError(mensajeError(err, 'No se pudo consultar el calendario.'));
    } finally { setBusy(false); }
  };
  const edit = (type, field, value) => {
    setPeriods((current) => ({ ...current, [type]: { ...current[type], [field]: value } }));
    key.current = crypto.randomUUID(); setNotice('');
  };
  const save = async (event) => {
    event.preventDefault();
    if (busy || stale || loadedYear !== Number(year)) return;
    const next = [];
    for (const [type] of MODALIDADES) {
      const p = periods[type];
      if (!p.desde && !p.hasta) continue;
      if (!p.desde || !p.hasta || p.desde > p.hasta) {
        setError('Completá ambas fechas de cada modalidad y ordenalas antes de guardar.'); return;
      }
      next.push({ tipo: type, ...p });
    }
    setBusy(true); setError(''); setNotice('');
    try {
      const { data } = await guardarCalendario(year, { revision_esperada: revision, periodos: next }, key.current);
      setRevision(data.revision); setZone(data.zona_horaria); key.current = crypto.randomUUID();
      setNotice('Calendario guardado. Las aprobaciones anteriores conservan sus fechas.');
    } catch (err) {
      setError(mensajeError(err, 'No se pudo guardar. Conservamos las fechas ingresadas.'));
      if (err.response?.data?.detail?.codigo === 'calendario_desactualizado') setStale(true);
    } finally { setBusy(false); }
  };
  return <div className="fade-in">
    <PageHead kicker="Administración" title="Calendario lectivo" subtitle="Fechas por año. Las modalidades sin fechas quedan sin configurar." />
    <div className="row gap-2" style={{ marginBottom: 16 }}>
      <label htmlFor="calendar-year">Año lectivo</label>
      <input id="calendar-year" type="number" min="1900" max="9998" value={year} onChange={(e) => setYear(e.target.value)} disabled={busy} />
      <button className="btn btn-secondary" onClick={load} disabled={busy}>Consultar año</button>
    </div>
    {error && <p role="alert" className="callout bad">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Procesando calendario…</p>}
    {loadedYear !== null && <form className="card" onSubmit={save} style={{ padding: 20 }}>
      <p>Calendario {loadedYear}, revisión {revision}. {zone && `Fechas locales de ${zone}.`}</p>
      {MODALIDADES.map(([type, label]) => <fieldset key={type} disabled={busy || loadedYear !== Number(year)} style={{ marginBottom: 16 }}>
        <legend>{label}</legend>
        <label htmlFor={`${type}-start`}>Inicio del {label}</label>
        <input id={`${type}-start`} type="date" value={periods[type].desde} onChange={(e) => edit(type, 'desde', e.target.value)} />
        <label htmlFor={`${type}-end`}>Fin del {label}</label>
        <input id={`${type}-end`} type="date" value={periods[type].hasta} onChange={(e) => edit(type, 'hasta', e.target.value)} />
      </fieldset>)}
      <p>Los cuatrimestres no deben solaparse. El ciclo anual puede incluirlos.</p>
      <button className="btn btn-primary" type="submit" disabled={busy || stale || loadedYear !== Number(year)}>Guardar calendario</button>
    </form>}
  </div>;
}
