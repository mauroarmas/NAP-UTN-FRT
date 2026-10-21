import { useId, useRef, useState } from 'react';
import { registrarEvidencia } from '../services/api';
import { mensajeError } from '../utils/errors';

export default function RegistroEvidencia({ onRegistered, onDocumentRegistered, onDraftChange, disabled = false }) {
  const id = useId();
  const [documento, setDocumento] = useState('');
  const [registro, setRegistro] = useState(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  const registrar = async (event) => {
    event.preventDefault();
    if (submitting.current || disabled) return;
    setError('');
    if (new TextEncoder().encode(documento).length > 65536) {
      setError('El documento supera el límite de 64 KiB.');
      return;
    }
    submitting.current = true; setSaving(true);
    try {
      // Se conserva el texto original: el servidor detecta claves duplicadas.
      const { data } = await registrarEvidencia(documento, key.current);
      setRegistro(data);
      onRegistered?.(data);
      if (onDocumentRegistered) {
        let parsed = null;
        try { parsed = JSON.parse(documento); } catch { /* La validación corresponde al servidor. */ }
        onDocumentRegistered(data, parsed);
      }
    } catch (err) {
      setError(mensajeError(err, 'No se pudo registrar la evidencia.'));
    } finally {
      submitting.current = false; setSaving(false);
    }
  };
  return <section className="card">
    <h3>Registrar evidencia institucional</h3>
    <p>Importá el documento JSON emitido tras la comprobación institucional. Registrarlo devuelve una referencia; la confirmación del cambio se realiza por separado.</p>
    <form onSubmit={registrar}>
      <div className="field">
        <label htmlFor={id}>Documento de evidencia</label>
        <textarea id={id} className="input" rows={8} disabled={saving || disabled} value={documento} onChange={(e) => { setDocumento(e.target.value); setRegistro(null); key.current = crypto.randomUUID(); onDraftChange?.(); }} required spellCheck={false} />
        <p className="card-meta">Máximo 64 KiB. No incluyas contraseñas, tokens ni códigos de recuperación.</p>
      </div>
      <button className="btn btn-primary" disabled={saving || disabled || !documento.trim()}>{saving ? 'Registrando…' : 'Registrar evidencia'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {registro && <div role="status"><p>Referencia: <code>{registro.evidencia_ref}</code></p><p>SHA-256: <code>{registro.sha256}</code></p></div>}
  </section>;
}
