import { useState, useEffect } from 'react';
import { Send, Pencil, Building2 } from 'lucide-react';
import { getCatedras, createCatedra, updateCatedra, getCatedra, getUsuarios } from '../services/api';
import { PageHead, StatusPill, Empty, Dialog } from '../components/ui';

/**
 * Administración de cátedras. La pantalla giraba alrededor de las cuotas; eso
 * desapareció. Lo que queda es identidad: quién responde por cada materia, y su
 * consumo vigente como dato informativo.
 */

const FORM_INICIAL = { nombre: '', descripcion: '', titular_id: '', activa: true };

export default function Catedras() {
  const [catedras, setCatedras] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editando, setEditando] = useState(null);
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [uso, setUso] = useState(null);

  const fetchTodo = async () => {
    try {
      const [c, u] = await Promise.all([getCatedras(), getUsuarios()]);
      setCatedras(c.data);
      setUsuarios(u.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTodo(); }, []);

  const abrirAlta = () => {
    setEditando(null);
    setForm(FORM_INICIAL);
    setUso(null);
    setShowForm(true);
  };

  const abrirEdicion = async (c) => {
    setEditando(c.id);
    setForm({ nombre: c.nombre, descripcion: c.descripcion || '', titular_id: c.titular_id || '', activa: c.activa });
    setUso(null);
    setShowForm(true);
    try {
      const { data } = await getCatedra(c.id);
      setUso({ vcpus: data.vcpus_en_uso, ram_mb: data.ram_en_uso_mb, storage_gb: data.storage_en_uso_gb, servicios_activos: data.servicios_activos });
    } catch {
      setUso(null);
    }
  };

  const cerrarForm = () => { setShowForm(false); setEditando(null); setUso(null); };

  const guardar = async (confirmar = false) => {
    const payload = {
      nombre: form.nombre,
      descripcion: form.descripcion,
      titular_id: form.titular_id ? parseInt(form.titular_id) : null,
    };
    if (editando) await updateCatedra(editando, { ...payload, activa: form.activa }, { confirmar });
    else await createCatedra(payload);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await guardar();
      cerrarForm();
      fetchTodo();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'servicios_vigentes') {
        if (confirm(`${d.mensaje}\n\nLos servicios no se eliminan, pero la cátedra deja de figurar como activa.\n¿Continuar igual?`)) {
          try {
            await guardar(true);
            cerrarForm();
            fetchTodo();
          } catch (e2) {
            alert(e2.response?.data?.detail || 'Error al dar de baja la cátedra');
          }
        }
      } else {
        alert(typeof d === 'string' ? d : 'Error al guardar la cátedra');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fade-in">
      <PageHead kicker="Administración" title="Cátedras" subtitle="Materias del sistema y quién responde por cada una.">
        <button className="btn-send" onClick={abrirAlta}>
          <Send size={17} /><span>Nueva cátedra</span>
        </button>
      </PageHead>

      <div className="card">
        <div className="card-header">
          <div className="card-title">Listado</div>
          <span className="section-count">{catedras.length} cátedras</span>
        </div>
        {catedras.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr><th>Nombre</th><th>Descripción</th><th>Responsable</th><th>Estado</th><th className="right">Acciones</th></tr>
              </thead>
              <tbody>
                {catedras.map((c) => (
                  <tr key={c.id}>
                    <td className="cell-strong nowrap">{c.nombre}</td>
                    <td style={{ color: 'var(--text-soft)' }}>{c.descripcion || '—'}</td>
                    <td className="nowrap">
                      {c.titular ? c.titular.nombre : <StatusPill kind="warn">Sin responsable</StatusPill>}
                    </td>
                    <td><StatusPill kind={c.activa ? 'ok' : 'off'}>{c.activa ? 'Activa' : 'Inactiva'}</StatusPill></td>
                    <td className="right">
                      <button className="btn btn-secondary btn-sm" onClick={() => abrirEdicion(c)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={<Building2 size={22} />}>{loading ? 'Cargando…' : 'No hay cátedras registradas.'}</Empty>
        )}
      </div>

      {showForm && (
        <Dialog
          title={editando ? `Editar cátedra` : 'Nueva cátedra'}
          onClose={cerrarForm}
          actions={
            <>
              <button className="btn btn-secondary" onClick={cerrarForm}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
                {saving ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear cátedra'}
              </button>
            </>
          }
        >
          {editando && (
            <p className="card-meta" style={{ marginBottom: 'var(--space-3)' }}>
              {uso
                ? `Consumo vigente: ${uso.vcpus} vCPU · ${uso.ram_mb} MB · ${uso.storage_gb} GB (${uso.servicios_activos} servicio${uso.servicios_activos === 1 ? '' : 's'} activo${uso.servicios_activos === 1 ? '' : 's'}).`
                : 'Consultando consumo actual…'}
            </p>
          )}

          <form onSubmit={handleSubmit}>
            <div className="field">
              <label>Nombre</label>
              <input className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required placeholder="Ej: Análisis Matemático" />
              <p className="card-meta" style={{ marginTop: 4 }}>Dos personas distintas pueden dictar materias con el mismo nombre.</p>
            </div>

            <div className="field">
              <label>Descripción</label>
              <input className="input" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Descripción opcional" />
            </div>

            <div className="field">
              <label>Responsable</label>
              <select className="input" value={form.titular_id} onChange={(e) => setForm({ ...form, titular_id: e.target.value })}>
                <option value="">Sin responsable asignado</option>
                {usuarios.filter((u) => u.activo).map((u) => (
                  <option key={u.id} value={u.id}>{u.nombre} ({u.username})</option>
                ))}
              </select>
              <p className="card-meta" style={{ marginTop: 4 }}>Reasignar el responsable no mueve servicios ni historial: son de la cátedra.</p>
            </div>

            {editando && (
              <div className="field">
                <label>Estado</label>
                <select className="input" value={form.activa ? 'activa' : 'inactiva'} onChange={(e) => setForm({ ...form, activa: e.target.value === 'activa' })}>
                  <option value="activa">Activa</option>
                  <option value="inactiva">Inactiva</option>
                </select>
                <p className="card-meta" style={{ marginTop: 4 }}>Dar de baja una cátedra con servicios vigentes pide confirmación.</p>
              </div>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}
