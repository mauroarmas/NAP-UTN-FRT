import { useMemo, useState } from 'react';

/**
 * Buscador de cátedras con marcado múltiple.
 *
 * El alta de usuario pasó de elegir una cátedra en un desplegable a elegir
 * varias. Con decenas de materias, un listado de casillas sin filtrar obliga a
 * scrollear para encontrar cada una, y sin un resumen arriba no se sabe qué
 * quedó marcado sin volver a recorrer todo.
 *
 * Por eso: filtro por nombre, lista acotada con scroll propio, y las elegidas
 * como fichas removibles fuera de la lista.
 *
 * Las cátedras que ya tienen responsable se muestran deshabilitadas **con el
 * nombre de su titular al lado**, en lugar de ocultarse: si desaparecieran,
 * quien las busca no entendería por qué no están.
 */

/** Normaliza para comparar sin acentos ni mayúsculas ("Programación" ≈ "programacion"). */
const normalizar = (texto) =>
  (texto || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

export default function SelectorCatedras({
  catedras = [],
  seleccionadas = [],
  onChange,
  // Ids que siguen disponibles aunque tengan titular: al editar, las que ya son
  // de esta persona no deben aparecer bloqueadas.
  idsPropios = [],
  disabled = false,
}) {
  const [filtro, setFiltro] = useState('');

  const disponible = (c) =>
    c.titular_id === null ||
    c.titular_id === undefined ||
    idsPropios.includes(c.id);

  const filtradas = useMemo(() => {
    const q = normalizar(filtro);
    if (!q) return catedras;
    return catedras.filter((c) => normalizar(c.nombre).includes(q));
  }, [catedras, filtro]);

  const elegidas = catedras.filter((c) => seleccionadas.includes(c.id));

  const alternar = (id) => {
    if (disabled) return;
    onChange(
      seleccionadas.includes(id)
        ? seleccionadas.filter((x) => x !== id)
        : [...seleccionadas, id]
    );
  };

  return (
    <div className="selector-catedras">
      {elegidas.length > 0 && (
        <div className="selector-catedras__fichas">
          {elegidas.map((c) => (
            <span key={c.id} className="badge info selector-catedras__ficha">
              {c.nombre}
              <button
                type="button"
                className="selector-catedras__quitar"
                onClick={() => alternar(c.id)}
                disabled={disabled}
                aria-label={`Quitar ${c.nombre}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <input
        type="text"
        className="form-input"
        placeholder="Buscar cátedra por nombre…"
        value={filtro}
        onChange={(e) => setFiltro(e.target.value)}
        disabled={disabled}
      />

      <div className="selector-catedras__lista">
        {filtradas.length === 0 && (
          <p className="selector-catedras__vacio">
            {catedras.length === 0
              ? 'No hay cátedras cargadas todavía.'
              : `Ninguna cátedra coincide con "${filtro}".`}
          </p>
        )}

        {filtradas.map((c) => {
          const libre = disponible(c);
          const marcada = seleccionadas.includes(c.id);
          return (
            <label
              key={c.id}
              className={`selector-catedras__fila${libre ? '' : ' is-ocupada'}`}
              title={
                libre ? undefined : `Ya es responsabilidad de ${c.titular?.nombre}`
              }
            >
              <input
                type="checkbox"
                checked={marcada}
                onChange={() => alternar(c.id)}
                disabled={disabled || !libre}
              />
              <span className="selector-catedras__nombre">{c.nombre}</span>
              {!libre && (
                <span className="selector-catedras__titular">
                  {c.titular?.nombre || 'con responsable'}
                </span>
              )}
            </label>
          );
        })}
      </div>

      <p className="selector-catedras__ayuda">
        {elegidas.length === 0
          ? 'Elegí al menos una cátedra.'
          : `${elegidas.length} cátedra${elegidas.length > 1 ? 's' : ''} seleccionada${
              elegidas.length > 1 ? 's' : ''
            }.`}
      </p>
    </div>
  );
}
