import { useEffect, useState } from 'react';
import { listarIdentidadesConsola, reintentarIdentidadConsola } from '../services/api';
import { PageHead } from '../components/ui';
import { mensajeError } from '../utils/errors';

const ESTADOS = { lista: 'Lista', en_preparacion: 'En preparación', con_error: 'Con error', retirada: 'Retirada' };

function Administracion() {
  const [filas, setFilas] = useState([]);
  const [estado, setEstado] = useState('');
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(null);
  const cargar = (filtro = estado) => {
    setCargando(true);
    return listarIdentidadesConsola(filtro)
      .then(({ data }) => { setFilas(data); setError(''); })
      .catch((err) => setError(mensajeError(err, 'No se pudo cargar el estado de las identidades.')))
      .finally(() => setCargando(false));
  };
  useEffect(() => { cargar(''); }, []);
  const reintentar = async (fila) => {
    if (ocupado) return;
    setOcupado(fila.usuario_id); setAviso(''); setError('');
    try {
      await reintentarIdentidadConsola(fila.usuario_id);
      setAviso(`Se pidió reintentar la identidad de ${fila.nombre || 'la persona'}. Se procesa en unos segundos.`);
      await cargar();
    } catch (err) { setError(mensajeError(err, 'No se pudo pedir el reintento.')); }
    finally { setOcupado(null); }
  };
  return <div className="stack gap-3">
    <PageHead kicker="Administración" title="Identidades de consola"
      subtitle="Cada persona tiene una identidad propia para abrir terminales. Se prepara y se retira sola; acá ves el estado y reintentás un fallo." />
    <label className="field">Estado
      <select value={estado} onChange={(e) => { setEstado(e.target.value); cargar(e.target.value); }}>
        <option value="">Todas</option>
        {Object.entries(ESTADOS).map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
      </select>
    </label>
    {error && <p role="alert" className="error">{error}</p>}
    {aviso && <p role="status">{aviso}</p>}
    {cargando ? <p>Cargando…</p> : filas.length === 0 ? <p>No hay identidades en este estado.</p> :
      <table className="table" aria-label="Identidades de consola">
        <thead><tr><th>Persona</th><th>Estado</th><th>Cátedras habilitadas</th><th>Última comprobación</th><th /></tr></thead>
        <tbody>{filas.map((fila) => <tr key={fila.usuario_id}>
          <td>{fila.nombre || `Persona ${fila.usuario_id}`}</td>
          <td>{ESTADOS[fila.estado] || fila.estado}{fila.ultimo_error_seguro && <div className="muted">{fila.ultimo_error_seguro}</div>}</td>
          <td>{fila.pools_aplicados.length ? fila.pools_aplicados.map((p) => p.replace('catedra-', '#')).join(', ') : '—'}</td>
          <td>{fila.reconciliada_at ? new Date(fila.reconciliada_at).toLocaleString('es-AR') : '—'}</td>
          <td>{fila.estado === 'con_error' && <button className="btn btn-secondary" disabled={ocupado !== null}
            onClick={() => reintentar(fila)}>Reintentar</button>}</td>
        </tr>)}</tbody>
      </table>}
  </div>;
}

export default function IdentidadesConsola({ user }) {
  return user?.rol === 'admin' ? <Administracion /> : <p>Acceso reservado a administración</p>;
}
