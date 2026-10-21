import { mensajeError } from '../utils/errors';
import { useState, useEffect, useId } from 'react';
import { UserPlus, Pencil, Users, Trash2 } from 'lucide-react';
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
  recibir_notificaciones_email: true,
};

export default function Usuarios({ user }) {
  const formId = useId();
  const [usuarios, setUsuarios] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editando, setEditando] = useState(null);
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [pendiente, setPendiente] = useState(null);
  const registrarPendiente = (response) => { if (response.status === 202) setPendiente(response.data.cambio_consola_id); };

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
      recibir_notificaciones_email: u.recibir_notificaciones_email !== undefined ? u.recibir_notificaciones_email : true,
    });
    setError('');
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (saving) return;
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
        if (form.rol === 'admin') {
          update.recibir_notificaciones_email = form.recibir_notificaciones_email;
        }
        registrarPendiente(await updateUsuario(editando.id, { ...update, revision_esperada: editando.revision_admin }));
      } else {
        if (!form.email || !form.email.trim()) {
          setError('El email es obligatorio para enviar la contraseña provisoria');
          setSaving(false);
          return;
        }
        await createUsuario(payload);
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
        setError(mensajeError(err, 'Error al guardar'));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActivo = async (u) => {
    if (u.id === user?.id) return;
    try {
      registrarPendiente(await updateUsuario(u.id, { activo: !u.activo, revision_esperada: u.revision_admin }));
      fetchAll();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'catedras_sin_responsable') {
        alert(`No se puede desactivar a "${u.nombre}": quedarían sin responsable las cátedras ${d.catedras.map((c) => c.nombre).join(', ')}.\n\nReasignalas a otra persona o dalas de baja primero.`);
      } else {
        alert(mensajeError(err, 'No se pudo guardar el cambio'));
      }
    }
  };

  const handleEliminar = async (u) => {
    if (!confirm(`¿Dar de baja a "${u.username}"? Se conservará la identidad del historial. Si tiene acceso nativo, el retiro quedará pendiente de revocación institucional.`)) return;
    try {
      const response = await retirarUsuario(u.id, u.revision_admin);
      registrarPendiente(response);
      const { data } = response;
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
          <UserPlus size={17} /><span>Nuevo usuario</span>
        </button>
      </PageHead>

      {pendiente && <p role="status">Cambio pendiente de revocación institucional. Referencia: <code>{pendiente}</code>. <a href="/admin/cambios-consola">Seguir trámite</a></p>}

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
          onClose={() => setShowForm(false)} closeDisabled={saving}
          actions={
            <>
              <button className="btn btn-secondary" onClick={() => setShowForm(false)} disabled={saving}>Cancelar</button>
              <button className="btn btn-primary" type="submit" form={formId + '-form'} disabled={saving}>
                {saving ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear usuario'}
              </button>
            </>
          }
        >
          {error && <div role="alert" id={formId + '-error'} className="login__error" style={{ textAlign: 'left', marginBottom: 'var(--space-3)' }}>{error}</div>}

          <form id={formId + '-form'} onSubmit={handleSubmit} aria-describedby={error ? formId + '-error' : undefined}><fieldset disabled={saving} style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
            <div className="grid cols-2">
              <div className="field">
                <label htmlFor={formId + '-username'}>Username</label>
                <input id={formId + '-username'} className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required disabled={!!editando} placeholder="ej: jperez" />
              </div>
              <div className="field">
                <label htmlFor={formId + '-nombre'}>Nombre completo</label>
                <input id={formId + '-nombre'} className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required placeholder="ej: Juan Pérez" />
              </div>
              <div className="field">
                <label htmlFor={formId + '-email'}>Email *</label>
                <input id={formId + '-email'} className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required placeholder="usuario@frt.utn.edu.ar" />
              </div>
              <div className="field">
                <label htmlFor={formId + '-rol'}>Rol</label>
                <select id={formId + '-rol'} className="input" value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
                  <option value="catedra_admin">Responsable de cátedra</option>
                  <option value="admin">Administrador</option>
                </select>
              </div>
              {editando ? (
                <div className="field" style={{ gridColumn: 'span 2' }}>
                  <label htmlFor={formId + '-password'}>Nueva contraseña (dejar vacío para mantener la actual)</label>
                  <input id={formId + '-password'} className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Sin cambios" />
                </div>
              ) : (
                <div className="field" style={{ gridColumn: 'span 2' }}>
                  <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', background: 'var(--color-bg-subtle, #f8fafc)', padding: '10px 14px', borderRadius: '4px', border: '1px solid var(--color-border, #e2e8f0)' }}>
                    ℹ️ <strong>Contraseña provisoria:</strong> El sistema generará automáticamente una credencial aleatoria segura y la enviará al correo del usuario para su primer ingreso.
                  </div>
                </div>
              )}
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

            {form.rol === 'admin' && (
              <div className="field" style={{ marginTop: 'var(--space-3)' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: 'normal' }}>
                  <input
                    type="checkbox"
                    checked={form.recibir_notificaciones_email}
                    onChange={(e) => setForm({ ...form, recibir_notificaciones_email: e.target.checked })}
                  />
                  <span>Recibir notificaciones por correo electrónico (nuevos pedidos y alertas operativas)</span>
                </label>
              </div>
            )}
          </fieldset></form>
        </Dialog>
      )}
    </div>
  );
}
