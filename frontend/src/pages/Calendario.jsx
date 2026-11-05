import { useRef, useState } from 'react';
import { getCalendario, guardarCalendario } from '../services/api';
import { mensajeError } from '../utils/errors';
import { PageHead } from '../components/ui';
import { CalendarDays, ChevronLeft, ChevronRight, Info, Save, Trash2 } from 'lucide-react';
import { ANIO_LECTIVO_MINIMO, ANIO_LECTIVO_MAXIMO, FECHA_MINIMA, anioLectivoValido, vigenciaInicial } from '../utils/vigencia';

const MODALIDADES = [
  ['primer_cuatrimestre', 'primer cuatrimestre', 'Primer cuatrimestre', 'Primera parte del año lectivo.'],
  ['segundo_cuatrimestre', 'segundo cuatrimestre', 'Segundo cuatrimestre', 'Segunda parte del año lectivo.'],
  ['anual', 'ciclo anual', 'Ciclo lectivo anual', 'Período completo de actividades.'],
];
const emptyPeriods = () => Object.fromEntries(MODALIDADES.map(([type]) => [type, { desde: '', hasta: '' }]));
const dateLabel = (date) => date.split('-').reverse().join('/');
const periodError = (period) => {
  if (!period.desde && !period.hasta) return '';
  if (!period.desde || !period.hasta) return 'Completá el inicio y el fin, o quitá ambas fechas.';
  if (period.desde < FECHA_MINIMA || period.hasta < FECHA_MINIMA) return `Elegí fechas de ${ANIO_LECTIVO_MINIMO} en adelante.`;
  if (period.desde > period.hasta) return 'La fecha final debe ser posterior o igual a la inicial.';
  return '';
};

