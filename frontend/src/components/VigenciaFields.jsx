import { useEffect, useState } from 'react';
import { getCalendario } from '../services/api';
import { mensajeError } from '../utils/errors';
import { ANIO_LECTIVO_MINIMO, ANIO_LECTIVO_MAXIMO, FECHA_MINIMA, anioLectivoValido, vigenciaInicial } from '../utils/vigencia';

const TYPES = [
  ['primer_cuatrimestre', '1° Cuatrimestre'], ['segundo_cuatrimestre', '2° Cuatrimestre'],
  ['anual', 'Ciclo Lectivo Anual'], ['personalizado', 'Rango Personalizado'],
];

export default function VigenciaFields({ value, onChange, onValid, onPeriodChange }) {
  const [calendar, setCalendar] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const academic = value.tipo !== 'personalizado';
  const year = String(value.anio_lectivo || '');
  const validYear = anioLectivoValido(year);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setCalendar(null); setError('');
    if (!academic || !anioLectivoValido(year)) { setLoading(false); return () => { active = false; }; }
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
  const valid = academic ? Boolean(validYear && !loading && !error && period && String(calendar?.anio) === year)
    : Boolean(value.desde && value.hasta && value.desde >= FECHA_MINIMA && value.hasta >= FECHA_MINIMA && value.desde <= value.hasta);
  useEffect(() => { onValid?.(valid); }, [valid, onValid]);
  useEffect(() => {
    onPeriodChange?.(valid ? { desde: academic ? period.desde : value.desde,
      hasta: academic ? period.hasta : value.hasta } : null);
  }, [valid, academic, period?.desde, period?.hasta, value.desde, value.hasta, onPeriodChange]);
  return <fieldset className="vigencia-fields">
    <legend>Vigencia solicitada</legend>
    <div className="row gap-2 vigencia-options" style={{ flexWrap: 'wrap' }}>
      {TYPES.map(([type, label]) => <button key={type} type="button" className={`btn ${value.tipo === type ? 'btn-primary' : 'btn-secondary'}`}
        aria-pressed={value.tipo === type} onClick={() => onChange(type === 'personalizado'
          ? { tipo: type, desde: '', hasta: '' } : { tipo: type, anio_lectivo: validYear ? Number(year) : vigenciaInicial().anio_lectivo })}>{label}</button>)}
    </div>
    {academic ? <>
      <div className="vigencia-year-field"><label htmlFor="vigencia-year">Año lectivo</label>
        <input id="vigencia-year" className="input" type="number" min={ANIO_LECTIVO_MINIMO} max={ANIO_LECTIVO_MAXIMO} value={year} aria-invalid={!validYear}
          onChange={(e) => onChange({ tipo: value.tipo, anio_lectivo: e.target.value ? Number(e.target.value) : '' })} required />
      </div>
      {!validYear && <p role="alert">Elegí un año lectivo entre {ANIO_LECTIVO_MINIMO} y {ANIO_LECTIVO_MAXIMO}.</p>}
      {loading && <p role="status">Consultando fechas del año…</p>}
      {error && <p role="alert">{error}</p>}
      {validYear && !loading && !error && !period && <p role="alert">Esta modalidad no está configurada para el año elegido.</p>}
      {validYear && period && String(calendar?.anio) === year && <p>Desde {period.desde} hasta {period.hasta}, inclusive. Fechas locales de {calendar.zona_horaria}.</p>}
    </> : <div className="row gap-2 vigencia-custom">
      <label htmlFor="vigencia-start">Fecha desde
        <input id="vigencia-start" className="input" type="date" min={FECHA_MINIMA} value={value.desde || ''} onChange={(e) => onChange({ ...value, desde: e.target.value })} required />
      </label>
      <label htmlFor="vigencia-end">Fecha hasta
        <input id="vigencia-end" className="input" type="date" min={value.desde && value.desde >= FECHA_MINIMA ? value.desde : FECHA_MINIMA} value={value.hasta || ''} onChange={(e) => onChange({ ...value, hasta: e.target.value })} required />
      </label>
      {value.desde && value.hasta && value.desde > value.hasta && <p role="alert">La fecha final debe ser posterior o igual a la inicial.</p>}
      {(value.desde && value.desde < FECHA_MINIMA || value.hasta && value.hasta < FECHA_MINIMA) && <p role="alert">Las fechas deben corresponder a {ANIO_LECTIVO_MINIMO} o un año posterior.</p>}
    </div>}
  </fieldset>;
}
