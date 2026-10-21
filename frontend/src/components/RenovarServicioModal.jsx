import { useEffect, useRef, useState } from 'react';
import { renovarServicio, modificarVigencia } from '../services/api';
import ErrorFormulario from './ErrorFormulario';
import VigenciaFields from './VigenciaFields';
import { vigenciaInicial } from '../utils/vigencia';
import { Dialog } from './ui';

export default function RenovarServicioModal({ servicio, periodo, user, onClose, onCreated }) {
  const [dates, setDates] = useState(vigenciaInicial);
  const [valid, setValid] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  useEffect(() => {
    setDates(periodo ? { tipo: 'personalizado', desde: periodo.desde, hasta: periodo.hasta } : vigenciaInicial());
    setValid(false); setReason(''); setError(''); setBusy(false);
    key.current = crypto.randomUUID(); submitting.current = false;
  }, [servicio, periodo]);
  if (!servicio || (periodo && user?.rol !== 'admin')) return null;
  const submit = async (event) => {
    event.preventDefault();
    if (submitting.current || !valid || (periodo && !reason.trim())) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const body = { vigencia: dates, ...(periodo ? { sustituye_vigencia_id: periodo.id, motivo: reason.trim() } : {}) };
      const { data } = await (periodo ? modificarVigencia(servicio.id, periodo.id, body, key.current)
        : renovarServicio(servicio.id, body, key.current));
      onCreated?.(data); onClose();
    } catch (err) { setError(err); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog title={periodo ? 'Solicitar modificación del período' : 'Solicitar renovación'} onClose={onClose} closeDisabled={busy}>
    <form className="col gap-3" onSubmit={submit}>
      <p>{servicio.nombre_snapshot || servicio.hostname || `Servicio #${servicio.id}`}</p>
      <p>La solicitud requiere aprobación. Conserva el contenedor y sus datos; no enciende el servicio ni habilita los días sin cobertura. La reactivación comprueba capacidad disponible.</p>
      {periodo && <p>Se propone sustituir el período {periodo.desde} al {periodo.hasta}. La cobertura actual se conserva hasta aprobar la modificación.</p>}
      <ErrorFormulario error={error} />
      <fieldset disabled={busy}><VigenciaFields value={dates} onValid={setValid} onChange={(value) => { setDates(value); key.current = crypto.randomUUID(); }} /></fieldset>
      {periodo && <label>Motivo de modificación
        <textarea aria-label="Motivo de modificación" required maxLength={2000} value={reason} disabled={busy} onChange={(e) => { setReason(e.target.value); key.current = crypto.randomUUID(); }} />
      </label>}
      <div className="row gap-2">
        <button type="button" onClick={onClose} disabled={busy}>Cerrar</button>
        <button className="btn btn-primary" type="submit" disabled={busy || !valid || Boolean(periodo && !reason.trim())}>{busy ? 'Enviando…' : periodo ? 'Enviar solicitud de modificación' : 'Enviar solicitud de renovación'}</button>
      </div>
    </form>
  </Dialog>;
}