export default function Calendario() {
  const [year, setYear] = useState(String(vigenciaInicial().anio_lectivo));
  const [loadedYear, setLoadedYear] = useState(null);
  const [revision, setRevision] = useState(0);
  const [zone, setZone] = useState('');
  const [periods, setPeriods] = useState(emptyPeriods);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const key = useRef(crypto.randomUUID());
  const validYear = anioLectivoValido(year);
  const selectedLoaded = validYear && loadedYear === Number(year);
  const first = periods.primer_cuatrimestre;
  const second = periods.segundo_cuatrimestre;
  const overlap = first.desde && first.hasta && second.desde && second.hasta
    && !periodError(first) && !periodError(second) && first.desde <= second.hasta && second.desde <= first.hasta;
  const invalidPeriods = Object.values(periods).some((period) => Boolean(periodError(period)));
  const configured = Object.values(periods).filter((period) => period.desde && period.hasta && !periodError(period)).length;
  const changeYear = (value) => { setYear(value); setError(''); setNotice(''); };
  const load = async () => {
    if (busy || !validYear) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const { data } = await getCalendario(year);
      if (Number(data.anio) !== Number(year)) {
        setError('El calendario recibido no coincide con el año elegido. Volvé a consultar.'); return;
      }
      const next = emptyPeriods();
      data.periodos.forEach((p) => { if (next[p.tipo]) next[p.tipo] = { desde: p.desde, hasta: p.hasta }; });
      setPeriods(next); setRevision(data.revision); setLoadedYear(Number(year)); setZone(data.zona_horaria); setStale(false);
      key.current = crypto.randomUUID();
    } catch (err) {
      if (err.response?.status === 404) {
        setPeriods(emptyPeriods()); setRevision(0); setLoadedYear(Number(year)); setStale(false); setZone('');
        setNotice('Este año no tiene calendario. Completá las modalidades que corresponden.');
        key.current = crypto.randomUUID();
      } else setError(mensajeError(err, 'No se pudo consultar el calendario.'));
    } finally { setBusy(false); }
  };
  const edit = (type, field, value) => {
    setPeriods((current) => ({ ...current, [type]: { ...current[type], [field]: value } }));
    key.current = crypto.randomUUID(); setNotice(''); setError('');
  };
  const clearPeriod = (type) => {
    setPeriods((current) => ({ ...current, [type]: { desde: '', hasta: '' } }));
    key.current = crypto.randomUUID(); setNotice(''); setError('');
  };
  const save = async (event) => {
    event.preventDefault();
    if (busy || stale || !selectedLoaded) return;
    if (invalidPeriods || overlap) {
      setError('Revisá las fechas señaladas antes de guardar.'); return;
    }
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
    <PageHead kicker="Administración" title="Calendario lectivo" subtitle="Definí los períodos que las cátedras podrán elegir al solicitar un servicio." />
    <div className="calendar-toolbar card">
      <div className="calendar-toolbar__label"><CalendarDays size={22} aria-hidden="true" /><div>
        <label htmlFor="calendar-year">Año lectivo</label>
        <p>Disponible desde {ANIO_LECTIVO_MINIMO}.</p>
      </div></div>
      <div className="calendar-year-controls">
        <button type="button" className="btn-icon" aria-label="Año anterior"
          disabled={busy || !validYear || Number(year) <= ANIO_LECTIVO_MINIMO} onClick={() => changeYear(String(Number(year) - 1))}><ChevronLeft size={18} /></button>
        <input id="calendar-year" className="input" type="number" min={ANIO_LECTIVO_MINIMO} max={ANIO_LECTIVO_MAXIMO} value={year}
          aria-invalid={!validYear} aria-describedby={!validYear ? 'calendar-year-error' : undefined}
          onChange={(e) => changeYear(e.target.value)} disabled={busy} />
        <button type="button" className="btn-icon" aria-label="Año siguiente"
          disabled={busy || !validYear || Number(year) >= ANIO_LECTIVO_MAXIMO} onClick={() => changeYear(String(Number(year) + 1))}><ChevronRight size={18} /></button>
      </div>
      <button className="btn btn-secondary" onClick={load} disabled={busy || !validYear}>Consultar año</button>
    </div>
    {!validYear && <p id="calendar-year-error" role="alert" className="callout bad">Elegí un año entre {ANIO_LECTIVO_MINIMO} y {ANIO_LECTIVO_MAXIMO} para configurar el calendario.</p>}
    {error && <p role="alert" className="callout bad">{error}</p>}
    {notice && <p role="status" className="callout">{notice}</p>}
    {busy && <p role="status">Procesando calendario…</p>}
    {loadedYear === null && !busy && <div className="calendar-empty card">
      <CalendarDays size={32} strokeWidth={1.5} aria-hidden="true" />
      <h2>Prepará el calendario de cada año</h2>
      <p>Elegí el año y pulsá «Consultar año» para revisar o completar sus fechas.</p>
    </div>}
    {loadedYear !== null && <form className="calendar-editor" onSubmit={save}>
      <div className="calendar-editor__heading"><div><h2>Períodos de {loadedYear}</h2>
        <p>Completá sólo las modalidades que se utilizarán. Las fechas de inicio y fin están incluidas.</p></div>
        <span className="tag neutral">{configured} de 3 completos</span>
      </div>
      {!selectedLoaded && <p role="status" className="callout">Cambiaste el año seleccionado. Pulsá «Consultar año» para editar su calendario.</p>}
      {stale && <p role="alert" className="callout bad">Otra persona actualizó este calendario. Volvé a consultar el año antes de guardar; tus fechas siguen visibles para que puedas revisarlas.</p>}
      <div className="calendar-period-grid">
        {MODALIDADES.map(([type, label, title, hint]) => {
          const p = periods[type];
          const problem = periodError(p);
          const complete = p.desde && p.hasta && !problem;
          return <fieldset key={type} className="calendar-period card" disabled={busy || !selectedLoaded}>
            <legend className="sr-only">{title}</legend>
            <div className="calendar-period__heading"><h3>{title}</h3>
              <span className={`tag ${problem ? 'warn' : complete ? 'ok' : 'neutral'}`}>{problem ? 'Revisar fechas' : complete ? 'Completo' : 'Sin configurar'}</span>
            </div>
            <p className="calendar-period__hint">{hint}</p>
            <div className="calendar-period__dates">
              <label htmlFor={`${type}-start`}>Inicio
                <input id={`${type}-start`} aria-label={`Inicio del ${label}`} className="input" type="date" min={FECHA_MINIMA}
                  aria-invalid={Boolean(problem)} aria-describedby={problem ? `${type}-error` : undefined}
                  value={p.desde} onChange={(e) => edit(type, 'desde', e.target.value)} />
              </label>
              <label htmlFor={`${type}-end`}>Fin
                <input id={`${type}-end`} aria-label={`Fin del ${label}`} className="input" type="date" min={p.desde && p.desde >= FECHA_MINIMA ? p.desde : FECHA_MINIMA}
                  aria-invalid={Boolean(problem)} aria-describedby={problem ? `${type}-error` : undefined}
                  value={p.hasta} onChange={(e) => edit(type, 'hasta', e.target.value)} />
              </label>
            </div>
            {problem ? <p id={`${type}-error`} role="alert" className="calendar-period__error">{problem}</p>
              : <p className="calendar-period__summary">{complete ? `Del ${dateLabel(p.desde)} al ${dateLabel(p.hasta)}` : 'Esta modalidad no estará disponible hasta completar sus fechas.'}</p>}
            <button type="button" className="btn btn-ghost btn-sm calendar-period__clear" disabled={!p.desde && !p.hasta} onClick={() => clearPeriod(type)}>
              <Trash2 size={13} aria-hidden="true" /> Quitar fechas
            </button>
          </fieldset>;
        })}
      </div>
      {overlap && <p role="alert" className="callout bad">Los cuatrimestres se superponen. El primero debe finalizar antes de que comience el segundo.</p>}
      <div className="calendar-editor__note"><Info size={17} aria-hidden="true" /><div>
        <p>Los cuatrimestres no deben superponerse. El ciclo anual puede incluir ambos.</p>
        <p>Los pedidos ya aprobados conservan sus fechas.{zone && ` Zona horaria: ${zone}.`}</p>
      </div></div>
      <div className="calendar-editor__actions"><span>Los cambios se aplican al guardar.</span>
        <button className="btn btn-primary" type="submit" disabled={busy || stale || !selectedLoaded || invalidPeriods || Boolean(overlap)}><Save size={16} aria-hidden="true" /> Guardar calendario</button>
      </div>
    </form>}
  </div>;
}
