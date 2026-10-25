import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Building2, ChevronDown, ClipboardCheck, Home, LogOut,
  Moon, Package, Server, Settings, Sun, Users, CalendarDays, Shield,
} from 'lucide-react';
import useTheme from '../hooks/useTheme';
import { iniciales } from './ui';
import utnLogo from '../assets/utn-logo.jpeg';

const LINKS = [
  { to: '/catalogo', label: 'Catálogo', icon: Package },
  { to: '/pedidos', label: 'Pedidos', icon: ClipboardCheck },
  { to: '/servicios', label: 'Servicios', icon: Server },
  { to: '/metricas', label: 'Métricas', icon: Activity },
];

const CATEDRA_LINKS = [
  { to: '/catalogo', label: 'Catálogo', icon: Package },
  { to: '/pedidos', label: 'Pedidos', icon: ClipboardCheck },
];

const ADMIN_LINKS = [
  { to: '/definiciones', label: 'Definiciones', icon: Package },
  { to: '/calendario', label: 'Calendario', icon: CalendarDays },
  { to: '/catedras', label: 'Cátedras', icon: Building2 },
  { to: '/templates', label: 'Perfiles', icon: Package },
  { to: '/usuarios', label: 'Usuarios', icon: Users },
  { to: '/admin/cambios-consola', label: 'Accesos a consola', icon: Settings },
];

export default function TopNav({ user, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const [adminOpen, setAdminOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const adminRef = useRef(null);
  const menuRef = useRef(null);
  const lastY = useRef(0);

  const isAdmin = user?.rol === 'admin';
  const isDark = theme === 'dark';

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

  const logout = async () => {
    if (await onLogout()) navigate('/login');
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
            <span className="k">UTN-FRT</span>
            <span className="n">NAP</span>
          </span>
        </button>

        <div className="topnav-divider" />

        <nav className="topnav-links">
          {(isAdmin ? LINKS : CATEDRA_LINKS).map(({ to, label, icon: Icon }) => (
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

        <div className="topnav-right" style={{ marginLeft: 'auto' }}>
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

                {/* Separador */}
                <div style={{ height: 1, background: 'var(--color-divider)', margin: '4px 0' }} />

                {/* Para cátedra, acceso directo a Inicio */}
                {!isAdmin && (
                  <NavLink
                    to="/"
                    end
                    className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
                    onClick={() => setMenuOpen(false)}
                  >
                    <Home size={15} />
                    Inicio
                  </NavLink>
                )}

                {/* Seguridad (para admin y cátedra) */}
                <NavLink
                  to="/seguridad"
                  className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
                  onClick={() => setMenuOpen(false)}
                >
                  <Shield size={15} />
                  Seguridad
                </NavLink>

                {/* Separador */}
                <div style={{ height: 1, background: 'var(--color-divider)', margin: '4px 0' }} />

                {/* Toggle de tema dentro del menú del usuario */}
                <button
                  className="menu-item"
                  onClick={() => { toggleTheme(); }}
                  style={{ justifyContent: 'space-between' }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {isDark ? <Moon size={15} /> : <Sun size={15} />}
                    {isDark ? 'Modo oscuro' : 'Modo claro'}
                  </span>
                  {/* Mini switch visual */}
                  <span style={{
                    display: 'inline-flex', alignItems: 'center',
                    width: 32, height: 18, borderRadius: 9,
                    background: isDark ? 'var(--color-accent)' : 'var(--color-divider)',
                    padding: 2, transition: 'background 0.2s', flexShrink: 0,
                  }}>
                    <span style={{
                      width: 14, height: 14, borderRadius: '50%',
                      background: 'var(--color-surface)',
                      transform: isDark ? 'translateX(14px)' : 'translateX(0)',
                      transition: 'transform 0.2s',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                    }} />
                  </span>
                </button>

                {/* Separador */}
                <div style={{ height: 1, background: 'var(--color-divider)', margin: '4px 0' }} />

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

