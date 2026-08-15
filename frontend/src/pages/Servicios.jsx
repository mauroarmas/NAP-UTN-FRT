import { useState, useEffect, useRef } from 'react';
import { getPedidos, listarServicios, desplegarPedido, iniciarServicio, detenerServicio, reiniciarServicio, eliminarServicio, getStatusServicio, getCatedras, getBaseConsolaProxmox } from '../services/api';

const ESTADO_SERVICIO_CONFIG = {
  running:  { label: 'Corriendo',  badge: 'success', icon: '🟢' },
  stopped:  { label: 'Detenido',  badge: 'neutral',  icon: '⏹️' },
  paused:   { label: 'Pausado',   badge: 'warning',  icon: '⏸️' },
  error:    { label: 'Error',     badge: 'error',    icon: '⚠️' },
};

// Cada cuánto se re-consulta el estado real de los contenedores. El backend
// reconcilia contra Proxmox en cada listado, así que este intervalo es lo que
// hace que la vista siga al contenedor y no al revés.
const INTERVALO_REFRESCO_MS = 10000;

export default function Servicios({ user }) {
  const [servicios, setServicios] = useState([]);
  const [pedidosAprobados, setPedidosAprobados] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accionando, setAccionando] = useState(null); // ID del servicio/pedido en acción
  const [statusDetalle, setStatusDetalle] = useState(null);
  const [proxmoxBase, setProxmoxBase] = useState(null); // URL de Proxmox, solo admin
  const [actualizadoAt, setActualizadoAt] = useState(null);
  const accionandoRef = useRef(null); // el refresco automático no debe pisar una acción en curso

  const isAdmin = user?.rol === 'admin';

  const marcarAccion = (valor) => {
    accionandoRef.current = valor;
    setAccionando(valor);
  };

  const fetchData = async () => {
    try {
      const [srvRes, pedRes, catRes, baseRes] = await Promise.allSettled([
        listarServicios(),
        isAdmin ? getPedidos('aprobado') : Promise.resolve({ data: [] }),
        isAdmin ? getCatedras() : Promise.resolve({ data: [] }),
        isAdmin ? getBaseConsolaProxmox() : Promise.resolve({ data: {} }),
      ]);
      if (srvRes.status === 'fulfilled') {
        setServicios(srvRes.value.data);
        setActualizadoAt(new Date());
      }
      if (pedRes.status === 'fulfilled') setPedidosAprobados(pedRes.value.data);
      if (catRes.status === 'fulfilled') setCatedras(catRes.value.data);
      if (baseRes.status === 'fulfilled') setProxmoxBase(baseRes.value.data.base_url || null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Consola nativa de Proxmox (xterm.js). Solo para admin: requiere sesión
  // propia en Proxmox, y la cátedra no debe llegar nunca a esa interfaz.
  const urlConsolaProxmox = (s) =>
    `${proxmoxBase}/?console=lxc&xtermjs=1&vmid=${s.proxmox_vmid}` +
    `&vmname=${encodeURIComponent(s.hostname || '')}&node=${encodeURIComponent(s.proxmox_node || '')}&cmd=`;

  const catedraNombre = (id) => catedras.find(c => c.id === id)?.nombre || `Cátedra #${id}`;

  useEffect(() => {
    fetchData();
    const timer = setInterval(() => {
      if (!accionandoRef.current) fetchData();
    }, INTERVALO_REFRESCO_MS);
    return () => clearInterval(timer);
  }, []);

  const handleDesplegar = async (pedidoId) => {
    if (!confirm(`¿Desplegar pedido #${pedidoId} en Proxmox?`)) return;
    marcarAccion(`deploy-${pedidoId}`);
    try {
      await desplegarPedido(pedidoId);
      await fetchData();
      alert(`✅ Pedido #${pedidoId} desplegado exitosamente`);
    } catch (err) {
      alert(`❌ Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      marcarAccion(null);
    }
  };

  const handleStart = async (id) => {
    marcarAccion(`start-${id}`);
    try {
      await iniciarServicio(id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
      await fetchData(); // el rechazo puede venir de un estado ya cambiado: re-sincronizar
    } finally {
      marcarAccion(null);
    }
  };

  const handleStop = async (id) => {
    if (!confirm('¿Detener el servicio?')) return;
    marcarAccion(`stop-${id}`);
    try {
      await detenerServicio(id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleRestart = async (id) => {
    if (!confirm('¿Reiniciar el servicio?')) return;
    marcarAccion(`restart-${id}`);
    try {
      await reiniciarServicio(id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  // Cierra el registro del portal liberando el contenedor. Si el contenedor ya
  // no existe (lo borraron desde Proxmox), el backend igual cierra el registro.
  const handleEliminar = async (s) => {
    const huerfano = s.existe_en_proxmox === false;
    const aviso = huerfano
      ? `El contenedor ${s.proxmox_vmid} ya no existe en Proxmox.\n¿Dar de baja el registro del servicio?`
      : `¿Dar de baja el servicio y eliminar el contenedor ${s.proxmox_vmid} en Proxmox?\nEsta acción no se puede deshacer.`;
    if (!confirm(aviso)) return;
    marcarAccion(`delete-${s.id}`);
    try {
      await eliminarServicio(s.id);
      await fetchData();
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleStatus = async (id) => {
    try {
      const { data } = await getStatusServicio(id);
      setStatusDetalle(data);
    } catch (err) {
      alert(`❌ ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <h1 className="page-title">Servicios</h1>
          <p className="page-subtitle">Contenedores desplegados en Proxmox VE</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <button className="btn btn-secondary btn-sm" onClick={fetchData}>🔄 Actualizar</button>
          <div className="stat-label" style={{ marginTop: 6, fontSize: 11 }}>
            {actualizadoAt
              ? `Estado real al ${actualizadoAt.toLocaleTimeString('es-AR')}`
              : 'Consultando Proxmox...'}
          </div>
        </div>
      </div>

      {/* Stats rápidas */}
      <div className="cards-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-icon green">🟢</div>
          <div className="stat-value">{servicios.filter(s => s.estado === 'running').length}</div>
          <div className="stat-label">Corriendo</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon orange">⏹️</div>
          <div className="stat-value">{servicios.filter(s => s.estado === 'stopped').length}</div>
          <div className="stat-label">Detenidos</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon purple">📦</div>
          <div className="stat-value">{servicios.length}</div>
          <div className="stat-label">Total desplegados</div>
        </div>
      </div>

      {/* Pedidos aprobados esperando despliegue — solo admin */}
      {isAdmin && pedidosAprobados.length > 0 && (
        <div className="card" style={{ marginBottom: 24, borderColor: 'var(--accent)' }}>
          <div className="card-header">
            <h3 className="card-title">🚀 Pedidos listos para desplegar</h3>
            <span className="badge info">
              <span className="badge-dot"></span>
              {pedidosAprobados.length} pendiente{pedidosAprobados.length > 1 ? 's' : ''}
            </span>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Pedido</th>
                  <th>Cátedra</th>
                  <th>Template</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {pedidosAprobados.map(p => (
                  <tr key={p.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>#{p.id}</td>
                    <td>{catedraNombre(p.catedra_id)}</td>
                    <td>Template #{p.template_id}</td>
                    <td>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleDesplegar(p.id)}
                        disabled={accionando === `deploy-${p.id}`}
                      >
                        {accionando === `deploy-${p.id}` ? '⏳ Desplegando...' : '🚀 Desplegar'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detalle de status Proxmox */}
      {statusDetalle && (
        <div className="card fade-in" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3 className="card-title">Estado en Proxmox — VMID {statusDetalle.vmid}</h3>
            <button className="btn btn-secondary btn-sm" onClick={() => setStatusDetalle(null)}>✕</button>
          </div>
          <pre style={{ fontSize: 12, color: 'var(--text-secondary)', overflowX: 'auto', background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-sm)' }}>
            {JSON.stringify(statusDetalle.proxmox_status, null, 2)}
          </pre>
        </div>
      )}

      {/* Lista de servicios */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Contenedores ({servicios.length})</h3>
        </div>

        {servicios.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>VMID</th>
                  <th>Hostname</th>
                  <th>Nodo</th>
                  <th>Recursos</th>
                  <th>Estado</th>
                  <th>Desplegado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {servicios.map(s => (
                  <tr key={s.id}>
                    <td style={{ color: 'var(--accent)', fontWeight: 600, fontFamily: 'monospace' }}>
                      {s.proxmox_vmid || '—'}
                    </td>
                    <td style={{ color: 'var(--text-primary)' }}>{s.hostname || '—'}</td>
                    <td>{s.proxmox_node || '—'}</td>
                    <td style={{ fontSize: 12 }}>
                      ⚡{s.vcpus_asignados}v · 💾{s.ram_asignada_mb}MB · 💿{s.disk_asignado_gb}GB
                    </td>
                    <td>
                      <span className={`badge ${ESTADO_SERVICIO_CONFIG[s.estado]?.badge || 'neutral'}`}>
                        <span className="badge-dot"></span>
                        {ESTADO_SERVICIO_CONFIG[s.estado]?.icon} {ESTADO_SERVICIO_CONFIG[s.estado]?.label || s.estado}
                      </span>
                      {/* Dos avisos distintos: el contenedor ya no existe (registro
                          huérfano, hay que darlo de baja) o simplemente no se pudo
                          confirmar el estado (Proxmox no respondió). */}
                      {s.existe_en_proxmox === false ? (
                        <div
                          className="stat-label"
                          style={{ fontSize: 11, marginTop: 4, color: 'var(--error, #ef4444)' }}
                          title="El contenedor fue eliminado desde Proxmox. El registro sigue acá para el historial de consumo: dalo de baja para cerrarlo."
                        >
                          🗑️ ya no existe en Proxmox
                        </div>
                      ) : s.estado_sincronizado === false && (
                        <div
                          className="stat-label"
                          style={{ fontSize: 11, marginTop: 4 }}
                          title="Proxmox no respondió: este es el último estado conocido"
                        >
                          ⚠️ sin confirmar
                        </div>
                      )}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {s.deployed_at ? new Date(s.deployed_at).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {/* Sin contenedor detrás, las acciones de ciclo de vida
                            solo pueden fallar: lo único que queda por hacer es
                            cerrar el registro. */}
                        {s.existe_en_proxmox === false ? (
                          isAdmin ? (
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleEliminar(s)}
                              disabled={accionando === `delete-${s.id}`}
                            >
                              {accionando === `delete-${s.id}` ? '⏳' : '🗑️ Dar de baja'}
                            </button>
                          ) : (
                            <span className="stat-label" style={{ fontSize: 11 }}>
                              Avisá al administrador
                            </span>
                          )
                        ) : (
                        <>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleStatus(s.id)}
                          title="Ver estado en Proxmox"
                        >📊</button>
                        {/* Start disponible en todo estado que no sea "corriendo"
                            (detenido, pausado o error): encender es la salida de
                            todos ellos y la forma de recuperar un contenedor que
                            quedó caído, por ejemplo tras reiniciar Proxmox. */}
                        {s.estado !== 'running' && (
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handleStart(s.id)}
                            disabled={accionando === `start-${s.id}`}
                            title="Encender el contenedor en Proxmox"
                          >
                            {accionando === `start-${s.id}` ? '⏳' : '▶ Start'}
                          </button>
                        )}
                        {s.estado === 'running' && (
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => handleStop(s.id)}
                            disabled={accionando === `stop-${s.id}`}
                          >
                            {accionando === `stop-${s.id}` ? '⏳' : '⏹ Stop'}
                          </button>
                        )}
                        {s.estado === 'running' && (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleRestart(s.id)}
                            disabled={accionando === `restart-${s.id}`}
                          >
                            {accionando === `restart-${s.id}` ? '⏳' : '🔁 Reiniciar'}
                          </button>
                        )}
                        {isAdmin && proxmoxBase && s.estado === 'running' && s.proxmox_vmid && (
                          <a
                            className="btn btn-secondary btn-sm"
                            href={urlConsolaProxmox(s)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Abrir la consola de Proxmox en otra pestaña (requiere sesión en Proxmox)"
                          >
                            🖥️ Consola
                          </a>
                        )}
                        {isAdmin && (
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => handleEliminar(s)}
                            disabled={accionando === `delete-${s.id}`}
                            title="Dar de baja el servicio y liberar el contenedor en Proxmox"
                          >
                            {accionando === `delete-${s.id}` ? '⏳' : '🗑️'}
                          </button>
                        )}
                        </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🖥️</div>
            <p className="empty-state-text">
              {loading ? 'Cargando...' : 'No hay servicios desplegados aún'}
            </p>
            {isAdmin && !loading && (
              <p className="stat-label">Aprobá un pedido y desplegalo desde esta vista</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
