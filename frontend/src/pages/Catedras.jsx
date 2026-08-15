import { useState, useEffect } from 'react';
import { getCatedras, createCatedra, getProxmoxStatus } from '../services/api';

export default function Catedras() {
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    nombre: '', descripcion: '', cuota_vcpus: 2, cuota_ram_mb: 1024, cuota_storage_gb: 8,
  });
  const [saving, setSaving] = useState(false);
  const [capacidad, setCapacidad] = useState(null); // { vcpus, ram_mb, storage_gb } del clúster

  const fetchCatedras = async () => {
    try {
      const { data } = await getCatedras();
      setCatedras(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCapacidad = async () => {
    try {
      const { data } = await getProxmoxStatus();
      const online = (data.nodes || []).filter(n => n.status === 'online');
      setCapacidad({
        vcpus: online.reduce((acc, n) => acc + (n.maxcpu || 0), 0),
        ram_mb: online.reduce((acc, n) => acc + (n.maxmem || 0), 0) / (1024 * 1024),
        storage_gb: online.reduce((acc, n) => acc + (n.maxdisk || 0), 0) / (1024 ** 3),
      });
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => { fetchCatedras(); fetchCapacidad(); }, []);

  // Cuota ya reservada por cátedras activas: lo que queda disponible es capacidad - comprometido.
  const comprometido = catedras.filter(c => c.activa).reduce((acc, c) => ({
    vcpus: acc.vcpus + c.cuota_vcpus,
    ram_mb: acc.ram_mb + c.cuota_ram_mb,
    storage_gb: acc.storage_gb + c.cuota_storage_gb,
  }), { vcpus: 0, ram_mb: 0, storage_gb: 0 });

  const disponible = capacidad ? {
    vcpus: Math.max(0, Math.floor(capacidad.vcpus - comprometido.vcpus)),
    ram_mb: Math.max(0, Math.floor(capacidad.ram_mb - comprometido.ram_mb)),
    storage_gb: Math.max(0, Math.floor(capacidad.storage_gb - comprometido.storage_gb)),
  } : null;

  const handleCreate = async (e) => {
    e.preventDefault();
    if (disponible && (
      form.cuota_vcpus > disponible.vcpus ||
      form.cuota_ram_mb > disponible.ram_mb ||
      form.cuota_storage_gb > disponible.storage_gb
    )) {
      alert('La cuota solicitada supera la capacidad disponible del clúster Proxmox');
      return;
    }
    setSaving(true);
    try {
      await createCatedra(form);
      setShowForm(false);
      setForm({ nombre: '', descripcion: '', cuota_vcpus: 2, cuota_ram_mb: 1024, cuota_storage_gb: 8 });
      fetchCatedras();
      fetchCapacidad();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al crear cátedra');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Cátedras</h1>
          <p className="page-subtitle">Administración de cátedras y cuotas de recursos</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Nueva Cátedra'}
        </button>
      </div>

      {showForm && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Nueva Cátedra</h3>
          <form onSubmit={handleCreate}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group" style={{ gridColumn: 'span 2' }}>
                <label className="form-label">Nombre</label>
                <input className="form-input" value={form.nombre} onChange={e => setForm({...form, nombre: e.target.value})} required placeholder="Ej: Análisis Matemático" />
              </div>
              <div className="form-group" style={{ gridColumn: 'span 2' }}>
                <label className="form-label">Descripción</label>
                <input className="form-input" value={form.descripcion} onChange={e => setForm({...form, descripcion: e.target.value})} placeholder="Descripción opcional" />
              </div>
              <div className="form-group">
                <label className="form-label">vCPUs</label>
                <input className="form-input" type="number" min="1" max={disponible?.vcpus || undefined} value={form.cuota_vcpus} onChange={e => setForm({...form, cuota_vcpus: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.vcpus} de {capacidad.vcpus} (clúster Proxmox)
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">RAM (MB)</label>
                <input className="form-input" type="number" min="128" step="128" max={disponible?.ram_mb || undefined} value={form.cuota_ram_mb} onChange={e => setForm({...form, cuota_ram_mb: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.ram_mb} de {Math.floor(capacidad.ram_mb)} MB
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">Disco (GB)</label>
                <input className="form-input" type="number" min="1" max={disponible?.storage_gb || undefined} value={form.cuota_storage_gb} onChange={e => setForm({...form, cuota_storage_gb: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.storage_gb} de {Math.floor(capacidad.storage_gb)} GB
                  </div>
                )}
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creando...' : 'Crear Cátedra'}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Listado ({catedras.length})</h3>
        </div>
        {catedras.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Descripción</th>
                  <th>vCPUs</th>
                  <th>RAM</th>
                  <th>Disco</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {catedras.map((c) => (
                  <tr key={c.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{c.nombre}</td>
                    <td>{c.descripcion || '—'}</td>
                    <td>{c.cuota_vcpus}</td>
                    <td>{c.cuota_ram_mb} MB</td>
                    <td>{c.cuota_storage_gb} GB</td>
                    <td>
                      <span className={`badge ${c.activa ? 'success' : 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {c.activa ? 'Activa' : 'Inactiva'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🏛️</div>
            <p className="empty-state-text">{loading ? 'Cargando...' : 'No hay cátedras registradas'}</p>
          </div>
        )}
      </div>
    </div>
  );
}
