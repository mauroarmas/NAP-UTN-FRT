import { useState, useEffect, useRef, useMemo } from 'react';
import {
  RefreshCw, Play, Pause, RotateCw, Trash2, Terminal, Activity,
  Pin, PinOff, CalendarClock, Send, Loader2, Copy, Search, X, ExternalLink, Settings,
} from 'lucide-react';
import {
  getPedidos, listarServicios, desplegarPedido, iniciarServicio, detenerServicio,
  reiniciarServicio, eliminarServicio, getStatusServicio, getCatedras, getCatedrasMias,
  getTemplates, getBaseConsolaProxmox, reactivarServicio, actualizarServicio, renovarServicio,
} from '../services/api';
import { PageHead, StatusPill, Empty, Dialog } from '../components/ui';

const CFG = {
  running: { label: 'Corriendo', kind: 'ok' },
  stopped: { label: 'Detenido', kind: 'off' },
  paused:  { label: 'Pausado', kind: 'warn' },
  error:   { label: 'Error', kind: 'bad' },
};

const INTERVALO_REFRESCO_MS = 10000;

const EN_CURSO = {
  start: 'Iniciando…',
  stop: 'Deteniendo…',
  restart: 'Reiniciando…',
  reactivar: 'Reactivando…',
  delete: 'Dando de baja…',
  exento: 'Guardando…',
  renovar: 'Solicitando…',
  deploy: 'Desplegando…',
};

const Spinner = ({ size = 13 }) => <Loader2 size={size} className="spin" aria-hidden="true" />;

