export default function EstadoConsulta({ remote, nombre, mostrarCarga = false }) {
  if (remote.error) return <div className="callout bad" role="alert">
    <p>{remote.error} {remote.data !== null && remote.data !== undefined && 'Conservamos los datos anteriores.'}</p>
    <button className="btn btn-secondary btn-sm" disabled={remote.loading} onClick={remote.reload}>Reintentar {nombre}</button>
  </div>;
  if (mostrarCarga && remote.loading) return <p role="status">Consultando {nombre}…</p>;
  return null;
}
