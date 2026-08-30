import { useState, useEffect } from 'react';
import { Send, Pencil, Users, Trash2 } from 'lucide-react';
import { getUsuarios, createUsuario, updateUsuario, retirarUsuario, getCatedras } from '../services/api';
import SelectorCatedras from '../components/SelectorCatedras';
import { PageHead, StatusPill, Empty, Dialog, iniciales } from '../components/ui';

const ROL = {
  admin: { label: 'Administrador', kind: 'accent' },
  catedra_admin: { label: 'Responsable de cátedra', kind: 'off' },
};

const FORM_INICIAL = {
  username: '', nombre: '', email: '', password: '',
  rol: 'catedra_admin', catedra_ids: [],
};

export default function Usuarios({ user }) {
  const [usuarios, setUsuarios] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editando, setEditando] = useState(null);
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fetchAll = async () => {
    try {
      const [u, c] = await Promise.all([getUsuarios(), getCatedras()]);
      setUsuarios(u.data);
      setCatedras(c.data);
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
      username: u.username, nombre: u.nombre, email: u.email || '', password: '',
      rol: u.rol, catedra_ids: (u.catedras || []).map((c) => c.id),
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
        username: form.username, nombre: form.nombre, email: form.email || null,
        rol: form.rol, catedra_ids: form.catedra_ids,
      };
      if (form.rol !== 'admin' && form.catedra_ids.length === 0) {
        setError('Asigná al menos una cátedra.');
        setSaving(false);
        return;
      }
      if (editando) {
        const update = { ...payload };
        delete update.username;
        if (form.password) update.nueva_password = form.password;
        await updateUsuario(editando.id, update);
      } else {
        if (!form.password) { setError('La contraseña es requerida'); setSaving(false); return; }
        await createUsuario({ ...payload, password: form.password });
      }
      setShowForm(false);
      fetchAll();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'catedras_ya_asignadas') {
        const nombres = d.catedras_no_disponibles.map((c) => `${c.nombre}${c.titular ? ` (${c.titular})` : ''}`).join(', ');
        setError(`No se creó el usuario. Estas cátedras ya tienen responsable: ${nombres}. Actualizá la lista y elegí otras.`);
        fetchAll();
      } else {
        setError(typeof d === 'string' ? d : 'Error al guardar');
      }
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
      const d = err.response?.data?.detail;
      if (d?.codigo === 'catedras_sin_responsable') {
        alert(`No se puede desactivar a "${u.nombre}": quedarían sin responsable las cátedras ${d.catedras.map((c) => c.nombre).join(', ')}.\n\nReasignalas a otra persona o dalas de baja primero.`);
      } else {
        alert(typeof d === 'string' ? d : 'Error');
      }
    }
  };

  const handleEliminar = async (u) => {
    // El texto ya no promete un borrado irreversible: si la persona dejó
    // historial, la cuenta se da de baja y sus pedidos siguen figurando. Es el
    // backend quien decide, y quien devuelve el resultado real.
    if (!confirm(
      `¿Dar de baja a "${u.username}"?\n\n` +
      'Si creó pedidos alguna vez, la cuenta queda desactivada y su historial se ' +
      'conserva. Si nunca usó el sistema, se elimina.'
    )) return;
    try {
      const { data } = await retirarUsuario(u.id);
      if (data?.mensaje) alert(data.mensaje);
      fetchAll();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'catedras_sin_responsable') {
        const nombres = (d.catedras || []).map((c) => c.nombre).join(', ');
        alert(`${d.mensaje}\n\nCátedras a cargo: ${nombres}`);
      } else {
        alert(typeof d === 'string' ? d : d?.mensaje || 'No se pudo dar de baja la cuenta');
      }
    }
  };

  const catedrasDe = (u) => (u.catedras || []).length > 0 ? u.catedras.map((c) => c.nombre).join(', ') : '—';

  return (
    <div className="fade-in">
      <PageHead kicker="Administración" title="Usuarios" subtitle="Cuentas, roles y asignación a cátedras.">
        <button className="btn-send" onClick={abrirNuevo}>
          <Send size={17} /><span>Invitar usuario</span>
        </button>
      </PageHead>

      <div className="card">
        <div className="card-header">
          <div className="card-title">Cuentas del portal</div>
          <span className="section-count">{usuarios.length} usuarios</span>
        </div>
        {usuarios.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr><th>Usuario</th><th>Correo</th><th>Rol</th><th>Cátedras</th><th>2FA</th><th>Estado</th><th className="right">Acciones</th></tr>
              </thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id} style={{ opacity: u.activo ? 1 : 0.55 }}>
                    <td className="nowrap">
                      <span className="row gap-2">
                        <span className="avatar" style={{ width: 30, height: 30, fontSize: 11, cursor: 'default' }}>{iniciales(u.nombre)}</span>
                        <span className="col" style={{ lineHeight: 1.2 }}>
                          <span className="cell-strong">{u.nombre}</span>
                          <code style={{ fontSize: 11, color: 'var(--text-faint)' }}>{u.username}</code>
                        </span>
                      </span>
                    </td>
                    <td className="nowrap" style={{ color: 'var(--text-soft)' }}>{u.email || '—'}</td>
                    <td className="nowrap">
                      {u.rol === 'admin'
                        ? <StatusPill kind="accent">{ROL.admin.label}</StatusPill>
                        : <span style={{ fontSize: 13, color: 'var(--text-body)' }}>{ROL[u.rol]?.label || u.rol}</span>}
                    </td>
                    <td style={{ fontSize: 13 }}>{catedrasDe(u)}</td>
                    <td>{u.totp_habilitado ? <StatusPill kind="ok">Sí</StatusPill> : <span className="card-meta">No</span>}</td>
                    <td>
                      <button
                        onClick={() => handleToggleActivo(u)}
                        style={{ border: 0, background: 'none', padding: 0, cursor: u.id === user?.id ? 'not-allowed' : 'pointer' }}
                        title={u.id === user?.id ? 'No podés desactivarte a vos mismo' : 'Cambiar estado'}
                      >
                        <StatusPill kind={u.activo ? 'ok' : 'off'}>{u.activo ? 'Activo' : 'Inactivo'}</StatusPill>
                      </button>
                    </td>
                    <td>
                      <div className="row gap-1" style={{ justifyContent: 'flex-end' }}>
                        <button className="btn-icon" title="Editar" onClick={() => abrirEditar(u)}><Pencil size={15} /></button>
                        {u.id !== user?.id && (
                          <button className="btn-icon danger" title="Eliminar" onClick={() => handleEliminar(u)}><Trash2 size={15} /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={<Users size={22} />}>{loading ? 'Cargando…' : 'Sin usuarios registrados.'}</Empty>
        )}
      </div>

      {showForm && (
        <Dialog
          wide
          title={editando ? `Editar: ${editando.username}` : 'Nuevo usuario'}
          onClose={() => setShowForm(false)}
          actions={
            <>
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
                {saving ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear usuario'}
              </button>
            </>
          }
        >
          {error && <div className="login__error" style={{ textAlign: 'left', marginBottom: 'var(--space-3)' }}>{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="grid cols-2">
              <div className="field">
                <label>Username</label>
                <input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required disabled={!!editando} placeholder="ej: jperez" />
              </div>
              <div className="field">
                <label>Nombre completo</label>
                <input className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required placeholder="ej: Juan Pérez" />
              </div>
              <div className="field">
                <label>Email</label>
                <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="usuario@frt.utn.edu.ar" />
              </div>
              <div className="field">
                <label>{editando ? 'Nueva contraseña (vacío = sin cambio)' : 'Contraseña'}</label>
                <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required={!editando} placeholder={editando ? 'Sin cambios' : 'Mínimo 8 caracteres'} />
              </div>
              <div className="field">
                <label>Rol</label>
                <select className="input" value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
                  <option value="catedra_admin">Responsable de cátedra</option>
                  <option value="admin">Administrador</option>
                </select>
              </div>
            </div>

            <div className="field">
              <label>Cátedras a cargo{form.rol === 'admin' && ' (opcional para un administrador)'}</label>
              <SelectorCatedras
                catedras={catedras}
                seleccionadas={form.catedra_ids}
                onChange={(ids) => setForm({ ...form, catedra_ids: ids })}
                idsPropios={editando ? (editando.catedras || []).map((c) => c.id) : []}
                disabled={saving}
              />
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
