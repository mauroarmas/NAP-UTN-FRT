import { useState, useEffect } from 'react';
import { getTemplates, createTemplate, getProxmoxTemplates } from '../services/api';

export default function Templates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    nombre: '', descripcion: '', tipo: 'lxc',
    default_vcpus: 1, default_ram_mb: 256, default_disk_gb: 2,
    os_template: '',
  });
  const [saving, setSaving] = useState(false);
  const [osTemplates, setOsTemplates] = useState([]);
  const [loadingOsTemplates, setLoadingOsTemplates] = useState(true);
  const [osTemplatesError, setOsTemplatesError] = useState(false);

  const fetchTemplates = async () => {
    try {
      const { data } = await getTemplates();
      setTemplates(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchOsTemplates = async () => {
    try {
      const { data } = await getProxmoxTemplates();
      setOsTemplates(data);
    } catch (err) {
      console.error(err);
      setOsTemplatesError(true);
    } finally {
      setLoadingOsTemplates(false);
    }
  };

  useEffect(() => { fetchTemplates(); fetchOsTemplates(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await createTemplate({
        ...form,
        os_template: form.os_template || null,
      });
      setShowForm(false);
      setForm({ nombre: '', descripcion: '', tipo: 'lxc', default_vcpus: 1, default_ram_mb: 256, default_disk_gb: 2, os_template: '' });
      fetchTemplates();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al crear template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Templates</h1>
          <p className="page-subtitle">Catálogo de templates de recursos para las cátedras</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Nuevo Template'}
        </button>
      </div>

      {showForm && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Nuevo Template</h3>
          <form onSubmit={handleCreate}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Nombre</label>
                <input className="form-input" value={form.nombre} onChange={e => setForm({...form, nombre: e.target.value})} required placeholder="Ej: Ubuntu Server Small" />
              </div>
              <div className="form-group">
                <label className="form-label">Tipo</label>
                <select className="form-input" value={form.tipo} onChange={e => setForm({...form, tipo: e.target.value})}>
                  <option value="lxc">LXC (Contenedor)</option>
                  <option value="qemu">QEMU (VM)</option>
                </select>
              </div>
              <div className="form-group" style={{ gridColumn: 'span 2' }}>
                <label className="form-label">Descripción</label>
                <input className="form-input" value={form.descripcion} onChange={e => setForm({...form, descripcion: e.target.value})} placeholder="Descripción del template" />
              </div>
              <div className="form-group">
                <label className="form-label">vCPUs</label>
                <input className="form-input" type="number" min="1" value={form.default_vcpus} onChange={e => setForm({...form, default_vcpus: parseInt(e.target.value)})} />
              </div>
              <div className="form-group">
                <label className="form-label">RAM (MB)</label>
                <input className="form-input" type="number" min="64" step="64" value={form.default_ram_mb} onChange={e => setForm({...form, default_ram_mb: parseInt(e.target.value)})} />
              </div>
              <div className="form-group">
                <label className="form-label">Disco (GB)</label>
                <input className="form-input" type="number" min="1" value={form.default_disk_gb} onChange={e => setForm({...form, default_disk_gb: parseInt(e.target.value)})} />
              </div>
              <div className="form-group">
                <label className="form-label">OS Template (Proxmox)</label>
                {osTemplatesError ? (
                  <input className="form-input" value={form.os_template} onChange={e => setForm({...form, os_template: e.target.value})} placeholder="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst" />
                ) : (
                  <select className="form-input" value={form.os_template} onChange={e => setForm({...form, os_template: e.target.value})} disabled={loadingOsTemplates}>
                    <option value="">{loadingOsTemplates ? 'Cargando...' : 'Sin template'}</option>
                    {osTemplates.map(t => (
                      <option key={t.volid} value={t.volid}>{t.volid.split('/').pop()}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creando...' : 'Crear Template'}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Catálogo ({templates.length})</h3>
        </div>

        {templates.length > 0 ? (
          <div className="cards-grid" style={{ marginBottom: 0 }}>
            {templates.map(t => (
              <div key={t.id} className="stat-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div className={`stat-icon ${t.tipo === 'lxc' ? 'blue' : 'purple'}`}>
                    {t.tipo === 'lxc' ? '📦' : '🖥️'}
                  </div>
                  <span className={`badge ${t.activo ? 'success' : 'neutral'}`}>
                    <span className="badge-dot"></span>
                    {t.tipo.toUpperCase()}
                  </span>
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>{t.nombre}</div>
                {t.descripcion && <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>{t.descripcion}</div>}
                <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span>⚡ {t.default_vcpus} vCPU</span>
                  <span>💾 {t.default_ram_mb} MB</span>
                  <span>💿 {t.default_disk_gb} GB</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <p className="empty-state-text">{loading ? 'Cargando...' : 'No hay templates creados'}</p>
          </div>
        )}
      </div>
    </div>
  );
}
