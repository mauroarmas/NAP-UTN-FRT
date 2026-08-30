import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Building2, ChevronDown, ClipboardCheck, LogOut,
  Package, Server, Settings, Users,
} from 'lucide-react';
import useTheme from '../hooks/useTheme';
import { iniciales } from './ui';
import utnLogo from '../assets/utn-logo.jpeg';

const LINKS = [
  { to: '/pedidos', label: 'Pedidos', icon: ClipboardCheck },
  { to: '/servicios', label: 'Servicios', icon: Server },
  { to: '/metricas', label: 'Métricas', icon: Activity },
];

const ADMIN_LINKS = [
  { to: '/catedras', label: 'Cátedras', icon: Building2 },
  { to: '/templates', label: 'Templates', icon: Package },
  { to: '/usuarios', label: 'Usuarios', icon: Users },
];

export default function TopNav({ user }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { toggle: toggleTheme } = useTheme();
  const [adminOpen, setAdminOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const adminRef = useRef(null);
  const menuRef = useRef(null);
  const lastY = useRef(0);

  const isAdmin = user?.rol === 'admin';

  // La barra se retira al bajar y vuelve al subir: gana lectura vertical en las
  // pantallas largas sin sacar la navegación de un gesto.
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY || 0;
      if (y > lastY.current + 4 && y > 80) setHidden(true);
      else if (y < lastY.current - 4 || y <= 80) setHidden(false);
      lastY.current = y;
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setAdminOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const onClick = (e) => {
      if (adminRef.current && !adminRef.current.contains(e.target)) setAdminOpen(false);
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
    window.location.reload();
  };

  const misCatedras = user?.catedras || [];
  const rolLabel = isAdmin
    ? 'Administrador'
    : misCatedras.length === 0
      ? 'Sin cátedra asignada'
      : misCatedras.length === 1
        ? misCatedras[0].nombre
        : `${misCatedras.length} cátedras`;

  return (
    <header className={`topnav ${hidden ? 'is-hidden' : ''}`}>
      <div className="topnav-inner">
        <button className="topnav-brand" onClick={() => navigate('/')} title="Ir al Dashboard">
          <img src={utnLogo} alt="UTN FRT" />
          <span className="topnav-brand-text">
            <span className="k">Facultad Regional Tucumán</span>
            <span className="n">Portal de Gestión</span>
          </span>
        </button>

        <div className="topnav-divider" />

        <nav className="topnav-links">
          {LINKS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `topnav-link ${isActive ? 'active' : ''}`}>
              <Icon size={16} />
              {label}
            </NavLink>
          ))}

          {isAdmin && (
            <div className="menu" ref={adminRef} style={{ marginLeft: 6 }}>
              <button
                className={`topnav-menu-trigger ${ADMIN_LINKS.some((l) => location.pathname.startsWith(l.to)) ? 'active' : ''}`}
                onClick={() => setAdminOpen((v) => !v)}
              >
                <Settings size={16} />
                Administración
                <ChevronDown size={14} />
              </button>
              {adminOpen && (
                <div className="menu-panel to-left">
                  {ADMIN_LINKS.map(({ to, label, icon: Icon }) => (
                    <NavLink key={to} to={to} className="menu-item">
                      <Icon size={15} />
                      {label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )}
        </nav>

        <div className="topnav-right">
          <button
            className="theme-switch"
            onClick={toggleTheme}
            aria-label="Cambiar tema"
            title="Cambiar tema claro / oscuro"
          >
            <span className="knob" />
          </button>

          <div className="topnav-divider" />

          <div className="menu" ref={menuRef}>
            <button
              className="avatar"
              onClick={() => setMenuOpen((v) => !v)}
              title={user?.nombre}
              aria-label="Cuenta"
            >
              {iniciales(user?.nombre)}
            </button>
            {menuOpen && (
              <div className="menu-panel to-right" style={{ minWidth: 232 }}>
                <div className="menu-head">
                  <span className="avatar" style={{ cursor: 'default' }}>{iniciales(user?.nombre)}</span>
                  <span className="who">
                    <span className="name">{user?.nombre || 'Usuario'}</span>
                    <span className="role" title={rolLabel}>{rolLabel}</span>
                  </span>
                </div>
                <button className="menu-item danger" onClick={logout}>
                  <LogOut size={15} />
                  Cerrar sesión
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
