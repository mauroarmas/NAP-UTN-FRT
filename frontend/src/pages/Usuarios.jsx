import { useState, useEffect } from 'react';
import { getUsuarios, createUsuario, updateUsuario, deleteUsuario, getCatedras } from '../services/api';

const ROL_CONFIG = {
  admin:        { label: 'Administrador', badge: 'error',   icon: '🔑' },
  catedra_admin:{ label: 'Cátedra',       badge: 'info',    icon: '🎓' },
};

const FORM_INICIAL = {
  username: '', nombre: '', email: '', password: '',
  rol: 'catedra_admin', catedra_id: '',
};

export default function Usuarios({ user }) {
  const [usuarios, setUsuarios]   = useState([]);
  const [catedras, setCatedras]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);
  const [editando, setEditando]   = useState(null);   // usuario en edición
  const [form, setForm]           = useState(FORM_INICIAL);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');

  const fetchAll = async () => {
    try {
      const [uRes, cRes] = await Promise.all([getUsuarios(), getCatedras()]);
      setUsuarios(uRes.data);
      setCatedras(cRes.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const abrirNuevo = () => {
    setEditando(null);
    setForm(FORM_INICIAL);
    setError('');
    setShowForm(true);
  };

  const abrirEditar = (u) => {
    setEditando(u);
    setForm({
      username:   u.username,
      nombre:     u.nombre,
      email:      u.email || '',
      password:   '',
      rol:        u.rol,
      catedra_id: u.catedra_id || '',
    });
    setError('');
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        username:   form.username,
        nombre:     form.nombre,
        email:      form.email || null,
        rol:        form.rol,
        catedra_id: form.catedra_id ? parseInt(form.catedra_id) : null,
      };

      if (editando) {
        // PATCH — solo enviar nueva_password si se llenó
        const update = { ...payload };
        delete update.username;          // username no se puede cambiar
        if (form.password) update.nueva_password = form.password;
        await updateUsuario(editando.id, update);
      } else {
        if (!form.password) { setError('La contraseña es requerida'); setSaving(false); return; }
        await createUsuario({ ...payload, password: form.password });
      }

      setShowForm(false);
      fetchAll();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActivo = async (u) => {
    if (u.id === user?.id) return;
    try {
      await updateUsuario(u.id, { activo: !u.activo });
      fetchAll();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error');
    }
  };

  const handleEliminar = async (u) => {
    if (!confirm(`¿Eliminar a "${u.username}"? Esta acción no se puede deshacer.`)) return;
    try {
      await deleteUsuario(u.id);
      fetchAll();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al eliminar');
    }
  };

  const nombreCatedra = (id) => catedras.find(c => c.id === id)?.nombre || '—';

  return (
    <div className="fade-in">
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Usuarios</h1>
          <p className="page-subtitle">Gestión de cuentas y permisos del sistema</p>
        </div>
        <button className="btn btn-primary" onClick={abrirNuevo}>+ Nuevo Usuario</button>
      </div>

      {/* Formulario crear/editar */}
      {showForm && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>
            {editando ? `Editando: ${editando.username}` : 'Nuevo Usuario'}
          </h3>

          {error && (
            <div style={{ background: 'var(--error-bg)', color: 'var(--error)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: 16, fontSize: 14 }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input
                  className="form-input"
                  value={form.username}
                  onChange={e => setForm({ ...form, username: e.target.value })}
                  required
                  disabled={!!editando}
                  placeholder="ej: jperez"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Nombre completo</label>
                <input
                  className="form-input"
                  value={form.nombre}
                  onChange={e => setForm({ ...form, nombre: e.target.value })}
                  required
                  placeholder="ej: Juan Pérez"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  className="form-input"
                  type="email"
                  value={form.email}
                  onChange={e => setForm({ ...form, email: e.target.value })}
                  placeholder="usuario@utn.frt.edu.ar"
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  {editando ? 'Nueva contraseña (dejar vacío para no cambiar)' : 'Contraseña'}
                </label>
                <input
                  className="form-input"
                  type="password"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                  required={!editando}
                  placeholder={editando ? 'Sin cambios' : 'Mínimo 8 caracteres'}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Rol</label>
                <select
                  className="form-input"
                  value={form.rol}
                  onChange={e => setForm({ ...form, rol: e.target.value })}
                >
                  <option value="catedra_admin">🎓 Cátedra</option>
                  <option value="admin">🔑 Administrador</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Cátedra asignada</label>
                <select
                  className="form-input"
                  value={form.catedra_id}
                  onChange={e => setForm({ ...form, catedra_id: e.target.value })}
                >
                  <option value="">Sin cátedra (solo admin)</option>
                  {catedras.map(c => (
                    <option key={c.id} value={c.id}>{c.nombre}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Guardando...' : editando ? 'Guardar cambios' : 'Crear usuario'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowForm(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tabla de usuarios */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Usuarios del sistema ({usuarios.length})</h3>
        </div>

        {usuarios.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Nombre</th>
                  <th>Email</th>
                  <th>Rol</th>
                  <th>Cátedra</th>
                  <th>2FA</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map(u => (
                  <tr key={u.id} style={{ opacity: u.activo ? 1 : 0.5 }}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div className="user-avatar" style={{ width: 32, height: 32, fontSize: 13 }}>
                          {u.nombre?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                        </div>
                        <code style={{ fontSize: 13 }}>{u.username}</code>
                      </div>
                    </td>
                    <td style={{ color: 'var(--text-primary)' }}>{u.nombre}</td>
                    <td style={{ fontSize: 13 }}>{u.email || '—'}</td>
                    <td>
                      <span className={`badge ${ROL_CONFIG[u.rol]?.badge || 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {ROL_CONFIG[u.rol]?.icon} {ROL_CONFIG[u.rol]?.label || u.rol}
                      </span>
                    </td>
                    <td>{nombreCatedra(u.catedra_id)}</td>
                    <td>
                      {u.totp_habilitado
                        ? <span className="badge success"><span className="badge-dot"></span>Activo</span>
                        : <span className="badge neutral">No</span>
                      }
                    </td>
                    <td>
                      <button
                        className={`badge ${u.activo ? 'success' : 'neutral'}`}
                        style={{ cursor: u.id === user?.id ? 'not-allowed' : 'pointer', border: 'none' }}
                        onClick={() => handleToggleActivo(u)}
                        title={u.id === user?.id ? 'No podés desactivarte a vos mismo' : ''}
                      >
                        <span className="badge-dot"></span>
                        {u.activo ? 'Activo' : 'Inactivo'}
                      </button>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => abrirEditar(u)}
                        >
                          ✏️ Editar
                        </button>
                        {u.id !== user?.id && (
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => handleEliminar(u)}
                          >
                            🗑️
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">👤</div>
            <p className="empty-state-text">{loading ? 'Cargando...' : 'Sin usuarios registrados'}</p>
          </div>
        )}
      </div>
    </div>
  );
}
