import { useCallback, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Dialog } from './ui';
import BibliotecaAplicaciones from './BibliotecaAplicaciones';
import AplicacionPropiaForm from './AplicacionPropiaForm';

export default function AgregarServicioModal({ onClose, onGuardado }) {
  const [application, setApplication] = useState(null);
  const [source, setSource] = useState('biblioteca');
  const [operations, setOperations] = useState({});
  const busy = Object.values(operations).some(Boolean);
  const libraryBusy = useCallback((value) => setOperations((current) => ({ ...current, library: value })), []);
  const additionBusy = useCallback((value) => setOperations((current) => ({ ...current, addition: value })), []);
  const heading = useRef(null);

  const dismiss = () => {
    if (!busy) onClose();
  };
  const finish = () => {
    onGuardado?.();
    onClose();
  };

  return (
    <Dialog wide className="service-wizard" title="Agregar servicio" onClose={dismiss} closeDisabled={busy}>
      <div className="service-add-flow">
        <div className="own-application-source" role="group" aria-label="Origen del servicio">
          <button
            type="button"
            className={`btn ${source === 'biblioteca' ? 'btn-primary' : 'btn-secondary'}`}
            disabled={busy}
            aria-pressed={source === 'biblioteca'}
            onClick={() => {
              setSource('biblioteca');
              setApplication(null);
            }}
          >
            Docker Hub
          </button>
          <button
            type="button"
            className={`btn ${source === 'imagen' ? 'btn-primary' : 'btn-secondary'}`}
            disabled={busy}
            aria-pressed={source === 'imagen'}
            onClick={() => {
              setSource('imagen');
              setApplication(null);
            }}
          >
            Imagen propia
          </button>
        </div>

        {source === 'imagen' ? (
          <AplicacionPropiaForm onAdded={finish} onBusyChange={additionBusy} />
        ) : (
          <>
            {application && (
              <>
                <button
                  type="button"
                  className="btn btn-ghost service-add-back"
                  disabled={busy}
                  onClick={() => {
                    setApplication(null);
                    requestAnimationFrame(() => heading.current?.focus());
                  }}
                >
                  <ArrowLeft size={15} />
                  Volver a la búsqueda
                </button>
                <h3 className="service-add-heading">{application.nombre}</h3>
                <AplicacionPropiaForm
                  key={application.repositorio || application.nombre}
                  initialValues={{
                    nombre: (application.nombre || '').split('/').pop(),
                    imagen: application.referencia || application.repositorio || '',
                    descripcion: application.descripcion || '',
                  }}
                  onAdded={finish}
                  onBusyChange={additionBusy}
                />
              </>
            )}

            <div ref={heading} tabIndex={-1} hidden={Boolean(application)}>
              <BibliotecaAplicaciones
                onBusyChange={libraryBusy}
                onContinue={setApplication}
                onManualEntry={() => {
                  setSource('imagen');
                  setApplication(null);
                }}
              />
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
