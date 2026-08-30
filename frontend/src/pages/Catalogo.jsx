import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Cpu, CheckCircle2 } from 'lucide-react';
import { getTemplates, getCatedras, getCatedrasMias, createPedido } from '../services/api';
import { PageHead, Dialog, Empty } from '../components/ui';

const GRUPOS = [
  { key: 'lxc', label: 'Contenedores LXC', icon: Box },
  { key: 'qemu', label: 'Máquinas Virtuales', icon: Cpu },
];

const FILTROS = [
  { key: 'todos', label: 'Todos' },
  { key: 'lxc', label: 'Contenedores' },
  { key: 'qemu', label: 'Máquinas Virtuales' },
];

export default function Catalogo({ user }) {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState('todos');
  const [activa, setActiva] = useState(null); // template en el diálogo
  const [catedraId, setCatedraId] = useState('');
  const [justificacion, setJustificacion] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [confirmado, setConfirmado] = useState(null); // { id, nombre }

  const isAdmin = user?.rol === 'admin';

  useEffect(() => {
    getTemplates()
      .then(({ data }) => setTemplates(data.filter((t) => t.activo !== false)))
      .catch(console.error)
      .finally(() => setLoading(false));
    (isAdmin ? getCatedras() : getCatedrasMias())
      .then(({ data }) => {
        setCatedras(data);
        if (!isAdmin && data.length === 1) setCatedraId(String(data[0].id));
      })
      .catch(console.error);
  }, [isAdmin]);

  const catedraUnica = !isAdmin && catedras.length === 1 ? catedras[0] : null;
  const necesitaElegirCatedra = !catedraUnica;

  const gruposVisibles = useMemo(
    () => GRUPOS
      .filter((g) => filtro === 'todos' || filtro === g.key)
      .map((g) => ({ ...g, items: templates.filter((t) => t.tipo === g.key) }))
      .filter((g) => g.items.length > 0),
    [templates, filtro],
  );

  const abrir = (tpl) => {
    setActiva(tpl);
    setJustificacion('');
    if (catedraUnica) setCatedraId(String(catedraUnica.id));
    else if (catedras.length === 1) setCatedraId(String(catedras[0].id));
    else setCatedraId('');
  };

  const enviar = async () => {
    if (necesitaElegirCatedra && !catedraId) {
      alert('Elegí la cátedra para la que es el pedido.');
      return;
    }
    setEnviando(true);
    try {
      const { data } = await createPedido({
        template_id: activa.id,
        catedra_id: catedraId ? parseInt(catedraId) : null,
        parametros_extra: justificacion.trim() ? { justificacion_uso: justificacion.trim() } : null,
      });
      setConfirmado({ id: data.id, nombre: activa.nombre });
      setActiva(null);
    } catch (err) {
      alert(err.response?.data?.detail || 'No se pudo enviar la solicitud');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="fade-in">
      <PageHead
        title="Catálogo de Servicios"
        subtitle="Elegí un template estandarizado y enviá tu solicitud. Un administrador la resuelve según la capacidad real del clúster."
      />

      {confirmado && (
        <div className="callout accent" style={{ marginBottom: 'var(--space-4)' }}>
          <CheckCircle2 size={18} />
          <span>
            Solicitud enviada — seguimiento <strong className="tabnum">#{confirmado.id}</strong> ({confirmado.nombre}).{' '}
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/pedidos')}>Ver en Pedidos</button>
          </span>
        </div>
      )}

      <div className="row gap-2 wrap mb-6">
        {FILTROS.map((f) => (
          <button
            key={f.key}
            className={`btn btn-sm ${filtro === f.key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFiltro(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card"><Empty icon={<Box size={22} />}>Cargando catálogo…</Empty></div>
      ) : gruposVisibles.length === 0 ? (
        <div className="card">
          <Empty icon={<Box size={22} />} hint="Un administrador debe crearlos desde Administración → Templates.">
            No hay templates disponibles.
          </Empty>
        </div>
      ) : (
        gruposVisibles.map((g) => (
          <div key={g.key} className="mb-6">
            <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>{g.label}</div>
            <div className="grid cols-3">
              {g.items.map((t) => (
                <div key={t.id} className="card">
                  <div className="row gap-2">
                    <g.icon size={16} style={{ color: 'var(--color-accent-700)', flex: 'none' }} />
                    <span className="card-title" style={{ fontSize: 16 }}>{t.nombre}</span>
                  </div>
                  <p className="card-body clamp-2">{t.descripcion || 'Template estandarizado de la infraestructura.'}</p>
                  <div className="card-meta tabnum">
                    {t.default_vcpus} vCPU · {t.default_ram_mb} MB · {t.default_disk_gb} GB
                  </div>
                  <button className="btn btn-primary btn-block" onClick={() => abrir(t)}>Solicitar</button>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {activa && (
        <Dialog
          title={`Solicitar: ${activa.nombre}`}
          onClose={() => setActiva(null)}
          actions={
            <>
              <button className="btn btn-secondary" onClick={() => setActiva(null)}>Cancelar</button>
              <button className="btn btn-primary" onClick={enviar} disabled={enviando}>
                {enviando ? 'Enviando…' : 'Enviar solicitud'}
              </button>
            </>
          }
        >
          <p style={{ color: 'var(--text-soft)', marginBottom: 'var(--space-3)' }} className="tabnum">
            {activa.tipo === 'qemu' ? 'Máquina Virtual' : 'Contenedor LXC'} ·{' '}
            {activa.default_vcpus} vCPU · {activa.default_ram_mb} MB · {activa.default_disk_gb} GB
          </p>

          <div className="field">
            <label>Cátedra</label>
            {necesitaElegirCatedra ? (
              <select className="input" value={catedraId} onChange={(e) => setCatedraId(e.target.value)}>
                <option value="">Seleccionar cátedra…</option>
                {catedras.map((c) => (
                  <option key={c.id} value={c.id}>{c.nombre}</option>
                ))}
              </select>
            ) : (
              <input className="input" value={catedraUnica.nombre} disabled />
            )}
          </div>

          <div className="field">
            <label>Justificación de uso <span style={{ color: 'var(--text-faint)' }}>(opcional)</span></label>
            <textarea
              className="input"
              rows={3}
              placeholder="Ej: prácticas de laboratorio del segundo cuatrimestre"
              value={justificacion}
              onChange={(e) => setJustificacion(e.target.value)}
            />
          </div>

          <p className="card-meta">El pedido queda pendiente de aprobación.</p>
        </Dialog>
      )}
    </div>
  );
}
