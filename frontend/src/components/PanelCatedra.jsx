import Servicios from '../pages/Servicios';
import Metricas from '../pages/Metricas';

export default function PanelCatedra({ user }) {
  return (
    <div className="fade-in">
      <Servicios user={user} />

      <hr
        style={{
          border: 'none',
          borderTop: '1px solid var(--color-divider)',
          margin: 'var(--space-8) 0 var(--space-6)',
        }}
      />

      <Metricas user={user} />
    </div>
  );
}
