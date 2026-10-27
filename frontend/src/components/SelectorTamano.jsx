import { resumenRecursos } from '../utils/tamanos';

export default function SelectorTamano({ sizes, value, onChange, allowed, disabled = false, name = 'tamano', legend = 'Tamaño de recursos' }) {
  return <fieldset className="size-picker" disabled={disabled}>
    <legend>{legend}</legend>
    <div className="size-picker__options">
      {sizes.map((size) => {
        const available = !allowed || allowed.includes(size.id);
        return <label key={size.id} className={`size-option ${value === size.id ? 'is-selected' : ''} ${!available ? 'is-unavailable' : ''}`}>
          <input type="radio" name={name} value={size.id} checked={value === size.id} disabled={!available} onChange={() => onChange(size.id)} />
          <span><strong>{size.nombre}</strong><span className="size-option__resources">{resumenRecursos(size)}</span>
            {!available && <span className="size-option__reason">No alcanza los mínimos de esta aplicación</span>}</span>
        </label>;
      })}
    </div>
  </fieldset>;
}
