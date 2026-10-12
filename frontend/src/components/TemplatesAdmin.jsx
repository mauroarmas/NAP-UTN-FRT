import { useState, useEffect } from 'react';
import { AlertCircle } from 'lucide-react';
import { createTemplate, updateTemplate, getProxmoxTemplates } from '../services/api';
import { Dialog } from './ui';

const FORM_INICIAL = {
  nombre: '',
  descripcion: '',
  modelo_servicio: 'iaas',
  tipo: 'lxc',
  default_vcpus: 1,
  default_ram_mb: 256,
  default_disk_gb: 2,
  justificacion_disco: '',
  os_template: '',
};

export default function TemplatesAdmin({ open, template, onClose, onGuardado }) {
  const [form, setForm] = useState(FORM_INICIAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [osTemplates, setOsTemplates] = useState([]);
  const [loadingOs, setLoadingOs] = useState(true);
  const [osError, setOsError] = useState(false);

  const editando = !!template;

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (template) {
      setForm({
        nombre: template.nombre || '',
        descripcion: template.descripcion || '',
        modelo_servicio: template.modelo_servicio || 'iaas',
        tipo: template.tipo || 'lxc',
        default_vcpus: template.default_vcpus || 1,
        default_ram_mb: template.default_ram_mb || 256,
        default_disk_gb: template.default_disk_gb || 2,
        justificacion_disco: template.justificacion_disco || '',
        os_template: template.os_template || '',
      });
    } else {
      setForm(FORM_INICIAL);
    }
  }, [open, template]);

  useEffect(() => {
    if (!open) return;
    setLoadingOs(true);
    getProxmoxTemplates()
      .then(({ data }) => setOsTemplates(data))
      .catch(() => setOsError(true))
      .finally(() => setLoadingOs(false));
  }, [open]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    setSaving(true);
    try {
      const payload = {
        ...form,
        os_template: form.os_template || null,
        justificacion_disco: form.justificacion_disco.trim() || null,
      };

      if (editando) {
        delete payload.tipo; // El tipo no se puede cambiar
        const { data } = await updateTemplate(template.id, payload);
        if (onGuardado) onGuardado(data);
      } else {
        const { data } = await createTemplate(payload);
        if (onGuardado) onGuardado(data);
      }
      onClose();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === 'string' ? d : d?.mensaje || 'Error al guardar la plantilla.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={editando ? `Corregir plantilla: ${template.nombre}` : 'Nuevo template de recurso'}
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button type="submit" form="form-template-admin" className="btn btn-primary" disabled={saving}>
            {saving ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear template'}
          </button>
        </>
      }
    >
      <form id="form-template-admin" onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {error && (
          <div className="callout bad">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="grid cols-2">
          <div className="field">
            <label>Nombre de la plantilla</label>
            <input
              className="input"
              value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              required
              placeholder="Ej: LXC Small Docker"
            />
          </div>

          <div className="field">
            <label>Modelo de Servicio</label>
            <select
              className="input"
              value={form.modelo_servicio}
              onChange={(e) => setForm({ ...form, modelo_servicio: e.target.value })}
            >
              <option value="iaas">IaaS (Infraestructura / VMs / Contenedores)</option>
              <option value="paas">PaaS (Plataforma / Modelos / APIs)</option>
              <option value="saas">SaaS (Software / Moodle / Apps)</option>
            </select>
          </div>
        </div>

        <div className="grid cols-2">
          <div className="field">
            <label>Tipo de Recurso</label>
            <select
              className="input"
              value={form.tipo}
              disabled={editando}
              title={editando ? 'El tipo de recurso no se puede alterar en plantillas existentes' : undefined}
              onChange={(e) => setForm({ ...form, tipo: e.target.value })}
            >
              <option value="lxc">LXC (Contenedor)</option>
              <option value="qemu">QEMU (Máquina Virtual)</option>
            </select>
          </div>

          <div className="field">
            <label>OS Template (Proxmox)</label>
            {osError ? (
              <input
                className="input"
                value={form.os_template}
                onChange={(e) => setForm({ ...form, os_template: e.target.value })}
                placeholder="local:vztmpl/debian-12-standard.tar.zst"
              />
            ) : (
              <select
                className="input"
                value={form.os_template}
                onChange={(e) => setForm({ ...form, os_template: e.target.value })}
                disabled={loadingOs}
              >
                <option value="">{loadingOs ? 'Cargando templates…' : 'Sin template específico'}</option>
                {osTemplates.map((t) => (
                  <option key={t.volid} value={t.volid}>
                    {t.volid.split('/').pop()}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="field">
          <label>Descripción</label>
          <input
            className="input"
            value={form.descripcion}
            onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
            placeholder="Propósito, software instalado o especificaciones de la plantilla"
          />
        </div>

        <div className="grid cols-3">
          <div className="field">
            <label>vCPUs</label>
            <input
              className="input"
              type="number"
              min="1"
              value={form.default_vcpus}
              onChange={(e) => setForm({ ...form, default_vcpus: parseInt(e.target.value) || 1 })}
              required
            />
          </div>
          <div className="field">
            <label>RAM (MB)</label>
            <input
              className="input"
              type="number"
              min="64"
              step="64"
              value={form.default_ram_mb}
              onChange={(e) => setForm({ ...form, default_ram_mb: parseInt(e.target.value) || 64 })}
              required
            />
          </div>
          <div className="field">
            <label>Disco (GB)</label>
            <input
              className="input"
              type="number"
              min="1"
              value={form.default_disk_gb}
              onChange={(e) => setForm({ ...form, default_disk_gb: parseInt(e.target.value) || 1 })}
              required
            />
          </div>
        </div>
      </form>
    </Dialog>
  );
}

