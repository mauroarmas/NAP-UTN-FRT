import { useState, useEffect } from 'react';
import { Send, Package, Cpu, Zap, MemoryStick, HardDrive, Pencil, EyeOff, Eye, Filter } from 'lucide-react';
import { getTemplates, retirarTemplate, reactivarTemplate } from '../services/api';
import { PageHead, Empty } from '../components/ui';
import TemplatesAdmin from '../components/TemplatesAdmin';

const MODELOS = [
  { id: 'todos', label: 'Todos los modelos' },
  { id: 'iaas', label: 'IaaS (Infraestructura)' },
  { id: 'paas', label: 'PaaS (Plataforma)' },
  { id: 'saas', label: 'SaaS (Software)' },
];

const MODELO_STYLES = {
  iaas: { label: 'IaaS', bg: 'rgba(59, 130, 246, 0.12)', color: '#3b82f6', border: 'rgba(59, 130, 246, 0.3)' },
  paas: { label: 'PaaS', bg: 'rgba(168, 85, 247, 0.12)', color: '#a855f7', border: 'rgba(168, 85, 247, 0.3)' },
  saas: { label: 'SaaS', bg: 'rgba(16, 185, 129, 0.12)', color: '#10b981', border: 'rgba(16, 185, 129, 0.3)' },
};

