export default function Servicios() {
  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Servicios</h1>
        <p className="page-subtitle">Servicios desplegados y activos</p>
      </div>
      <div className="card">
        <div className="empty-state">
          <div className="empty-state-icon">🖥️</div>
          <p className="empty-state-text">No hay servicios desplegados aún</p>
        </div>
      </div>
    </div>
  );
}
