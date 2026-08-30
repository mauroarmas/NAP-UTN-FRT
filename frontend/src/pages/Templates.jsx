import { useState, useEffect } from 'react';
import { Send, Package, Cpu, Zap, MemoryStick, HardDrive, Pencil, EyeOff, Eye } from 'lucide-react';
import { getTemplates, createTemplate, updateTemplate, retirarTemplate, reactivarTemplate, getProxmoxTemplates } from '../services/api';
import { PageHead, Empty, Dialog } from '../components/ui';

const FORM_INICIAL = {
  nombre: '', descripcion: '', tipo: 'lxc',
  default_vcpus: 1, default_ram_mb: 256, default_disk_gb: 2, os_template: '',
};

export default function Templates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [osTemplates, setOsTemplates] = useState([]);
  const [loadingOs, setLoadingOs] = useState(true);
  const [osError, setOsError] = useState(false);
  // id de la plantilla que se está corrigiendo; null = alta de una nueva.
  const [editando, setEditando] = useState(null);
  const [verRetiradas, setVerRetiradas] = useState(false);
  // Qué quedó fuera del alcance de la última corrección (informativo, FR-003).
  const [alcance, setAlcance] = useState(null);

  const fetchTemplates = async () => {
    try {
      const { data } = await getTemplates(verRetiradas);
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
  }, [verRetiradas]);

  useEffect(() => {
    getProxmoxTemplates()
      .then(({ data }) => setOsTemplates(data))
      .catch(() => setOsError(true))
      .finally(() => setLoadingOs(false));
  }, []);

  const abrirEdicion = (t) => {
    setEditando(t.id);
    setForm({
      nombre: t.nombre, descripcion: t.descripcion || '', tipo: t.tipo,
      default_vcpus: t.default_vcpus, default_ram_mb: t.default_ram_mb,
      default_disk_gb: t.default_disk_gb, os_template: t.os_template || '',
      justificacion_disco: t.justificacion_disco || '',
    });
    setShowForm(true);
  };

  const cerrarForm = () => {
    setShowForm(false);
    setEditando(null);
    setForm(FORM_INICIAL);
  };

  const handleGuardar = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, os_template: form.os_template || null };
      if (editando) {
        // El tipo no se puede cambiar: el backend lo rechaza y con razón, así
        // que ni siquiera se envía al corregir.
        delete payload.tipo;
        const { data } = await updateTemplate(editando, payload);
        setAlcance(data.alcance_del_cambio || null);
      } else {
        await createTemplate(payload);
      }
      cerrarForm();
      fetchTemplates();
    } catch (err) {
      const d = err.response?.data?.detail;
      alert(typeof d === 'string' ? d : d?.mensaje || 'No se pudo guardar la plantilla');
    } finally {
      setSaving(false);
    }
  };

  const handleRetiro = async (t) => {
    const accion = t.activo ? 'retirar del catálogo' : 'volver a habilitar';
    if (t.activo && !confirm(
      `¿${t.nombre} se ${accion}?\n\nDeja de ofrecerse en pedidos nuevos. ` +
      'Los servicios ya desplegados siguen funcionando y los pedidos históricos ' +
      'la siguen mostrando.'
    )) return;
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
        title="Templates"
        subtitle="Catálogo estandarizado, adaptado a la capacidad real de la infraestructura."
      >
        <button className="btn-send" onClick={() => setShowForm(true)}>
          <Send size={17} /><span>Nuevo template</span>
        </button>
      </PageHead>

      {alcance && (
        <div className="card mb-4" style={{ borderLeft: '3px solid var(--color-accent)' }}>
          <div className="card-title" style={{ fontSize: 15 }}>Cambios guardados</div>
          <p className="card-body" style={{ marginTop: 6 }}>
            Rigen para los pedidos nuevos.{' '}
            {alcance.servicios_desplegados > 0 && (
              <>Los <strong>{alcance.servicios_desplegados}</strong> servicios ya desplegados
              con esta plantilla siguen con los recursos que se les asignó. </>
            )}
            {alcance.pedidos_aprobados_pendientes > 0 && (
              <>Hay <strong>{alcance.pedidos_aprobados_pendientes}</strong> pedido(s) aprobados
              sin desplegar: se desplegarán con la capacidad que ya tienen reservada. </>
            )}
          </p>
          <button className="btn btn-secondary" style={{ marginTop: 10 }} onClick={() => setAlcance(null)}>
            Entendido
          </button>
        </div>
      )}

      <div className="row between mb-4" style={{ alignItems: 'baseline' }}>
        <div className="section-label">Catálogo</div>
        <div className="row gap-3" style={{ alignItems: 'baseline' }}>
          <label className="card-meta" style={{ cursor: 'pointer' }}>
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
        <div className="grid cols-4">
          {templates.map((t) => {
            const Icon = t.tipo === 'lxc' ? Package : Cpu;
            return (
              <div key={t.id} className="card" style={{ justifyContent: 'space-between', gap: 'var(--space-3)' }}>
                <div className="row between" style={{ alignItems: 'flex-start' }}>
                  <span className="stat__glyph"><Icon size={16} /></span>
                  <div className="row gap-2" style={{ alignItems: 'center' }}>
                    {!t.activo && <span className="tag">Retirada</span>}
                    <span className="tag">{t.tipo?.toUpperCase()}</span>
                  </div>
                </div>
                <div>
                  <div className="card-title" style={{ fontSize: 17 }}>{t.nombre}</div>
                  {t.descripcion && <p className="card-body" style={{ marginTop: 6 }}>{t.descripcion}</p>}
                </div>
                <div className="row wrap gap-3" style={{ paddingTop: 'var(--space-3)', borderTop: '1px solid var(--color-divider)' }}>
                  <span className="card-meta tabnum"><Zap size={12} /> {t.default_vcpus} vCPU</span>
                  <span className="card-meta tabnum"><MemoryStick size={12} /> {t.default_ram_mb} MB</span>
                  <span className="card-meta tabnum"><HardDrive size={12} /> {t.default_disk_gb} GB</span>
                </div>
                <div className="row gap-2" style={{ paddingTop: 'var(--space-2)' }}>
                  <button className="btn btn-secondary" onClick={() => abrirEdicion(t)}>
                    <Pencil size={13} /> Corregir
                  </button>
                  <button className="btn btn-secondary" onClick={() => handleRetiro(t)}>
                    {t.activo ? <><EyeOff size={13} /> Retirar</> : <><Eye size={13} /> Habilitar</>}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card">
          <Empty icon={<Package size={22} />}>{loading ? 'Cargando…' : 'No hay templates creados.'}</Empty>
        </div>
      )}

      {showForm && (
        <Dialog
          title={editando ? 'Corregir plantilla' : 'Nuevo template'}
          onClose={cerrarForm}
          actions={
            <>
              <button className="btn btn-secondary" onClick={cerrarForm}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleGuardar} disabled={saving}>
                {saving ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear template'}
              </button>
            </>
          }
        >
          <form onSubmit={handleGuardar}>
            <div className="grid cols-2">
              <div className="field">
                <label>Nombre</label>
                <input className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required placeholder="Ej: Ubuntu Server Small" />
              </div>
              <div className="field">
                <label>Tipo</label>
                <select className="input" value={form.tipo} disabled={!!editando} title={editando ? 'El tipo no se puede cambiar: creá una plantilla nueva' : undefined} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
                  <option value="lxc">LXC (Contenedor)</option>
                  <option value="qemu">QEMU (VM)</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label>Descripción</label>
              <input className="input" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Descripción del template" />
            </div>
            <div className="grid cols-3">
              <div className="field">
                <label>vCPUs</label>
                <input className="input" type="number" min="1" value={form.default_vcpus} onChange={(e) => setForm({ ...form, default_vcpus: parseInt(e.target.value) })} />
              </div>
              <div className="field">
                <label>RAM (MB)</label>
                <input className="input" type="number" min="64" step="64" value={form.default_ram_mb} onChange={(e) => setForm({ ...form, default_ram_mb: parseInt(e.target.value) })} />
              </div>
              <div className="field">
                <label>Disco (GB)</label>
                <input className="input" type="number" min="1" value={form.default_disk_gb} onChange={(e) => setForm({ ...form, default_disk_gb: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="field">
              <label>OS Template (Proxmox)</label>
              {osError ? (
                <input className="input" value={form.os_template} onChange={(e) => setForm({ ...form, os_template: e.target.value })} placeholder="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst" />
              ) : (
                <select className="input" value={form.os_template} onChange={(e) => setForm({ ...form, os_template: e.target.value })} disabled={loadingOs}>
                  <option value="">{loadingOs ? 'Cargando…' : 'Sin template'}</option>
                  {osTemplates.map((t) => (
                    <option key={t.volid} value={t.volid}>{t.volid.split('/').pop()}</option>
                  ))}
                </select>
              )}
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
