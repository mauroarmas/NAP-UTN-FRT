import useRemoteData from '../hooks/useRemoteData';
import { getAlertas, getAvisos, getEstadoCorreo } from '../services/api';
import EstadoConsulta from './EstadoConsulta';

const labels = { caida: 'Caída confirmada', cpu_sostenida: 'Uso sostenido de CPU', ram_sostenida: 'Uso sostenido de RAM',
  operacion_incierta: 'Operación sin resultado confirmado', vencimiento_no_aplicado: 'Vencimiento pendiente' };

export default function AlertasServicio({ user, servicioId }) {
  const scope = `${user?.id || ''}:${user?.rol || ''}:${servicioId || 'todos'}`;
  const params = servicioId ? { servicio_id: servicioId } : {};
  const incidents = useRemoteData((options) => getAlertas({ ...params, estado: 'abierto' }, options),
    { key: `alertas:${scope}`, refreshMs: 60000, errorMessage: 'No se pudieron consultar las alertas.' });
  const notices = useRemoteData((options) => getAvisos(params, options),
    { key: `avisos:${scope}`, refreshMs: 60000, errorMessage: 'No se pudieron consultar los avisos.' });
  const mail = useRemoteData((options) => getEstadoCorreo({ estado: 'fallida' }, options),
    { key: `correo:${scope}`, refreshMs: 60000, enabled: user?.rol === 'admin', errorMessage: 'No se pudo consultar el estado del correo.' });
  return <section aria-label="Alertas y avisos" className="card mb-4">
    <h2 className="section-subtitle">Alertas y avisos</h2>
    <EstadoConsulta remote={incidents} nombre="alertas" mostrarCarga />
    <EstadoConsulta remote={notices} nombre="avisos" />
    <EstadoConsulta remote={mail} nombre="estado del correo" />
    {incidents.data?.length === 0 && !incidents.error && !incidents.loading && <p>No hay incidentes abiertos.</p>}
    {incidents.data?.length > 0 && <ul>{incidents.data.map((row) => <li key={row.id}>
      <strong>{labels[row.tipo] || 'Revisar servicio'}</strong> · Servicio #{row.servicio_id} · Desde {new Date(row.abierto_at).toLocaleString('es-AR')}.
    </li>)}</ul>}
    {notices.data?.length > 0 && <details><summary>Avisos recientes ({notices.data.length})</summary>
      <ul>{notices.data.map((row) => <li key={row.id}><strong>{row.asunto}</strong>: {row.texto}</li>)}</ul>
    </details>}
    {user?.rol === 'admin' && mail.data?.length > 0 && <p className="callout warn" role="status">
      Hay {mail.data.length} avisos con entrega de correo fallida. Las decisiones del portal permanecen registradas; el envío se reintentará.
    </p>}
  </section>;
}