export default function Servicios({ user }) {
  const [servicios, setServicios] = useState([]);
  const [pedidosAprobados, setPedidosAprobados] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accionando, setAccionando] = useState(null);
  const [statusDetalle, setStatusDetalle] = useState(null);
  const [proxmoxBase, setProxmoxBase] = useState(null);
  const [actualizadoAt, setActualizadoAt] = useState(null);

  // Filtros
  const [filtroCatedra, setFiltroCatedra] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('');
  const [busqueda, setBusqueda] = useState('');

  // Menú de acciones por engranaje (ID del servicio con menú abierto)
  const [menuAccionesAbierto, setMenuAccionesAbierto] = useState(null);

  const accionandoRef = useRef(null);
  const isAdmin = user?.rol === 'admin';

  const marcarAccion = (tipo, id) => {
    const v = tipo ? { tipo, id } : null;
    accionandoRef.current = v;
    setAccionando(v);
  };

  const enCurso = (tipo, id) => accionando?.tipo === tipo && accionando?.id === id;

  const fetchData = async () => {
    try {
      const [srvRes, pedRes, catRes, baseRes, tplRes] = await Promise.allSettled([
        listarServicios(),
        isAdmin ? getPedidos('aprobado') : Promise.resolve({ data: [] }),
        isAdmin ? getCatedras() : getCatedrasMias(),
        getBaseConsolaProxmox(),
        getTemplates(),
      ]);
      if (srvRes.status === 'fulfilled') { setServicios(srvRes.value.data); setActualizadoAt(new Date()); }
      if (pedRes.status === 'fulfilled') setPedidosAprobados(pedRes.value.data);
      if (catRes.status === 'fulfilled') setCatedras(catRes.value.data);
      if (baseRes.status === 'fulfilled') setProxmoxBase(baseRes.value.data.base_url || null);
      if (tplRes.status === 'fulfilled') setTemplates(tplRes.value.data);
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

  // Cerrar menú de engranaje al hacer clic fuera
  useEffect(() => {
    const onDocClick = (e) => {
      if (!e.target.closest('.acciones-menu')) {
        setMenuAccionesAbierto(null);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const catedra = (id) => catedras.find((c) => c.id === id);
  const catedraNombre = (id) => catedra(id)?.nombre || `Cátedra #${id}`;
  const templateDe = (s) => templates.find((t) => t.id === s.template_id);

  const tipoServicioBadge = (s) => {
    const tpl = templateDe(s);
    if (tpl?.modelo_servicio === 'saas') return { label: 'SaaS', kind: 'accent' };
    if (tpl?.modelo_servicio === 'paas') return { label: 'PaaS', kind: 'accent' };
    return { label: 'IaaS', kind: 'neutral' };
  };

  const formatRam = (mb) => {
    if (!mb) return '—';
    return mb >= 1024 ? `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)} GB` : `${mb} MB`;
  };

  const fmtFecha = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const urlConsolaProxmox = (s) =>
    `${proxmoxBase}/?console=lxc&xtermjs=1&vmid=${s.proxmox_vmid}` +
    `&vmname=${encodeURIComponent(s.hostname || '')}&node=${encodeURIComponent(s.proxmox_node || '')}&cmd=`;

  const handleDesplegar = async (pedidoId) => {
    if (!confirm(`¿Desplegar pedido #${pedidoId} en Proxmox?`)) return;
    marcarAccion('deploy', pedidoId);
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
    marcarAccion('reactivar', id);
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
      'Marcar "siempre activo" excluye este servicio del apagado automático por falta de uso.\n\n' +
      'Usalo cuando el servicio deba seguir arriba aunque no registre actividad.'
    )) return;
    marcarAccion('exento', s.id);
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
    marcarAccion('renovar', s.id);
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
    marcarAccion(verbo, id);
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
    marcarAccion('delete', s.id);
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

  // Filtrado de servicios
  const serviciosFiltrados = useMemo(() => {
    return servicios.filter((s) => {
      const tpl = templateDe(s);
      if (filtroCatedra && String(s.catedra_id) !== String(filtroCatedra)) {
        return false;
      }
      if (filtroTipo) {
        if (filtroTipo === 'saas') {
          if (tpl?.modelo_servicio !== 'saas') return false;
        } else if (filtroTipo === 'paas') {
          if (tpl?.modelo_servicio !== 'paas') return false;
        } else if (filtroTipo === 'iaas') {
          // Contenedores y VMs entran dentro de IaaS según requerimiento
          const esIaas = tpl?.modelo_servicio === 'iaas' || !tpl?.modelo_servicio || s.tipo === 'lxc' || s.tipo === 'qemu';
          if (!esIaas) return false;
        }
      }
      if (busqueda.trim()) {
        const q = busqueda.trim().toLowerCase();
        const nombreTpl = tpl?.nombre?.toLowerCase() || '';
        const hostname = s.hostname?.toLowerCase() || '';
        const ip = s.ip_address?.toLowerCase() || '';
        const cat = catedraNombre(s.catedra_id).toLowerCase();
        if (!nombreTpl.includes(q) && !hostname.includes(q) && !ip.includes(q) && !cat.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [servicios, filtroCatedra, filtroTipo, busqueda, templates, catedras]);

  const corriendo = servicios.filter((s) => s.estado === 'running').length;
  const detenidos = servicios.filter((s) => s.estado === 'stopped').length;
  const hayFiltrosActivos = Boolean(filtroCatedra || filtroTipo || busqueda);

  return (
    <div className="fade-in">
      <PageHead title="Servicios" subtitle="Servicios desplegados y en funcionamiento.">
        <div className="col" style={{ alignItems: 'flex-end', gap: 6 }}>
          <button className="btn btn-secondary" onClick={fetchData}>
            <RefreshCw size={15} /> Actualizar
          </button>
          <span className="card-meta">
            {actualizadoAt ? `Actualizado al ${actualizadoAt.toLocaleTimeString('es-AR')}` : 'Consultando servicios…'}
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
                        onClick={() => handleDesplegar(p.id)} disabled={!!accionando}
                        aria-busy={enCurso('deploy', p.id)}>
                        {enCurso('deploy', p.id) ? <Spinner size={15} /> : <Send size={15} />}
                        <span>{enCurso('deploy', p.id) ? EN_CURSO.deploy : 'Desplegar'}</span>
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
        {/* Encabezado con título y filtros horizontales */}
        <div
          className="card-header"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            flexWrap: 'wrap',
            marginBottom: 'var(--space-3)',
          }}
        >
          <div className="card-title" style={{ margin: 0, whiteSpace: 'nowrap' }}>
            Servicios desplegados
            <span className="section-count" style={{ marginLeft: 8 }}>
              {serviciosFiltrados.length === servicios.length
                ? `(${servicios.length})`
                : `(${serviciosFiltrados.length} de ${servicios.length})`}
            </span>
          </div>

          {/* Barra horizontal de filtros */}
          <div
            style={{
              display: 'inline-flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
            }}
          >
            <div className="input-search" style={{ width: 190, flex: 'none', position: 'relative' }}>
              <Search size={14} />
              <input
                className="input"
                style={{ width: '100%', height: 34, fontSize: 13, paddingLeft: 30 }}
                placeholder="Buscar servicio..."
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />
              {busqueda && (
                <button
                  className="btn-icon"
                  style={{ width: 18, height: 18, position: 'absolute', right: 6, top: 8 }}
                  onClick={() => setBusqueda('')}
                  title="Borrar búsqueda"
                >
                  <X size={11} />
                </button>
              )}
            </div>

            <select
              className="input"
              style={{ width: 'auto', minWidth: 160, height: 34, fontSize: 13, flex: 'none' }}
              value={filtroCatedra}
              onChange={(e) => setFiltroCatedra(e.target.value)}
              aria-label="Filtrar por cátedra"
            >
              <option value="">Todas las cátedras</option>
              {catedras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>

            <select
              className="input"
              style={{ width: 'auto', minWidth: 155, height: 34, fontSize: 13, flex: 'none' }}
              value={filtroTipo}
              onChange={(e) => setFiltroTipo(e.target.value)}
              aria-label="Filtrar por tipo de servicio"
            >
              <option value="">Todos los tipos</option>
              <option value="iaas">IaaS (Infraestructura)</option>
              <option value="paas">PaaS (Plataforma)</option>
              <option value="saas">Software (SaaS)</option>
            </select>

            {hayFiltrosActivos && (
              <button
                className="btn btn-secondary btn-sm"
                style={{ height: 34, padding: '0 12px', fontSize: 12, flex: 'none', whiteSpace: 'nowrap' }}
                onClick={() => {
                  setFiltroCatedra('');
                  setFiltroTipo('');
                  setBusqueda('');
                }}
              >
                Limpiar
              </button>
            )}
          </div>
        </div>

        {serviciosFiltrados.length > 0 ? (
          <div
            className="table-container"
            style={{
              minHeight: serviciosFiltrados.length <= 3 ? 240 : undefined,
              paddingBottom: menuAccionesAbierto ? 90 : 0,
            }}
          >
            <table>
              <thead>
                <tr>
                  {isAdmin && <th>VMID</th>}
                  <th>Servicio</th>
                  <th>Cátedra</th>
                  {isAdmin && <th>Nodo</th>}
                  <th>Recursos</th>
                  <th>Estado</th>
                  <th>Fecha</th>
                  <th className="right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {serviciosFiltrados.map((s, idx) => {
                  const cfg = CFG[s.estado] || { label: s.estado, kind: 'off' };
                  const tpl = templateDe(s);
                  const badge = tipoServicioBadge(s);
                  const busy = (k) => enCurso(k, s.id);
                  const ocupada = accionando !== null
                    && accionando.tipo !== 'deploy'
                    && accionando.id === s.id;
                  const abreHaciaArriba = serviciosFiltrados.length > 1 && idx >= serviciosFiltrados.length - 1;

                  return (
                    <tr key={s.id}>
                      {isAdmin && (
                        <td className="cell-strong tabnum" style={{ color: 'var(--color-accent-700)' }}>
                          {s.proxmox_vmid || '—'}
                        </td>
                      )}
                      <td className="nowrap">
                        <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                          <div className="row gap-2" style={{ alignItems: 'center' }}>
                            <span className="cell-strong">
                              {tpl?.nombre || s.hostname || `Servicio #${s.id}`}
                            </span>
                            <span className={`tag ${badge.kind}`} style={{ fontSize: 10, padding: '1px 6px' }}>
                              {badge.label}
                            </span>
                          </div>

                          {s.hostname && s.hostname !== tpl?.nombre && (
                            <span className="card-meta tabnum">{s.hostname}</span>
                          )}

                          {s.ip_address && (
                            <span className="card-meta tabnum" style={{ color: 'var(--text-soft)' }}>
                              IP: {s.ip_address}
                            </span>
                          )}

                          {s.url_acceso && (
                            <div className="row gap-1" style={{ alignItems: 'center', marginTop: 2 }}>
                              <a
                                href={s.url_acceso}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  fontSize: 12,
                                  color: 'var(--color-accent-700)',
                                  textDecoration: 'underline',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 4,
                                }}
                              >
                                {s.url_acceso}
                                <ExternalLink size={11} />
                              </a>
                              <button
                                className="btn-icon"
                                style={{ padding: 2, width: 20, height: 20 }}
                                title="Copiar URL"
                                onClick={() => {
                                  navigator.clipboard.writeText(s.url_acceso);
                                  alert('URL copiada al portapapeles');
                                }}
                              >
                                <Copy size={11} />
                              </button>
                            </div>
                          )}

                          {s.credenciales_acceso && (
                            <div className="row gap-1" style={{ alignItems: 'center' }}>
                              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                                {typeof s.credenciales_acceso === 'object'
                                  ? JSON.stringify(s.credenciales_acceso)
                                  : s.credenciales_acceso}
                              </span>
                              <button
                                className="btn-icon"
                                style={{ padding: 2, width: 20, height: 20 }}
                                title="Copiar credenciales"
                                onClick={() => {
                                  const txt = typeof s.credenciales_acceso === 'object'
                                    ? JSON.stringify(s.credenciales_acceso, null, 2)
                                    : s.credenciales_acceso;
                                  navigator.clipboard.writeText(txt);
                                  alert('Credenciales copiadas al portapapeles');
                                }}
                              >
                                <Copy size={11} />
                              </button>
                            </div>
                          )}
                        </div>
                      </td>

                      <td>
                        <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                          <span>{catedraNombre(s.catedra_id)}</span>
                          {isAdmin && catedra(s.catedra_id)?.titular?.nombre && (
                            <span className="card-meta">{catedra(s.catedra_id).titular.nombre}</span>
                          )}
                        </div>
                      </td>

                      {isAdmin && (
                        <td className="nowrap" style={{ color: 'var(--text-soft)' }}>
                          {s.proxmox_node || '—'}
                        </td>
                      )}

                      <td className="tabnum nowrap" style={{ color: 'var(--text-soft)' }}>
                        {s.vcpus_asignados} vCPU · {formatRam(s.ram_asignada_mb)} · {s.disk_asignado_gb} GB
                      </td>

                      <td>
                        <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                          <StatusPill kind={cfg.kind}>{cfg.label}</StatusPill>
                          {ocupada && (
                            <span className="card-meta"
                                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--st-warn)' }}>
                              <Spinner size={11} /> {EN_CURSO[accionando.tipo]}
                            </span>
                          )}
                          {s.existe_en_proxmox === false ? (
                            <span className="card-meta" style={{ color: 'var(--st-bad)' }}>
                              {isAdmin ? 'ya no existe en Proxmox' : 'No disponible · Avisá a soporte'}
                            </span>
                          ) : s.estado_sincronizado === false && (
                            <span className="card-meta">sin confirmar</span>
                          )}
                          {s.pausado_auto_at && (
                            <span className="card-meta">pausado por inactividad · datos seguros</span>
                          )}
                          {!s.pausado_auto_at && s.pausa_programada_at && (
                            <span className="card-meta" style={{ color: 'var(--st-warn)' }}>
                              se pausará el {new Date(s.pausa_programada_at).toLocaleDateString('es-AR')} por inactividad
                            </span>
                          )}
                          {s.exento_pausado && <span className="card-meta">siempre activo</span>}
                          {s.vence_at && (() => {
                            const diffDias = Math.ceil((new Date(s.vence_at) - new Date()) / (1000 * 60 * 60 * 24));
                            return (
                              <span className="card-meta" style={{ color: diffDias <= 7 ? 'var(--st-warn)' : 'var(--text-soft)' }}>
                                {diffDias > 0 ? `Vence en ${diffDias} días (${new Date(s.vence_at).toLocaleDateString('es-AR')})` : `Vencido (${new Date(s.vence_at).toLocaleDateString('es-AR')})`}
                              </span>
                            );
                          })()}
                        </div>
                      </td>

                      <td className="tabnum nowrap">{fmtFecha(s.deployed_at)}</td>

                      <td>
                        <div className="row gap-1" style={{ justifyContent: 'flex-end', position: 'relative' }}>
                          {s.existe_en_proxmox === false ? (
                            isAdmin ? (
                              <button className="btn-icon danger" onClick={() => handleEliminar(s)}
                                disabled={ocupada} aria-busy={busy('delete')} title="Dar de baja">
                                {busy('delete') ? <Spinner size={14} /> : <Trash2 size={16} />}
                              </button>
                            ) : (
                              <span className="card-meta">Avisá a soporte</span>
                            )
                          ) : (
                            <>
                              {/* Icono 1: Reanudar / Pausar (Iniciar / Detener) */}
                              {s.pausado_auto_at ? (
                                <button
                                  className="btn-icon ok"
                                  onClick={() => handleReactivar(s.id)}
                                  disabled={ocupada}
                                  aria-busy={busy('reactivar')}
                                  title="Reanudar / Reactivar servicio"
                                >
                                  {busy('reactivar') ? <Spinner size={14} /> : <Play size={16} />}
                                </button>
                              ) : s.estado === 'running' ? (
                                <button
                                  className="btn-icon warn"
                                  onClick={() => handleStop(s.id)}
                                  disabled={ocupada}
                                  aria-busy={busy('stop')}
                                  title="Pausar / Detener servicio"
                                >
                                  {busy('stop') ? <Spinner size={14} /> : <Pause size={16} />}
                                </button>
                              ) : (
                                <button
                                  className="btn-icon ok"
                                  onClick={() => handleStart(s.id)}
                                  disabled={ocupada}
                                  aria-busy={busy('start')}
                                  title="Iniciar servicio"
                                >
                                  {busy('start') ? <Spinner size={14} /> : <Play size={16} />}
                                </button>
                              )}

                              {/* Icono 2: Engranaje que despliega las demás acciones */}
                              <div className="acciones-menu" style={{ position: 'relative' }}>
                                <button
                                  className={`btn-icon ${menuAccionesAbierto === s.id ? 'active' : ''}`}
                                  onClick={() => setMenuAccionesAbierto((cur) => (cur === s.id ? null : s.id))}
                                  title="Opciones del servicio"
                                  aria-haspopup="true"
                                  aria-expanded={menuAccionesAbierto === s.id}
                                >
                                  <Settings size={16} />
                                </button>

                                {menuAccionesAbierto === s.id && (
                                  <div
                                    className="menu-panel to-right"
                                    style={{
                                      minWidth: 200,
                                      zIndex: 60,
                                      right: 0,
                                      top: abreHaciaArriba ? 'auto' : 'calc(100% + 4px)',
                                      bottom: abreHaciaArriba ? 'calc(100% + 4px)' : 'auto',
                                      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                                    }}
                                  >
                                    {/* Reiniciar */}
                                    <button
                                      className="menu-item"
                                      onClick={() => {
                                        setMenuAccionesAbierto(null);
                                        handleRestart(s.id);
                                      }}
                                      disabled={ocupada || s.estado !== 'running'}
                                      title={s.estado !== 'running' ? 'El servicio debe estar corriendo para reiniciarlo' : undefined}
                                    >
                                      <RotateCw size={14} />
                                      <span>Reiniciar</span>
                                    </button>

                                    {/* Solicitar renovación */}
                                    <button
                                      className="menu-item"
                                      onClick={() => {
                                        setMenuAccionesAbierto(null);
                                        handleRenovar(s);
                                      }}
                                      disabled={ocupada}
                                    >
                                      <CalendarClock size={14} />
                                      <span>Solicitar renovación</span>
                                    </button>

                                    {/* Marcar o quitar siempre activo */}
                                    <button
                                      className="menu-item"
                                      onClick={() => {
                                        setMenuAccionesAbierto(null);
                                        handleExento(s);
                                      }}
                                      disabled={ocupada}
                                    >
                                      {s.exento_pausado ? <PinOff size={14} /> : <Pin size={14} />}
                                      <span>{s.exento_pausado ? 'Quitar siempre activo' : 'Marcar siempre activo'}</span>
                                    </button>

                                    {/* Estado en Proxmox */}
                                    <button
                                      className="menu-item"
                                      onClick={() => {
                                        setMenuAccionesAbierto(null);
                                        handleStatus(s.id);
                                      }}
                                    >
                                      <Activity size={14} />
                                      <span>Estado en Proxmox</span>
                                    </button>

                                    {/* Consola Terminal (si está disponible) */}
                                    {proxmoxBase && s.estado === 'running' && s.proxmox_vmid && (
                                      <a
                                        className="menu-item"
                                        href={urlConsolaProxmox(s)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={() => setMenuAccionesAbierto(null)}
                                      >
                                        <Terminal size={14} />
                                        <span>Abrir consola</span>
                                      </a>
                                    )}

                                    {/* Dar de baja (si es admin o huérfano) */}
                                    {(isAdmin || s.existe_en_proxmox === false) && (
                                      <>
                                        <div style={{ height: 1, background: 'var(--color-divider)', margin: '4px 0' }} />
                                        <button
                                          className="menu-item danger"
                                          onClick={() => {
                                            setMenuAccionesAbierto(null);
                                            handleEliminar(s);
                                          }}
                                          disabled={ocupada}
                                        >
                                          <Trash2 size={14} />
                                          <span>Dar de baja</span>
                                        </button>
                                      </>
                                    )}
                                  </div>
                                )}
                              </div>
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
            hint={hayFiltrosActivos ? 'Probá cambiando o limpiando los filtros seleccionados.' : (isAdmin && !loading ? 'Aprobá un pedido y desplegalo desde esta vista.' : undefined)}
          >
            {loading ? 'Cargando…' : (hayFiltrosActivos ? 'No se encontraron servicios que coincidan con los filtros.' : 'No hay servicios desplegados aún.')}
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
