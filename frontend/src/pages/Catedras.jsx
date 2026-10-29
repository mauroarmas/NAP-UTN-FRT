import { mensajeError } from '../utils/errors.js';
import { useState, useEffect, useId, useRef } from 'react';
import { Send, Pencil, Building2, ShieldCheck } from 'lucide-react';
import { getCatedras, createCatedra, updateCatedra, getCatedra, getUsuarios, verificarInfraCatedra } from '../services/api';
import { PageHead, StatusPill, Empty, Dialog, ConfirmDialog } from '../components/ui';

/**
 * Administración de cátedras. La pantalla giraba alrededor de las cuotas; eso
 * desapareció. Lo que queda es identidad: quién responde por cada materia, y su
 * consumo vigente como dato informativo.
 */

const FORM_INICIAL = { nombre: '', descripcion: '', titular_id: '', activa: true };

export default function Catedras() {
  const formId = useId();
  const [catedras, setCatedras] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editando, setEditando] = useState(null);
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [confirmacion, setConfirmacion] = useState(null);
  const [error, setError] = useState('');
  const [uso, setUso] = useState(null);
  const [revision, setRevision] = useState(null);
  const [pendiente, setPendiente] = useState(null);
  const [infra, setInfra] = useState({});
  const [infraDetalle, setInfraDetalle] = useState(null);
  const infraRequest = useRef(0);
  const infraLabels = { preparada: ['Preparada', 'ok'], sin_servicios: ['Sin servicios', 'off'], requiere_atencion: ['Requiere atención', 'warn'] };
  const verificarInfra = async (category) => {
    const request = ++infraRequest.current;
    setInfraDetalle({ category, loading: true });
    try {
      const { data } = await verificarInfraCatedra(category.id);
      if (request !== infraRequest.current) return;
      setInfra((current) => ({ ...current, [category.id]: data }));
      setInfraDetalle((current) => current?.category.id === category.id ? { category, data } : current);
    } catch {
      if (request !== infraRequest.current) return;
      setInfra((current) => ({ ...current, [category.id]: { estado: 'requiere_atencion' } }));
      setInfraDetalle((current) => current?.category.id === category.id ? { category,
        error: 'No se pudo verificar la infraestructura. Volvé a consultar; no se cambió el pool.' } : current);
    }
  };
  const registrarPendiente = (response) => { if (response.status === 202) setPendiente(response.data.cambio_consola_id); };

  const fetchTodo = async () => {
    try {
      const [c, u] = await Promise.all([getCatedras(), getUsuarios()]);
      setCatedras(c.data);
      setInfra({});
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
    setError('');
    setShowForm(true);
  };

  const abrirEdicion = async (c) => {
    setEditando(c.id);
    setRevision(c.revision_admin);
    setForm({ nombre: c.nombre, descripcion: c.descripcion || '', titular_id: c.titular_id || '', activa: c.activa });
    setUso(null);
    setError('');
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
    if (editando) return updateCatedra(editando, { ...payload, activa: form.activa, revision_esperada: revision }, { confirmar });
    return createCatedra(payload);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (saving) return;
    setError('');
    setSaving(true);
    try {
      registrarPendiente(await guardar());
      cerrarForm();
      fetchTodo();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'servicios_vigentes') {
        setConfirmacion({
          title: 'Servicios vigentes en la cátedra',
          message: d.mensaje,
          detail: 'Los servicios no se eliminan, pero la cátedra dejará de figurar como activa. ¿Deseás continuar igual?',
          confirmText: 'Continuar de todos modos',
          danger: true,
          onConfirm: async () => {
            setSaving(true);
            try {
              registrarPendiente(await guardar(true));
              cerrarForm();
              fetchTodo();
            } catch (e2) {
              setError(mensajeError(e2, 'Error al dar de baja la cátedra'));
            } finally {
              setSaving(false);
            }
          },
        });
      } else {
        setError(mensajeError(err, 'Error al guardar la cátedra'));
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

      {pendiente && <p role="status">Cambio pendiente de revocación institucional. Referencia: <code>{pendiente}</code>. <a href="/admin/cambios-consola">Seguir trámite</a></p>}

      <div className="card">
        <div className="card-header">
          <div className="card-title">Listado</div>
          <span className="section-count">{catedras.length} cátedras</span>
        </div>
        {catedras.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr><th>ID</th><th>Nombre</th><th>Descripción</th><th>Responsable</th><th>Estado</th><th>Pool de recursos</th><th className="right">Acciones</th></tr>
              </thead>
              <tbody>
                {catedras.map((c) => (
                  <tr key={c.id}>
                    <td className="tabnum cell-strong">{c.id}</td>
                    <td className="cell-strong nowrap">{c.nombre}</td>
                    <td style={{ color: 'var(--text-soft)' }}>{c.descripcion || '—'}</td>
                    <td className="nowrap">
                      {c.titular ? c.titular.nombre : <StatusPill kind="warn">Sin responsable</StatusPill>}
                    </td>
                    <td><StatusPill kind={c.activa ? 'ok' : 'off'}>{c.activa ? 'Activa' : 'Inactiva'}</StatusPill></td>
                    <td>{infra[c.id] ? <StatusPill kind={infraLabels[infra[c.id].estado]?.[1] || 'warn'}>{infraLabels[infra[c.id].estado]?.[0] || 'Requiere atención'}</StatusPill>
                      : <span className="card-meta">Sin verificar</span>}</td>
                    <td className="right">
                      <button className="btn btn-ghost btn-sm" onClick={() => verificarInfra(c)} aria-label={`Verificar infraestructura de ${c.nombre}`}>
                        <ShieldCheck size={13} aria-hidden="true" /> Verificar infraestructura
                      </button>
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

      {infraDetalle && <Dialog title={`Infraestructura de ${infraDetalle.category.nombre}`} onClose={() => { infraRequest.current += 1; setInfraDetalle(null); }}>
        <div className="col gap-3">
          {infraDetalle.loading && <p role="status">Comprobando el pool y los permisos del portal…</p>}
          {infraDetalle.error && <p role="alert">{infraDetalle.error}</p>}
          {infraDetalle.data && <>
            <p>Pool: <strong>{infraDetalle.data.pool}</strong></p>
            <StatusPill kind={infraLabels[infraDetalle.data.estado]?.[1] || 'warn'}>{infraLabels[infraDetalle.data.estado]?.[0] || 'Requiere atención'}</StatusPill>
            <p>{infraDetalle.data.mensaje}</p>
            {infraDetalle.data.permisos_faltantes?.length > 0 && <details><summary>Detalle para administración</summary>
              <p>Permisos faltantes: {infraDetalle.data.permisos_faltantes.join(', ')}.</p>
            </details>}
          </>}
          <p className="card-meta">Esta consulta no crea pools ni mueve contenedores. El pool se prepara automáticamente al desplegar un servicio y no establece cuotas.</p>
          {!infraDetalle.loading && <button className="btn btn-secondary" onClick={() => verificarInfra(infraDetalle.category)}>Volver a verificar</button>}
        </div>
      </Dialog>}

      {showForm && (
        <Dialog
          title={editando ? `Editar cátedra` : 'Nueva cátedra'}
          onClose={cerrarForm} closeDisabled={saving}
          actions={
            <>
              <button className="btn btn-secondary" onClick={cerrarForm} disabled={saving}>Cancelar</button>
              <button className="btn btn-primary" type="submit" form={formId + '-form'} disabled={saving}>
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

          {error && <p role="alert" id={formId + '-error'}>{error}</p>}
          <form id={formId + '-form'} onSubmit={handleSubmit} aria-describedby={error ? formId + '-error' : undefined}><fieldset disabled={saving} style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
            <div className="field">
              <label htmlFor={formId + '-nombre'}>Nombre</label>
              <input id={formId + '-nombre'} className="input" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required placeholder="Ej: Análisis Matemático" />
              <p className="card-meta" style={{ marginTop: 4 }}>Dos personas distintas pueden dictar materias con el mismo nombre.</p>
            </div>

            <div className="field">
              <label htmlFor={formId + '-descripcion'}>Descripción</label>
              <input id={formId + '-descripcion'} className="input" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Descripción opcional" />
            </div>

            <div className="field">
              <label htmlFor={formId + '-titular_id'}>Responsable</label>
              <select id={formId + '-titular_id'} className="input" value={form.titular_id} onChange={(e) => setForm({ ...form, titular_id: e.target.value })}>
                <option value="">Sin responsable asignado</option>
                {usuarios.filter((u) => u.activo).map((u) => (
                  <option key={u.id} value={u.id}>{u.nombre} ({u.username})</option>
                ))}
              </select>
              <p className="card-meta" style={{ marginTop: 4 }}>Reasignar el responsable no mueve servicios ni historial: son de la cátedra.</p>
            </div>

            {editando && (
              <div className="field">
                <label htmlFor={formId + '-activa'}>Estado</label>
                <select id={formId + '-activa'} className="input" value={form.activa ? 'activa' : 'inactiva'} onChange={(e) => setForm({ ...form, activa: e.target.value === 'activa' })}>
                  <option value="activa">Activa</option>
                  <option value="inactiva">Inactiva</option>
                </select>
                <p className="card-meta" style={{ marginTop: 4 }}>Dar de baja una cátedra con servicios vigentes pide confirmación.</p>
              </div>
            )}
          </fieldset></form>
        </Dialog>
      )}

      {confirmacion && (
        <ConfirmDialog
          title={confirmacion.title}
          message={confirmacion.message}
          detail={confirmacion.detail}
          confirmText={confirmacion.confirmText || 'Aceptar'}
          cancelText={confirmacion.cancelText || 'Cancelar'}
          danger={confirmacion.danger}
          busy={saving}
          onClose={() => setConfirmacion(null)}
          onConfirm={async () => {
            const fn = confirmacion.onConfirm;
            setConfirmacion(null);
            await fn();
          }}
        />
      )}
    </div>
  );
}
