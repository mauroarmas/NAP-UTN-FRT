import { mensajeError } from '../utils/errors';

export default function ErrorFormulario({ error, fallback = 'No se pudo guardar. Conservamos los datos.' }) {
  if (!error) return null;
  const fields = error?.response?.data?.detail?.campos || {};
  return <div role="alert" className="callout bad">
    <p>{typeof error === 'string' ? error : mensajeError(error, fallback)}</p>
    {Object.entries(fields).length > 0 && <ul>{Object.entries(fields).map(([name, message]) => <li key={name}>{name}: {message}</li>)}</ul>}
  </div>;
}
