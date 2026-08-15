import { useEffect, useRef, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

export default function Sidebar({ user }) {
  const navigate = useNavigate();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const menuRef = useRef(null);

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

  useEffect(() => {
    if (!menuAbierto) return;
    const cerrarSiEsAfuera = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuAbierto(false);
      }
    };
    document.addEventListener('mousedown', cerrarSiEsAfuera);
    return () => document.removeEventListener('mousedown', cerrarSiEsAfuera);
  }, [menuAbierto]);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">☁️</div>
          <div>
            <div className="sidebar-logo-text">NAP</div>
            <div className="sidebar-logo-sub">Nube Académica Personal -</div>
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

        <NavLink to="/metricas" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-item-icon">📈</span>
          Métricas
        </NavLink>
      </nav>

      <div className="sidebar-footer" ref={menuRef}>
        <div className="user-menu">
          <div className="user-info">
            <div className="user-avatar">{initials}</div>
            <div className="user-details">
              <div className="user-name">{user?.nombre || 'Usuario'}</div>
              <div className="user-role">{isAdmin ? 'Administrador' : 'Cátedra'}</div>
            </div>
            <button
              className="user-menu-trigger"
              onClick={() => setMenuAbierto(v => !v)}
              aria-label="Opciones de administrador"
              title="Opciones"
            >
              ⚙️
            </button>
          </div>

          {menuAbierto && (
            <div className="user-menu-dropdown">
              {isAdmin && (
                <>
                  <NavLink
                    to="/catedras"
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => setMenuAbierto(false)}
                  >
                    <span className="nav-item-icon">🏛️</span>
                    Cátedras
                  </NavLink>

                  <NavLink
                    to="/templates"
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => setMenuAbierto(false)}
                  >
                    <span className="nav-item-icon">📦</span>
                    Templates
                  </NavLink>

                  <NavLink
                    to="/usuarios"
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => setMenuAbierto(false)}
                  >
                    <span className="nav-item-icon">👥</span>
                    Usuarios
                  </NavLink>

                  <div className="user-menu-divider"></div>
                </>
              )}
              <button className="nav-item" onClick={handleLogout} style={{ color: 'var(--error)' }}>
                <span className="nav-item-icon">🚪</span>
                Cerrar Sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
