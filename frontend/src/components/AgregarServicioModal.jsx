import { useCallback, useRef, useState } from 'react';
import { ArrowLeft, Search, Wrench, Rocket } from 'lucide-react';
import { Dialog } from './ui';
import TemplatesAdmin from './TemplatesAdmin';
import BibliotecaAplicaciones from './BibliotecaAplicaciones';
import EnsayoPreparacion from './EnsayoPreparacion';

export default function AgregarServicioModal({ initialLibrary = false, onClose, onGuardado }) {
  const [stage, setStage] = useState(initialLibrary ? 'biblioteca' : 'elegir');
  const [libraryVisited, setLibraryVisited] = useState(initialLibrary);
  const [application, setApplication] = useState(null);
  const [preparationStep,setPreparationStep]=useState(1);
  const [operations, setOperations] = useState({});
  const busy = Object.values(operations).some(Boolean);
  const formBusy = useCallback((value) => setOperations((current) => ({ ...current, form: value })), []);
  const libraryBusy = useCallback((value) => setOperations((current) => ({ ...current, library: value })), []);
  const preparationBusy = useCallback((value) => setOperations((current) => ({ ...current, preparation: value })), []);
  const heading = useRef(null);
  const changeStage = (next) => { if (busy) return; if (next === 'biblioteca') setLibraryVisited(true); setStage(next); requestAnimationFrame(() => heading.current?.focus()); };
  const dismiss = () => { if (!busy) onClose(); };
  const finish = () => { onGuardado?.(); onClose(); };
  const progress=<ol className="wizard-progress" aria-label="Pasos del alta">
        {[['Elegir aplicación',Search],['Preparar',Wrench],['Publicar',Rocket]].map(([label,Icon],index)=><li key={label} className={index===(stage==='preparar'?preparationStep:0)?'is-current':''} aria-current={index===(stage==='preparar'?preparationStep:0)?'step':undefined}><span><Icon size={18}/></span><div><small>Paso {index+1}</small><strong>{label}</strong></div></li>)}
      </ol>;
  return <Dialog wide className="service-wizard" headerContent={progress} title="Agregar servicio" onClose={dismiss} closeDisabled={busy}>
    <div className="service-add-flow">
      {stage !== 'elegir' && <button type="button" className="btn btn-ghost service-add-back" disabled={busy}
        onClick={() => changeStage(stage === 'preparar' ? 'biblioteca' : 'elegir')}><ArrowLeft size={15} />
        {stage === 'preparar' ? 'Volver a la búsqueda' : 'Elegir una aplicación preparada'}</button>}
      <h3 ref={heading} tabIndex={-1} className={`service-add-heading ${stage==='biblioteca'?'sr-only':''}`}>{stage === 'elegir' ? 'Elegí tu aplicación' : stage === 'biblioteca' ? 'Buscar aplicación' : `Preparar y publicar ${application.nombre}`}</h3>
      {stage === 'elegir' && <TemplatesAdmin open embedded onClose={dismiss} onGuardado={finish}
        onBuscar={() => changeStage('biblioteca')} onBusyChange={formBusy} />}
      {libraryVisited && <div className="service-add-library" hidden={stage !== 'biblioteca'}>
        <BibliotecaAplicaciones onBusyChange={libraryBusy} onContinue={(row) => { setApplication(row); changeStage('preparar'); }} />
      </div>}
      {stage === 'preparar' && <EnsayoPreparacion key={application.id} incorporacion={application} onBusyChange={preparationBusy} onStepChange={setPreparationStep} onPublished={finish} />}

    </div>
  </Dialog>;
}
