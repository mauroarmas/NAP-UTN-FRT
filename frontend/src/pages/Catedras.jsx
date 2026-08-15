import { useState, useEffect } from 'react';
import { getCatedras, createCatedra, updateCatedra, getCatedra, getProxmoxStatus } from '../services/api';

const FORM_VACIO = {
  nombre: '', descripcion: '', cuota_vcpus: 2, cuota_ram_mb: 1024, cuota_storage_gb: 8, activa: true,
};

export default function Catedras() {
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);
  const [editando, setEditando] = useState(null); // id de la cátedra en edición, o null si es alta
  const [uso, setUso] = useState(null); // recursos en uso de la cátedra editada
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
  // En edición se excluye la propia cátedra, igual que hace el backend con `excluir_id`:
  // su cuota actual no es "de otro", es justamente la que se está reasignando.
  const comprometido = catedras
    .filter(c => c.activa && c.id !== editando)
    .reduce((acc, c) => ({
      vcpus: acc.vcpus + c.cuota_vcpus,
      ram_mb: acc.ram_mb + c.cuota_ram_mb,
      storage_gb: acc.storage_gb + c.cuota_storage_gb,
    }), { vcpus: 0, ram_mb: 0, storage_gb: 0 });

  const disponible = capacidad ? {
    vcpus: Math.max(0, Math.floor(capacidad.vcpus - comprometido.vcpus)),
    ram_mb: Math.max(0, Math.floor(capacidad.ram_mb - comprometido.ram_mb)),
    storage_gb: Math.max(0, Math.floor(capacidad.storage_gb - comprometido.storage_gb)),
  } : null;

  const cerrarForm = () => {
    setShowForm(false);
    setEditando(null);
    setUso(null);
    setForm(FORM_VACIO);
  };

  const abrirAlta = () => {
    setEditando(null);
    setUso(null);
    setForm(FORM_VACIO);
    setShowForm(true);
  };

  const abrirEdicion = async (c) => {
    setEditando(c.id);
    setForm({
      nombre: c.nombre,
      descripcion: c.descripcion || '',
      cuota_vcpus: c.cuota_vcpus,
      cuota_ram_mb: c.cuota_ram_mb,
      cuota_storage_gb: c.cuota_storage_gb,
      activa: c.activa,
    });
    setShowForm(true);
    setUso(null);
    try {
      // Lo que la cátedra ya tiene ocupado: la cuota nueva no puede quedar por debajo.
      const { data } = await getCatedra(c.id);
      setUso({
        vcpus: data.vcpus_en_uso,
        ram_mb: data.ram_en_uso_mb,
        storage_gb: data.storage_en_uso_gb,
        servicios_activos: data.servicios_activos,
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (disponible && (
      form.cuota_vcpus > disponible.vcpus ||
      form.cuota_ram_mb > disponible.ram_mb ||
      form.cuota_storage_gb > disponible.storage_gb
    )) {
      alert('La cuota solicitada supera la capacidad disponible del clúster Proxmox');
      return;
    }
    if (uso && (
      form.cuota_vcpus < uso.vcpus ||
      form.cuota_ram_mb < uso.ram_mb ||
      form.cuota_storage_gb < uso.storage_gb
    )) {
      alert(
        `La cuota no puede quedar por debajo de lo que la cátedra ya usa ` +
        `(${uso.vcpus} vCPUs, ${uso.ram_mb} MB, ${uso.storage_gb} GB). ` +
        `Dá de baja servicios primero.`
      );
      return;
    }
    setSaving(true);
    try {
      if (editando) {
        await updateCatedra(editando, form);
      } else {
        const { activa, ...alta } = form; // el alta no define estado: la cátedra nace activa
        await createCatedra(alta);
      }
      cerrarForm();
      fetchCatedras();
      fetchCapacidad();
    } catch (err) {
      alert(err.response?.data?.detail || `Error al ${editando ? 'actualizar' : 'crear'} la cátedra`);
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
        <button className="btn btn-primary" onClick={() => (showForm ? cerrarForm() : abrirAlta())}>
          {showForm ? 'Cancelar' : '+ Nueva Cátedra'}
        </button>
      </div>

      {showForm && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>
            {editando ? `Editar cátedra: ${form.nombre}` : 'Nueva Cátedra'}
          </h3>
          {editando && (
            <div className="stat-label" style={{ marginBottom: 16 }}>
              {uso
                ? `En uso ahora: ${uso.vcpus} vCPUs · ${uso.ram_mb} MB · ${uso.storage_gb} GB ` +
                  `(${uso.servicios_activos} servicio${uso.servicios_activos === 1 ? '' : 's'} activo${uso.servicios_activos === 1 ? '' : 's'}). ` +
                  `La cuota no puede quedar por debajo de eso.`
                : 'Consultando uso actual...'}
            </div>
          )}
          <form onSubmit={handleSubmit}>
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
                <input className="form-input" type="number" min={uso?.vcpus || 1} max={disponible?.vcpus || undefined} value={form.cuota_vcpus} onChange={e => setForm({...form, cuota_vcpus: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.vcpus} de {capacidad.vcpus} (clúster Proxmox)
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">RAM (MB)</label>
                <input className="form-input" type="number" min={uso?.ram_mb || 128} step="128" max={disponible?.ram_mb || undefined} value={form.cuota_ram_mb} onChange={e => setForm({...form, cuota_ram_mb: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.ram_mb} de {Math.floor(capacidad.ram_mb)} MB
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">Disco (GB)</label>
                <input className="form-input" type="number" min={uso?.storage_gb || 1} max={disponible?.storage_gb || undefined} value={form.cuota_storage_gb} onChange={e => setForm({...form, cuota_storage_gb: parseInt(e.target.value)})} />
                {disponible && (
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Disponible: {disponible.storage_gb} de {Math.floor(capacidad.storage_gb)} GB
                  </div>
                )}
              </div>
              {editando && (
                <div className="form-group">
                  <label className="form-label">Estado</label>
                  <select
                    className="form-input"
                    value={form.activa ? 'activa' : 'inactiva'}
                    onChange={e => setForm({ ...form, activa: e.target.value === 'activa' })}
                  >
                    <option value="activa">Activa</option>
                    <option value="inactiva">Inactiva</option>
                  </select>
                  <div className="stat-label" style={{ marginTop: 4 }}>
                    Una cátedra inactiva libera su cuota para el resto
                  </div>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving
                  ? (editando ? 'Guardando...' : 'Creando...')
                  : (editando ? 'Guardar cambios' : 'Crear Cátedra')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={cerrarForm}>
                Cancelar
              </button>
            </div>
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
                  <th>Acciones</th>
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
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => abrirEdicion(c)}
                        title="Editar cuotas y estado de la cátedra"
                      >
                        ✏️ Editar
                      </button>
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
