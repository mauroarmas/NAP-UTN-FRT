import { useCallback, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Dialog } from './ui';
import BibliotecaAplicaciones from './BibliotecaAplicaciones';
import EnsayoPreparacion from './EnsayoPreparacion';

export default function AgregarServicioModal({ onClose, onGuardado }) {
  const [application, setApplication] = useState(null);
  const [operations, setOperations] = useState({});
  const busy = Object.values(operations).some(Boolean);
  const libraryBusy = useCallback((value) => setOperations((current) => ({ ...current, library: value })), []);
  const additionBusy = useCallback((value) => setOperations((current) => ({ ...current, addition: value })), []);
  const heading = useRef(null);
  const dismiss = () => { if (!busy) onClose(); };
  const finish = () => { onGuardado?.(); onClose(); };
  return <Dialog wide className="service-wizard" title="Agregar servicio" onClose={dismiss} closeDisabled={busy}>
    <div className="service-add-flow">
      {application && <>
        <button type="button" className="btn btn-ghost service-add-back" disabled={busy} onClick={() => { setApplication(null); requestAnimationFrame(() => heading.current?.focus()); }}><ArrowLeft size={15}/>Volver a la búsqueda</button>
        <h3 className="service-add-heading">{application.nombre}</h3>
      </>}
      <div ref={heading} tabIndex={-1} hidden={Boolean(application)}>
        <BibliotecaAplicaciones onBusyChange={libraryBusy} onContinue={setApplication}/>
      </div>
      {application && <EnsayoPreparacion key={application.id} incorporacion={application} onBusyChange={additionBusy} onPublished={finish}/>}
    </div>
  </Dialog>;
}
