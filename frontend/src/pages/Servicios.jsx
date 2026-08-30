import { useState, useEffect, useRef } from 'react';
import {
  RefreshCw, Play, Square, RotateCw, Trash2, Terminal, Activity,
  Pin, PinOff, CalendarClock, Send,
} from 'lucide-react';
import {
  getPedidos, listarServicios, desplegarPedido, iniciarServicio, detenerServicio,
  reiniciarServicio, eliminarServicio, getStatusServicio, getCatedras,
  getBaseConsolaProxmox, reactivarServicio, actualizarServicio, renovarServicio,
} from '../services/api';
import { PageHead, StatusPill, Empty, Dialog } from '../components/ui';

const CFG = {
  running: { label: 'Corriendo', kind: 'ok' },
  stopped: { label: 'Detenido', kind: 'off' },
  paused:  { label: 'Pausado', kind: 'warn' },
  error:   { label: 'Error', kind: 'bad' },
};

// El backend reconcilia contra Proxmox en cada listado; este intervalo es lo que
// hace que la vista siga al contenedor y no al revés.
const INTERVALO_REFRESCO_MS = 10000;

export default function Servicios({ user }) {
  const [servicios, setServicios] = useState([]);
  const [pedidosAprobados, setPedidosAprobados] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accionando, setAccionando] = useState(null);
  const [statusDetalle, setStatusDetalle] = useState(null);
  const [proxmoxBase, setProxmoxBase] = useState(null);
  const [actualizadoAt, setActualizadoAt] = useState(null);
  const accionandoRef = useRef(null);

  const isAdmin = user?.rol === 'admin';

  const marcarAccion = (v) => { accionandoRef.current = v; setAccionando(v); };

  const fetchData = async () => {
    try {
      const [srvRes, pedRes, catRes, baseRes] = await Promise.allSettled([
        listarServicios(),
        isAdmin ? getPedidos('aprobado') : Promise.resolve({ data: [] }),
        isAdmin ? getCatedras() : Promise.resolve({ data: [] }),
        getBaseConsolaProxmox(),
      ]);
      if (srvRes.status === 'fulfilled') { setServicios(srvRes.value.data); setActualizadoAt(new Date()); }
      if (pedRes.status === 'fulfilled') setPedidosAprobados(pedRes.value.data);
      if (catRes.status === 'fulfilled') setCatedras(catRes.value.data);
      if (baseRes.status === 'fulfilled') setProxmoxBase(baseRes.value.data.base_url || null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(() => { if (!accionandoRef.current) fetchData(); }, INTERVALO_REFRESCO_MS);
    return () => clearInterval(timer);
  }, []);

  const catedraNombre = (id) => catedras.find((c) => c.id === id)?.nombre || `Cátedra #${id}`;

  // Única excepción al Principio I (enmienda constitucional v3.0.0): Proxmox no
  // acepta API tokens para el WebSocket de consola, así que el portal no puede
  // hacer de proxy. Sin esta derivación la cátedra no tendría forma de entrar a
  // su propio contenedor. La pertenencia ya la verificó el backend al listar; el
  // acceso del otro lado lo delimita el pool de la cátedra en Proxmox.
  const urlConsolaProxmox = (s) =>
    `${proxmoxBase}/?console=lxc&xtermjs=1&vmid=${s.proxmox_vmid}` +
    `&vmname=${encodeURIComponent(s.hostname || '')}&node=${encodeURIComponent(s.proxmox_node || '')}&cmd=`;

  const handleDesplegar = async (pedidoId) => {
    if (!confirm(`¿Desplegar pedido #${pedidoId} en Proxmox?`)) return;
    marcarAccion(`deploy-${pedidoId}`);
    try {
      await desplegarPedido(pedidoId);
      await fetchData();
      alert(`Pedido #${pedidoId} desplegado exitosamente`);
    } catch (err) {
      alert(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      marcarAccion(null);
    }
  };

  const handleReactivar = async (id) => {
    marcarAccion(`reactivar-${id}`);
    try {
      await reactivarServicio(id);
      await fetchData();
    } catch (err) {
      const d = err.response?.data?.detail;
      alert(d?.codigo === 'sin_capacidad' ? d.mensaje : (typeof d === 'string' ? d : err.message));
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleExento = async (s) => {
    const activando = !s.exento_pausado;
    if (activando && !confirm(
      'Marcar "siempre encendido" excluye este servicio del apagado automático por falta de uso.\n\n' +
      'Usalo cuando el servicio deba seguir arriba aunque no registre actividad.'
    )) return;
    marcarAccion(`exento-${s.id}`);
    try {
      await actualizarServicio(s.id, { exento_pausado: activando });
      await fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || err.message);
    } finally {
      marcarAccion(null);
    }
  };

  const handleRenovar = async (s) => {
    if (!confirm(
      `Solicitar renovación de ${s.hostname || `servicio #${s.id}`}.\n\n` +
      'Crea un pedido que un administrador tiene que aprobar. El servicio sigue funcionando mientras tanto.'
    )) return;
    marcarAccion(`renovar-${s.id}`);
    try {
      await renovarServicio(s.id);
      alert('Pedido de renovación creado.');
      await fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || err.message);
    } finally {
      marcarAccion(null);
    }
  };

  const accionSimple = (verbo, fn, confirmMsg) => async (id) => {
    if (confirmMsg && !confirm(confirmMsg)) return;
    marcarAccion(`${verbo}-${id}`);
    try {
      await fn(id);
      await fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || err.message);
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleStart = accionSimple('start', iniciarServicio);
  const handleStop = accionSimple('stop', detenerServicio, '¿Detener el servicio?');
  const handleRestart = accionSimple('restart', reiniciarServicio, '¿Reiniciar el servicio?');

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
      alert(err.response?.data?.detail || err.message);
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
      alert(err.response?.data?.detail || err.message);
    }
  };

  const fmt = (iso) => iso
    ? new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '—';

  const corriendo = servicios.filter((s) => s.estado === 'running').length;
  const detenidos = servicios.filter((s) => s.estado === 'stopped').length;

  return (
    <div className="fade-in">
      <PageHead title="Servicios" subtitle="Contenedores y máquinas virtuales desplegados en Proxmox VE.">
        <div className="col" style={{ alignItems: 'flex-end', gap: 6 }}>
          <button className="btn btn-secondary" onClick={fetchData}>
            <RefreshCw size={15} /> Actualizar
          </button>
          <span className="card-meta">
            {actualizadoAt ? `Estado real al ${actualizadoAt.toLocaleTimeString('es-AR')}` : 'Consultando Proxmox…'}
          </span>
        </div>
      </PageHead>

      <div className="grid cols-3 mb-6">
        <div className="stat stat--ok">
          <div className="stat__kicker">Corriendo</div>
          <div className="stat__value">{corriendo}</div>
        </div>
        <div className="stat stat--warn">
          <div className="stat__kicker">Detenidos</div>
          <div className="stat__value">{detenidos}</div>
        </div>
        <div className="stat stat--accent">
          <div className="stat__kicker">Total desplegados</div>
          <div className="stat__value">{servicios.length}</div>
        </div>
      </div>

      {isAdmin && pedidosAprobados.length > 0 && (
        <div className="card mb-6" style={{ borderColor: 'var(--accent-tint-bd)' }}>
          <div className="card-header">
            <div className="card-title">Pedidos listos para desplegar</div>
            <StatusPill kind="accent">{pedidosAprobados.length} pendiente{pedidosAprobados.length > 1 ? 's' : ''}</StatusPill>
          </div>
          <div className="table-container">
            <table>
              <thead><tr><th>Pedido</th><th>Cátedra</th><th>Template</th><th className="right">Acción</th></tr></thead>
              <tbody>
                {pedidosAprobados.map((p) => (
                  <tr key={p.id}>
                    <td className="cell-strong tabnum" style={{ color: 'var(--color-accent-700)' }}>#{p.id}</td>
                    <td>{catedraNombre(p.catedra_id)}</td>
                    <td style={{ color: 'var(--text-soft)' }}>Template #{p.template_id}</td>
                    <td className="right">
                      <button className="btn-send" style={{ padding: '7px 16px', fontSize: 13 }}
                        onClick={() => handleDesplegar(p.id)} disabled={accionando === `deploy-${p.id}`}>
                        <Send size={15} />
                        <span>{accionando === `deploy-${p.id}` ? 'Desplegando…' : 'Desplegar'}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">Contenedores desplegados ({servicios.length})</div>
        {servicios.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>VMID</th><th>Hostname</th><th>Nodo</th><th>Recursos</th>
                  <th>Estado</th><th>Desplegado</th><th className="right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {servicios.map((s) => {
                  const cfg = CFG[s.estado] || { label: s.estado, kind: 'off' };
                  const busy = (k) => accionando === `${k}-${s.id}`;
                  return (
                    <tr key={s.id}>
                      <td className="cell-strong tabnum" style={{ color: 'var(--color-accent-700)' }}>{s.proxmox_vmid || '—'}</td>
                      <td className="cell-strong nowrap">{s.hostname || '—'}</td>
                      <td className="nowrap" style={{ color: 'var(--text-soft)' }}>{s.proxmox_node || '—'}</td>
                      <td className="tabnum nowrap" style={{ color: 'var(--text-soft)' }}>
                        {s.vcpus_asignados} vCPU · {s.ram_asignada_mb} MB · {s.disk_asignado_gb} GB
                      </td>
                      <td>
                        <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                          <StatusPill kind={cfg.kind}>{cfg.label}</StatusPill>
                          {s.existe_en_proxmox === false ? (
                            <span className="card-meta" style={{ color: 'var(--st-bad)' }}>ya no existe en Proxmox</span>
                          ) : s.estado_sincronizado === false && (
                            <span className="card-meta">sin confirmar</span>
                          )}
                          {s.pausado_auto_at && (
                            <span className="card-meta">pausado por falta de uso · el disco sigue ocupado</span>
                          )}
                          {!s.pausado_auto_at && s.pausa_programada_at && (
                            <span className="card-meta" style={{ color: 'var(--st-warn)' }}>
                              se pausará el {new Date(s.pausa_programada_at).toLocaleDateString('es-AR')} si sigue sin uso
                            </span>
                          )}
                          {s.exento_pausado && <span className="card-meta">siempre encendido</span>}
                          {s.vence_at && (
                            <span className="card-meta">vence el {new Date(s.vence_at).toLocaleDateString('es-AR')}</span>
                          )}
                        </div>
                      </td>
                      <td className="tabnum nowrap">{fmt(s.deployed_at)}</td>
                      <td>
                        <div className="row gap-1" style={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                          {s.existe_en_proxmox === false ? (
                            isAdmin ? (
                              <button className="pill-btn bad" onClick={() => handleEliminar(s)} disabled={busy('delete')}>
                                <Trash2 size={13} /> Dar de baja
                              </button>
                            ) : (
                              <span className="card-meta">Avisá al administrador</span>
                            )
                          ) : (
                            <>
                              {s.pausado_auto_at ? (
                                <button className="pill-btn ok" onClick={() => handleReactivar(s.id)} disabled={busy('reactivar')}
                                  title="Volver a encenderlo. Los datos están intactos; los procesos que no arrancan solos hay que levantarlos.">
                                  <Play size={13} /> Reactivar
                                </button>
                              ) : s.estado === 'running' ? (
                                <button className="pill-btn warn" onClick={() => handleStop(s.id)} disabled={busy('stop')}>
                                  <Square size={12} /> Detener
                                </button>
                              ) : (
                                <button className="pill-btn ok" onClick={() => handleStart(s.id)} disabled={busy('start')}>
                                  <Play size={13} /> Iniciar
                                </button>
                              )}
                              {s.estado === 'running' && (
                                <button className="btn-icon" title="Reiniciar" onClick={() => handleRestart(s.id)} disabled={busy('restart')}>
                                  <RotateCw size={15} />
                                </button>
                              )}
                              <button className="btn-icon" title="Estado en Proxmox" onClick={() => handleStatus(s.id)}><Activity size={15} /></button>
                              {s.vence_at && (
                                <button className="btn-icon" title="Solicitar renovación" onClick={() => handleRenovar(s)} disabled={busy('renovar')}>
                                  <CalendarClock size={15} />
                                </button>
                              )}
                              <button className="btn-icon" onClick={() => handleExento(s)} disabled={busy('exento')}
                                title={s.exento_pausado ? 'Quitar "siempre encendido"' : 'Marcar "siempre encendido"'}>
                                {s.exento_pausado ? <Pin size={15} /> : <PinOff size={15} />}
                              </button>
                              {proxmoxBase && s.estado === 'running' && s.proxmox_vmid && (
                                <a className="btn-icon" href={urlConsolaProxmox(s)} target="_blank" rel="noopener noreferrer"
                                   title="Abrir la consola del contenedor (requiere sesión en Proxmox)">
                                  <Terminal size={15} />
                                </a>
                              )}
                              {isAdmin && (
                                <button className="btn-icon danger" title="Dar de baja" onClick={() => handleEliminar(s)} disabled={busy('delete')}>
                                  <Trash2 size={15} />
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={<RefreshCw size={22} />}
            hint={isAdmin && !loading ? 'Aprobá un pedido y desplegalo desde esta vista.' : undefined}
          >
            {loading ? 'Cargando…' : 'No hay servicios desplegados aún.'}
          </Empty>
        )}
      </div>

      {statusDetalle && (
        <Dialog wide title={`Estado en Proxmox — VMID ${statusDetalle.vmid}`} onClose={() => setStatusDetalle(null)}>
          <pre style={{
            fontSize: 12, color: 'var(--text-body)', overflowX: 'auto',
            background: 'color-mix(in srgb, var(--color-text) 6%, transparent)',
            padding: 'var(--space-3)', borderRadius: 'var(--radius-md)',
          }}>
            {JSON.stringify(statusDetalle.proxmox_status, null, 2)}
          </pre>
        </Dialog>
      )}
    </div>
  );
}
