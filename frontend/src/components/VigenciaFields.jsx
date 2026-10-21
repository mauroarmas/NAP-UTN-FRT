import { useEffect, useState } from 'react';
import { getCalendario } from '../services/api';
import { mensajeError } from '../utils/errors';

const TYPES = [
  ['primer_cuatrimestre', '1° Cuatrimestre'], ['segundo_cuatrimestre', '2° Cuatrimestre'],
  ['anual', 'Ciclo Lectivo Anual'], ['personalizado', 'Rango Personalizado'],
];

export default function VigenciaFields({ value, onChange, onValid }) {
  const [calendar, setCalendar] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const academic = value.tipo !== 'personalizado';
  const year = String(value.anio_lectivo || '');
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setCalendar(null); setError('');
    if (!academic || !/^\d{4}$/.test(year)) { setLoading(false); return () => { active = false; }; }
    setLoading(true);
    getCalendario(year, controller.signal).then(({ data }) => {
      if (active && String(data.anio) === year) setCalendar(data);
      else if (active) setError('El año recibido no coincide con el elegido. Volvé a consultar.');
    }).catch((err) => {
      if (active) setError(mensajeError(err, 'El año elegido no tiene calendario configurado'));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [academic, year]);
  const period = calendar?.periodos?.find((p) => p.tipo === value.tipo);
  const valid = academic ? Boolean(!loading && !error && period && String(calendar?.anio) === year)
    : Boolean(value.desde && value.hasta && value.desde <= value.hasta);
  useEffect(() => { onValid?.(valid); }, [valid, onValid]);
  return <fieldset>
    <legend>Vigencia solicitada</legend>
    <div className="row gap-2" style={{ flexWrap: 'wrap' }}>
      {TYPES.map(([type, label]) => <button key={type} type="button" className={`btn ${value.tipo === type ? 'btn-primary' : 'btn-secondary'}`}
        aria-pressed={value.tipo === type} onClick={() => onChange(type === 'personalizado'
          ? { tipo: type, desde: '', hasta: '' } : { tipo: type, anio_lectivo: Number(year) || new Date().getFullYear() })}>{label}</button>)}
    </div>
    {academic ? <>
      <label htmlFor="vigencia-year">Año lectivo</label>
      <input id="vigencia-year" type="number" min="1900" max="9998" value={year}
        onChange={(e) => onChange({ tipo: value.tipo, anio_lectivo: e.target.value ? Number(e.target.value) : '' })} required />
      {loading && <p role="status">Consultando fechas del año…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && !period && <p role="alert">Esta modalidad no está configurada para el año elegido.</p>}
      {period && <p>Desde {period.desde} hasta {period.hasta}, inclusive. Fechas locales de {calendar.zona_horaria}.</p>}
    </> : <div className="row gap-2">
      <label htmlFor="vigencia-start">Fecha desde</label>
      <input id="vigencia-start" type="date" value={value.desde || ''} onChange={(e) => onChange({ ...value, desde: e.target.value })} required />
      <label htmlFor="vigencia-end">Fecha hasta</label>
      <input id="vigencia-end" type="date" value={value.hasta || ''} onChange={(e) => onChange({ ...value, hasta: e.target.value })} required />
      {value.desde && value.hasta && value.desde > value.hasta && <p role="alert">La fecha final debe ser posterior o igual a la inicial.</p>}
    </div>}
  </fieldset>;
}
