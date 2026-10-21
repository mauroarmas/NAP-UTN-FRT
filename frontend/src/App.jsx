import { Component, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Login from './pages/Login';
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Pedidos = lazy(() => import('./pages/Pedidos'));
const Catalogo = lazy(() => import('./pages/Catalogo'));
const Servicios = lazy(() => import('./pages/Servicios'));
const Catedras = lazy(() => import('./pages/Catedras'));
const Templates = lazy(() => import('./pages/Templates'));
const Usuarios = lazy(() => import('./pages/Usuarios'));
const CambiosConsola = lazy(() => import('./pages/CambiosConsola'));
const Calendario = lazy(() => import('./pages/Calendario'));
const Definiciones = lazy(() => import('./pages/Definiciones'));
const Metricas = lazy(() => import('./pages/Metricas'));
import TopNav from './components/TopNav';
import CambiarPasswordInicialModal from './components/CambiarPasswordInicialModal';
import useSession from './hooks/useSession';
import Seguridad, { CodigosRecuperacion, DesafioIngreso } from './pages/Seguridad';
import './index.css';

class RouteErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="callout bad">
      <p>No se pudo cargar esta vista. Podés volver a cargarla o elegir otra sección.</p>
      <button className="btn btn-secondary" onClick={() => window.location.reload()}>Volver a cargar la vista</button>
    </div>;
    return this.props.children;
  }
}

function ProtectedLayout({ user, onRefresh, onLogout }) {
  const location = useLocation();
  return (
    <div className="app-shell">
      <TopNav user={user} onLogout={onLogout} />
      <main className="app-main">
        <div className="app-main-inner">
          <RouteErrorBoundary key={location.pathname}><Suspense fallback={<p role="status">Cargando vista…</p>}><Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/pedidos" element={<Pedidos user={user} />} />
            <Route path="/catalogo" element={<Catalogo user={user} />} />
            <Route path="/servicios" element={<Servicios user={user} />} />
            <Route path="/metricas" element={<Metricas user={user} />} />
            <Route path="/seguridad" element={<Seguridad key={String(user?.totp_habilitado)} user={user} onRefresh={onRefresh} />} />
            {user?.rol === 'admin' && (
              <>
                <Route path="/definiciones" element={<Definiciones />} />
                <Route path="/catedras" element={<Catedras />} />
                <Route path="/calendario" element={<Calendario />} />
                <Route path="/templates" element={<Templates />} />
                <Route path="/admin/templates" element={<Templates />} />
                <Route path="/usuarios" element={<Usuarios user={user} />} />
                <Route path="/admin/cambios-consola" element={<CambiosConsola user={user} />} />
              </>
            )}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes></Suspense></RouteErrorBoundary>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const { session, user, loading, error, refresh, logout, codes, clearCodes } = useSession();
  if (loading) return <p role="status">Consultando sesión…</p>;
  let content;
  if (codes) content = <CodigosRecuperacion codes={codes} onClose={clearCodes} />;
  else if (session?.estado === 'onboarding') content = <CambiarPasswordInicialModal user={user} onPasswordCambiada={refresh} />;
  else if (session?.estado === 'mfa_pending') content = <DesafioIngreso session={session} onRefresh={refresh} />;
  else if (session?.estado === 'recovery') content = <Seguridad user={user} recovery onRefresh={refresh} />;
  else if (session?.estado === 'operativo') content = <Routes><Route path="/*" element={<ProtectedLayout user={user} onRefresh={refresh} onLogout={logout} />} /></Routes>;
  else content = <Login onLogin={refresh} />;
  return <BrowserRouter>
    {error && <p role="alert">{error}</p>}
    {session?.estado === 'operativo' && !codes ? content : <div className="login fade-in"><div className="login__center">{content}</div>{session && <button className="btn btn-secondary" onClick={logout}>Cerrar sesión</button>}</div>}
  </BrowserRouter>;
}
