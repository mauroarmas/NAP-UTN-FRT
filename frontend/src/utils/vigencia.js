export const ANIO_LECTIVO_MINIMO = 2026;
export const ANIO_LECTIVO_MAXIMO = 9998;
export const FECHA_MINIMA = `${ANIO_LECTIVO_MINIMO}-01-01`;
export const anioLectivoValido = (year) => /^\d{4}$/.test(String(year)) && Number(year) >= ANIO_LECTIVO_MINIMO && Number(year) <= ANIO_LECTIVO_MAXIMO;
export const vigenciaInicial = () => ({ tipo: 'primer_cuatrimestre', anio_lectivo: Math.max(ANIO_LECTIVO_MINIMO, new Date().getFullYear()) });
