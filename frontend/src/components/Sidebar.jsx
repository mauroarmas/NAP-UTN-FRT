import { NavLink, useNavigate } from 'react-router-dom';

export default function Sidebar({ user }) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
    window.location.reload();
  };

  const isAdmin = user?.rol === 'admin';
  const initials = user?.nombre
    ? user.nombre.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : '??';

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">☁️</div>
          <div>
            <div className="sidebar-logo-text">Nube UTN</div>
            <div className="sidebar-logo-sub">Portal de Gestión</div>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">General</div>
        <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-item-icon">📊</span>
          Dashboard
        </NavLink>

        <NavLink to="/pedidos" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-item-icon">📋</span>
          Pedidos
        </NavLink>

        <NavLink to="/servicios" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-item-icon">🖥️</span>
          Servicios
        </NavLink>

        {isAdmin && (
          <>
            <div className="sidebar-section-label">Administración</div>
            <NavLink to="/catedras" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-item-icon">🏛️</span>
              Cátedras
            </NavLink>

            <NavLink to="/templates" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-item-icon">📦</span>
              Templates
            </NavLink>

            <NavLink to="/usuarios" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-item-icon">👥</span>
              Usuarios
            </NavLink>

            <NavLink to="/proxmox" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-item-icon">⚙️</span>
              Proxmox VE
            </NavLink>
          </>
        )}
      </nav>

      <div className="sidebar-footer">
        <div className="user-info">
          <div className="user-avatar">{initials}</div>
          <div className="user-details">
            <div className="user-name">{user?.nombre || 'Usuario'}</div>
            <div className="user-role">{isAdmin ? 'Administrador' : 'Cátedra'}</div>
          </div>
        </div>
        <button className="nav-item" onClick={handleLogout} style={{ marginTop: 8, color: 'var(--error)' }}>
          <span className="nav-item-icon">🚪</span>
          Cerrar Sesión
        </button>
      </div>
    </aside>
  );
}
