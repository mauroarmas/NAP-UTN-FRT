import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Pedidos from './pages/Pedidos';
import Servicios from './pages/Servicios';
import Catedras from './pages/Catedras';
import Templates from './pages/Templates';
import ProxmoxPanel from './pages/ProxmoxPanel';
import Sidebar from './components/Sidebar';
import './index.css';

function ProtectedLayout({ user }) {
  return (
    <div className="app-layout">
      <Sidebar user={user} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard user={user} />} />
          <Route path="/pedidos" element={<Pedidos user={user} />} />
          <Route path="/servicios" element={<Servicios />} />
          {user?.rol === 'admin' && (
            <>
              <Route path="/catedras" element={<Catedras />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/proxmox" element={<ProxmoxPanel />} />
            </>
          )}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    const token = localStorage.getItem('token');
    if (storedUser && token) {
      setUser(JSON.parse(storedUser));
    }
    setLoading(false);
  }, []);

  if (loading) return null;

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            user ? <Navigate to="/" replace /> : <Login onLogin={setUser} />
          }
        />
        <Route
          path="/*"
          element={
            user ? <ProtectedLayout user={user} /> : <Navigate to="/login" replace />
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
