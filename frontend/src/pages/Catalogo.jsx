import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Package } from 'lucide-react';
import { getTemplates } from '../services/api';
import { PageHead, Empty } from '../components/ui';
import NuevoPedidoModal from '../components/NuevoPedidoModal';
import { mensajeError } from '../utils/errors';
import { MODELOS_SERVICIO } from '../utils/catalogo';

const MODELS = MODELOS_SERVICIO;

export default function Catalogo({ user }) {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [created, setCreated] = useState(null);
  const [model, setModel] = useState('todos');
  useEffect(() => {
    let active = true;
    getTemplates().then(({ data }) => {
      if (active) setProfiles(data.filter((row) => row.tipo === 'lxc' && row.activo !== false && row.oferta_disponible === true));
    }).catch((err) => { if (active) setError(mensajeError(err, 'No se pudo cargar el catálogo.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return <div className="fade-in">
    <PageHead title="Catálogo de servicios" subtitle="Elegí qué necesitás para tu cátedra e indicá las fechas. Administración se encarga de asignar los recursos." />
    {error && <p role="alert" className="callout bad">{error}</p>}
    {created && <p role="status">Solicitud #{created.id} registrada. <Link to="/pedidos">Ver seguimiento</Link></p>}
    <div className="row wrap gap-2 mb-4">
      {[['todos', 'Todos'], ...MODELS].map(([value, label]) => <button key={value} className="btn btn-secondary" aria-pressed={model === value} onClick={() => setModel(value)}>{label}</button>)}
    </div>
    {loading ? <p role="status">Cargando catálogo…</p> : profiles.length === 0 ? <Empty icon={<Package size={22} />}>Todavía no hay servicios publicados disponibles.</Empty> :
      MODELS.filter(([value]) => model === 'todos' || model === value).map(([value, label]) => {
        const rows = profiles.filter((row) => row.modelo_servicio === value);
        return rows.length ? <section key={value} className="mb-6"><h2>{label}</h2><div className="grid cols-3">
          {rows.map((row) => <article className="card" key={row.id}>
            <h3>{row.nombre}</h3>{row.version_ofrecida && <p>Versión ofrecida: {row.version_ofrecida}</p>}<p>{row.descripcion || 'Servicio preparado para las prácticas.'}</p>
            <p className="card-meta">Recursos asignados por administración según las necesidades del pedido.</p>
            <button className="btn btn-primary" onClick={() => setSelected(row)}>Solicitar {row.nombre}</button>
          </article>)}
        </div></section> : null;
      })}
    <NuevoPedidoModal open={!!selected} initialTemplate={selected} user={user} onClose={() => setSelected(null)} onCreated={setCreated} />
  </div>;
}
