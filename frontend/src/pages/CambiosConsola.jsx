import { useEffect, useState } from 'react';
import { listarCambiosConsola, obtenerCambioConsola, confirmarRevocacionConsola, registrarFalloConsola } from '../services/api';
import { PageHead } from '../components/ui';
import RegistroEvidencia from '../components/RegistroEvidencia';
import { mensajeError } from '../utils/errors';

const ESTADOS = { pendiente: 'Pendiente de revocación', revocacion_fallida: 'Revocación fallida', completado: 'Cambio completado' };

function Administracion() {
  const [entries, setEntries] = useState([]);
  const [selected, setSelected] = useState(null);
  const [proof, setProof] = useState('');
  const [motivo, setMotivo] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    listarCambiosConsola().then(({ data }) => { if (active) setEntries(data); })
      .catch((err) => { if (active) setError(mensajeError(err, 'No se pudieron cargar los trámites.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const ver = async (id) => {
    setError(''); setBusy(true); setProof(''); setMotivo('');
    try { setSelected((await obtenerCambioConsola(id)).data); }
    catch (err) { setError(mensajeError(err, 'No se pudo cargar el trámite.')); }
    finally { setBusy(false); }
  };
  const actualizar = async (fallo = false) => {
    setBusy(true); setError('');
    try {
      if (fallo) await registrarFalloConsola(selected.id, motivo);
      else await confirmarRevocacionConsola(selected.id, proof.trim());
      const { data } = await obtenerCambioConsola(selected.id);
      setSelected(data);
      setEntries((rows) => rows.map((row) => row.id === data.id ? data : row));
    } catch (err) { setError(mensajeError(err, 'El trámite sigue pendiente; revisá la evidencia y su revisión.')); }
    finally { setBusy(false); }
  };
  return <div className="fade-in">
    <PageHead kicker="Administración" title="Cambios de acceso a consola" subtitle="Seguimiento de titularidad y permisos con revocación institucional previa." />
    {error && <p role="alert">{error}</p>}
    {loading ? <p role="status">Cargando trámites…</p> : entries.length === 0 ? <p>No hay trámites registrados.</p> : <div className="card table-container"><table>
      <thead><tr><th>Trámite</th><th>Cuenta / cátedra</th><th>Acción</th><th>Estado</th><th>Detalle</th></tr></thead>
      <tbody>{entries.map((row) => <tr key={row.id}><td><code>{row.id}</code></td><td>{row.usuario_id} / {row.catedra_id ?? 'Cuenta completa'}</td><td>{row.accion}</td><td>{ESTADOS[row.estado]}</td><td><button className="btn btn-secondary" onClick={() => ver(row.id)} disabled={busy}>Ver trámite</button></td></tr>)}</tbody>
    </table></div>}
    {selected && <section className="card" aria-label="Detalle del trámite">
      <h2>{ESTADOS[selected.estado]}</h2>
      <p>Identidad institucional: <code>{selected.identidad_nativa || 'Sin identidad nativa'}</code>. Revisión: {selected.revision_esperada}.</p>
      <p>Alcances anteriores: {(selected.scopes_anteriores || []).join(', ') || 'Ninguno'}.</p>
      <p>Alcances que deben conservarse: {(selected.scopes_propuestos || []).join(', ') || 'Ninguno'}.</p>
      {selected.ultimo_error_seguro && <p role="status">{selected.ultimo_error_seguro}</p>}
      {selected.estado !== 'completado' && <>
        <p>El operador institucional debe revocar los permisos y sesiones anteriores, verificar el acceso denegado y conservar los alcances indicados. El cambio académico se aplica al confirmar la evidencia de este trámite.</p>
        <RegistroEvidencia key={selected.id} onRegistered={(registro) => setProof(registro.evidencia_ref)} />
        <div className="field"><label htmlFor="revocacion-ref">Referencia UUID de evidencia registrada</label><input id="revocacion-ref" className="input" value={proof} onChange={(e) => setProof(e.target.value)} /></div>
        <button className="btn btn-primary" disabled={busy || !proof.trim()} onClick={() => actualizar()}>{busy ? 'Procesando…' : 'Confirmar revocación'}</button>
        <div className="field"><label htmlFor="revocacion-fallo">Motivo de fallo institucional</label><textarea id="revocacion-fallo" className="input" maxLength={500} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></div>
        <button className="btn btn-secondary" disabled={busy || !motivo.trim()} onClick={() => actualizar(true)}>Registrar fallo</button>
      </>}
    </section>}
  </div>;
}

export default function CambiosConsola({ user }) {
  return user?.rol === 'admin' ? <Administracion /> : <p>Acceso reservado a administración</p>;
}
