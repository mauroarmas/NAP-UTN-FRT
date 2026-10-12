import { useState, useEffect, useMemo } from 'react';
import { Server, Cloud, Cpu } from 'lucide-react';
import { getTemplates, getCatedras, getCatedrasMias, createPedido } from '../services/api';
import { Dialog } from './ui';

const MODELOS = [
  {
    key: 'iaas',
    label: 'IaaS (Infraestructura)',
    badge: 'IaaS',
    icon: Server,
  },
  {
    key: 'paas',
    label: 'PaaS (Plataforma)',
    badge: 'PaaS',
    icon: Cpu,
  },
  {
    key: 'saas',
    label: 'SaaS (Software)',
    badge: 'SaaS',
    icon: Cloud,
  },
];

const VIGENCIAS = [
  { key: 'primer_cuatrimestre', label: '1° Cuatrimestre' },
  { key: 'segundo_cuatrimestre', label: '2° Cuatrimestre' },
  { key: 'anual', label: 'Ciclo Lectivo Anual' },
  { key: 'personalizado', label: 'Rango Personalizado' },
];

export default function NuevoPedidoModal({ open, onClose, onCreated, user }) {
  const [modelo, setModelo] = useState('iaas');
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [nombreOtro, setNombreOtro] = useState('');
  const [titulo, setTitulo] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [vigenciaTipo, setVigenciaTipo] = useState('primer_cuatrimestre');
  const [vigenciaDesde, setVigenciaDesde] = useState('');
  const [vigenciaHasta, setVigenciaHasta] = useState('');
  const [catedras, setCatedras] = useState([]);
  const [catedraId, setCatedraId] = useState('');
  const [loading, setLoading] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  const isAdmin = user?.rol === 'admin';

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setNombreOtro('');
    setTitulo('');
    setDescripcion('');
    setVigenciaTipo('primer_cuatrimestre');
    setVigenciaDesde('');
    setVigenciaHasta('');

    Promise.all([
      getTemplates().then(({ data }) => data.filter((t) => t.activo !== false)),
      (isAdmin ? getCatedras() : getCatedrasMias()).then(({ data }) => data),
    ])
      .then(([tpls, cats]) => {
        setTemplates(tpls);
        setCatedras(cats);
        if (cats.length > 0) setCatedraId(String(cats[0].id));

        const iaasTpls = tpls.filter((t) => !t.modelo_servicio || t.modelo_servicio.toLowerCase() === 'iaas');
        if (iaasTpls.length > 0) {
          setTemplateId(String(iaasTpls[0].id));
        }
      })
      .catch((err) => {
        console.error('Error al cargar datos del formulario:', err);
        setError('No se pudieron cargar las plantillas o cátedras.');
      })
      .finally(() => setLoading(false));
  }, [open, isAdmin]);

  const plantillasDisponibles = useMemo(() => {
    return templates.filter((t) => {
      const m = (t.modelo_servicio || 'iaas').toLowerCase();
      return m === modelo;
    });
  }, [templates, modelo]);

  const handleCambioModelo = (nuevoModelo) => {
    setModelo(nuevoModelo);
    setError(null);

    const filtradas = templates.filter((t) => {
      const m = (t.modelo_servicio || 'iaas').toLowerCase();
      return m === nuevoModelo;
    });

    if (nuevoModelo === 'iaas') {
      if (filtradas.length > 0) {
        setTemplateId(String(filtradas[0].id));
      } else {
        setTemplateId('');
      }
    } else {
      if (filtradas.length > 0) {
        setTemplateId(String(filtradas[0].id));
      } else {
        setTemplateId('otro');
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (modelo === 'iaas' && (!templateId || templateId === 'otro')) {
      setError('Debes seleccionar una plantilla para servicios IaaS.');
      return;
    }

    if ((modelo === 'saas' || modelo === 'paas') && templateId === 'otro' && !nombreOtro.trim()) {
      setError('Por favor indica qué software o servicio requieres.');
      return;
    }

    if (!descripcion.trim()) {
      setError('Por favor provee una descripción de requerimientos.');
      return;
    }

    if (catedras.length > 1 && !catedraId) {
      setError('Por favor selecciona la cátedra.');
      return;
    }

    if (vigenciaTipo === 'personalizado' && (!vigenciaDesde || !vigenciaHasta)) {
      setError('Debes especificar fecha de inicio y fecha de finalización.');
      return;
    }

    setEnviando(true);
    try {
      const lineasDesc = [];
      if (templateId === 'otro' && nombreOtro.trim()) {
        lineasDesc.push(`[Servicio Solicitado: ${nombreOtro.trim()}]`);
      }
      if (titulo.trim()) {
        lineasDesc.push(`[Propósito: ${titulo.trim()}]`);
      }
      lineasDesc.push(descripcion.trim());

      const payload = {
        modelo_servicio: modelo,
        template_id: modelo === 'iaas' ? parseInt(templateId) : (templateId === 'otro' || !templateId ? null : parseInt(templateId)),
        descripcion_requerimientos: lineasDesc.join('\n'),
        vigencia_tipo: vigenciaTipo,
        vigencia_desde: vigenciaTipo === 'personalizado' && vigenciaDesde ? vigenciaDesde : null,
        vigencia_hasta: vigenciaTipo === 'personalizado' && vigenciaHasta ? vigenciaHasta : null,
        catedra_id: catedraId ? parseInt(catedraId) : null,
        parametros_extra: {
          titulo: titulo.trim() || null,
          software_solicitado: templateId === 'otro' ? nombreOtro.trim() : null,
        },
      };

      const { data } = await createPedido(payload);
      if (onCreated) onCreated(data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al enviar la solicitud.');
    } finally {
      setEnviando(false);
    }
  };

  if (!open) return null;

  return (
    <Dialog wide title="Nueva Solicitud de Recursos y Servicios" onClose={onClose}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {error && (
          <div className="callout bad">
            <span>{typeof error === 'string' ? error : JSON.stringify(error)}</span>
          </div>
        )}

        {/* Cátedra y Responsable como texto */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label className="label" style={{ fontWeight: 600, fontSize: 13, margin: 0 }}>
              Cátedra
            </label>
            <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>
              Responsable: <strong style={{ color: 'var(--color-text)' }}>{user?.nombre || user?.username || 'Usuario'}</strong>
            </span>
          </div>

          {catedras.length > 1 || isAdmin ? (
            <select
              className="input select"
              value={catedraId}
              onChange={(e) => setCatedraId(e.target.value)}
              required
            >
              {catedras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              readOnly
              value={catedras[0]?.nombre || 'Cátedra asignada'}
              style={{ opacity: 0.9, cursor: 'not-allowed' }}
            />
          )}
        </div>

        {/* Selector de Modelo de Servicio (IaaS, PaaS, SaaS) */}
        <div>
          <label className="label" style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--space-1)', display: 'block' }}>
            Tipo de Servicio
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
            {MODELOS.map((m) => {
              const Icon = m.icon;
              const activo = modelo === m.key;
              return (
                <button
                  type="button"
                  key={m.key}
                  onClick={() => handleCambioModelo(m.key)}
                  className="btn"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    padding: 'var(--space-2)',
                    background: activo ? 'var(--accent-tint)' : 'var(--color-surface)',
                    border: activo ? '1px solid var(--color-accent)' : '1px solid var(--color-divider)',
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    height: 'auto',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  <Icon size={16} style={{ color: activo ? 'var(--color-accent-700)' : 'var(--text-soft)' }} />
                  <strong style={{ fontSize: 13, color: 'var(--color-text)' }}>{m.label}</strong>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selección de plantilla o "Otro" según modelo */}
        <div>
          {modelo === 'iaas' ? (
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="label" style={{ fontWeight: 600, fontSize: 13 }}>
                Plantilla
              </label>
              <select
                className="input select"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                required
              >
                {plantillasDisponibles.length === 0 && (
                  <option value="">No hay plantillas IaaS disponibles</option>
                )}
                {plantillasDisponibles.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nombre} ({t.default_vcpus} vCPU · {t.default_ram_mb} MB RAM · {t.default_disk_gb} GB Disco)
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="label" style={{ fontWeight: 600, fontSize: 13 }}>
                  Servicio
                </label>
                <select
                  className="input select"
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  required
                >
                  {plantillasDisponibles.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.nombre} {t.descripcion ? `— ${t.descripcion}` : ''}
                    </option>
                  ))}
                  <option value="otro">Otro</option>
                </select>
              </div>

              {templateId === 'otro' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label className="label" style={{ fontWeight: 600, fontSize: 13 }}>
                    Especificar Software o Servicio
                  </label>
                  <input
                    className="input"
                    value={nombreOtro}
                    onChange={(e) => setNombreOtro(e.target.value)}
                    placeholder={modelo === 'saas' ? 'Ej: BookStack, Moodle...' : 'Ej: Ollama API, PostgreSQL...'}
                    required
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* 4. Justificación descriptiva para el administrador */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div>
            <label className="label" style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, display: 'block' }}>
              4. Justificación descriptiva para el administrador
            </label>
          </div>

          <div>
            <label className="label" style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, display: 'block' }}>
              Nombre o Título de la Solicitud *
            </label>
            <input
              className="input"
              placeholder="Ej: Entorno de Prácticas de Routing y Firewalls - 1C 2026"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="label" style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, display: 'block' }}>
              Descripción detallada y Justificación Pedagógica *
            </label>
            <textarea
              className="input textarea"
              rows={3}
              placeholder="Explica detalladamente qué actividades prácticas se realizarán, cantidad estimada de alumnos que interactuarán y cualquier necesidad de conectividad especial..."
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              required
            />
            <p className="card-meta" style={{ marginTop: 4, fontSize: 12, color: 'var(--text-soft)' }}>
              Esta justificación le permite al admin validar la criticidad del pedido antes de asignarle capacidad física.
            </p>
          </div>
        </div>

        {/* Vigencia Temporal */}
        <div>
          <label className="label" style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--space-1)', display: 'block' }}>
            Vigencia
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-2)' }}>
            {VIGENCIAS.map((v) => (
              <button
                type="button"
                key={v.key}
                onClick={() => setVigenciaTipo(v.key)}
                className={`btn btn-sm ${vigenciaTipo === v.key ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: 12, padding: '6px 8px', height: 'auto' }}
              >
                {v.label}
              </button>
            ))}
          </div>

          {vigenciaTipo === 'personalizado' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <div>
                <label className="label" style={{ fontSize: 11, color: 'var(--text-soft)' }}>Fecha Desde</label>
                <input
                  type="date"
                  className="input"
                  value={vigenciaDesde}
                  onChange={(e) => setVigenciaDesde(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="label" style={{ fontSize: 11, color: 'var(--text-soft)' }}>Fecha Hasta</label>
                <input
                  type="date"
                  className="input"
                  value={vigenciaHasta}
                  onChange={(e) => setVigenciaHasta(e.target.value)}
                  required
                />
              </div>
            </div>
          )}
        </div>

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={enviando}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={enviando || loading}>
            {enviando ? 'Enviando...' : 'Enviar Solicitud'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