export default function Templates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalAdminOpen, setModalAdminOpen] = useState(false);
  const [templateEditando, setTemplateEditando] = useState(null);
  const [verRetiradas, setVerRetiradas] = useState(false);
  const [filtroModelo, setFiltroModelo] = useState('todos');
  const [alcance, setAlcance] = useState(null);

  const fetchTemplates = async () => {
    try {
      const modeloParam = filtroModelo === 'todos' ? null : filtroModelo;
      const { data } = await getTemplates(verRetiradas, modeloParam);
      setTemplates(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verRetiradas, filtroModelo]);

  const abrirCreacion = () => {
    setTemplateEditando(null);
    setModalAdminOpen(true);
  };

  const abrirEdicion = (t) => {
    setTemplateEditando(t);
    setModalAdminOpen(true);
  };

  const handleRetiro = async (t) => {
    const accion = t.activo ? 'retirar del catálogo' : 'volver a habilitar';
    if (
      t.activo &&
      !confirm(
        `¿${t.nombre} se ${accion}?\n\nDeja de ofrecerse en pedidos nuevos. ` +
          'Los servicios ya desplegados siguen funcionando y los pedidos históricos la siguen mostrando.'
      )
    )
      return;
    try {
      await (t.activo ? retirarTemplate(t.id) : reactivarTemplate(t.id));
      fetchTemplates();
    } catch (err) {
      alert(err.response?.data?.detail || 'No se pudo cambiar el estado de la plantilla');
    }
  };

  return (
    <div className="fade-in">
      <PageHead
        kicker="Administración"
        title="Catálogo de Plantillas"
        subtitle="Gestión y parametrización de plantillas homologadas IaaS, PaaS y SaaS para las cátedras."
      >
        <button className="btn-send" onClick={abrirCreacion}>
          <Send size={17} />
          <span>Nuevo template</span>
        </button>
      </PageHead>

      {alcance && (
        <div className="card mb-4" style={{ borderLeft: '3px solid var(--color-accent)' }}>
          <div className="card-title" style={{ fontSize: 15 }}>Cambios guardados</div>
          <p className="card-body" style={{ marginTop: 6 }}>
            Rigen para los pedidos nuevos.{' '}
            {alcance.servicios_desplegados > 0 && (
              <>
                Los <strong>{alcance.servicios_desplegados}</strong> servicios ya desplegados con esta plantilla siguen
                con los recursos que se les asignó.{' '}
              </>
            )}
            {alcance.pedidos_aprobados_pendientes > 0 && (
              <>
                Hay <strong>{alcance.pedidos_aprobados_pendientes}</strong> pedido(s) aprobados sin desplegar: se
                desplegarán con la capacidad que ya tienen reservada.{' '}
              </>
            )}
          </p>
          <button className="btn btn-secondary" style={{ marginTop: 10 }} onClick={() => setAlcance(null)}>
            Entendido
          </button>
        </div>
      )}

      {/* Barra de filtros por modelo de servicio y retiradas */}
      <div className="row between mb-4" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
        <div className="row gap-2" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="card-meta" style={{ display: 'flex', alignItems: 'center', gap: 4, marginRight: 4 }}>
            <Filter size={14} /> Modelo:
          </span>
          {MODELOS.map((m) => (
            <button
              key={m.id}
              className={`btn btn-secondary ${filtroModelo === m.id ? 'active' : ''}`}
              style={{
                fontSize: '0.8rem',
                padding: '4px 10px',
                borderColor: filtroModelo === m.id ? 'var(--color-accent)' : undefined,
                background: filtroModelo === m.id ? 'var(--color-accent-subtle)' : undefined,
              }}
              onClick={() => setFiltroModelo(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="row gap-3" style={{ alignItems: 'center' }}>
          <label className="card-meta" style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={verRetiradas}
              onChange={(e) => setVerRetiradas(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            Ver retiradas
          </label>
          <span className="section-count">{templates.length} templates</span>
        </div>
      </div>

      {templates.length > 0 ? (
        <div className="grid cols-3">
          {templates.map((t) => {
            const Icon = t.tipo === 'lxc' ? Package : Cpu;
            const modeloInfo = MODELO_STYLES[t.modelo_servicio?.toLowerCase()] || MODELO_STYLES.iaas;

            return (
              <div
                key={t.id}
                className="card"
                style={{
                  justifyContent: 'space-between',
                  gap: 'var(--space-3)',
                  opacity: t.activo ? 1 : 0.65,
                }}
              >
                <div>
                  <div className="row between" style={{ alignItems: 'flex-start', marginBottom: 'var(--space-2)' }}>
                    <span className="stat__glyph"><Icon size={16} /></span>
                    <div className="row gap-2" style={{ alignItems: 'center' }}>
                      <span
                        className="tag"
                        style={{
                          background: modeloInfo.bg,
                          color: modeloInfo.color,
                          border: `1px solid ${modeloInfo.border}`,
                          fontWeight: 600,
                        }}
                      >
                        {modeloInfo.label}
                      </span>
                      <span className="tag">{t.tipo?.toUpperCase()}</span>
                      {!t.activo && <span className="tag" style={{ background: 'var(--color-divider)' }}>Retirada</span>}
                    </div>
                  </div>

                  <div className="card-title" style={{ fontSize: 17 }}>{t.nombre}</div>
                  {t.descripcion && (
                    <p className="card-body" style={{ marginTop: 6, fontSize: '0.85rem' }}>
                      {t.descripcion}
                    </p>
                  )}
                </div>

                <div>
                  <div
                    className="row wrap gap-3"
                    style={{
                      paddingTop: 'var(--space-3)',
                      borderTop: '1px solid var(--color-divider)',
                    }}
                  >
                    <span className="card-meta tabnum"><Zap size={12} /> {t.default_vcpus} vCPU</span>
                    <span className="card-meta tabnum"><MemoryStick size={12} /> {t.default_ram_mb} MB</span>
                    <span className="card-meta tabnum"><HardDrive size={12} /> {t.default_disk_gb} GB</span>
                  </div>

                  <div className="row gap-2" style={{ paddingTop: 'var(--space-3)' }}>
                    <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => abrirEdicion(t)}>
                      <Pencil size={13} /> Corregir
                    </button>
                    <button
                      className="btn btn-secondary"
                      style={{ flex: 1 }}
                      onClick={() => handleRetiro(t)}
                    >
                      {t.activo ? (
                        <><EyeOff size={13} /> Retirar</>
                      ) : (
                        <><Eye size={13} /> Habilitar</>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card">
          <Empty icon={<Package size={22} />}>
            {loading ? 'Cargando plantillas…' : 'No hay plantillas que coincidan con los filtros seleccionados.'}
          </Empty>
        </div>
      )}

      {/* Modal ABM de administración de plantillas */}
      <TemplatesAdmin
        open={modalAdminOpen}
        template={templateEditando}
        onClose={() => {
          setModalAdminOpen(false);
          setTemplateEditando(null);
        }}
        onGuardado={(data) => {
          if (data?.alcance_del_cambio) setAlcance(data.alcance_del_cambio);
          fetchTemplates();
        }}
      />
    </div>
  );
}
