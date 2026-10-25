import useRemoteData from '../hooks/useRemoteData';
import EstadoConsulta from '../components/EstadoConsulta';
import AlertasServicio from '../components/AlertasServicio';
import useOperacion, { operacionAbierta, textoOperacion } from '../hooks/useOperacion.js';
import { mensajeError } from '../utils/errors.js';
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  RefreshCw, Play, Pause, RotateCw, Trash2, Activity,
  Pin, PinOff, CalendarClock, Send, Loader2, Search, X, Settings, CircleAlert,
} from 'lucide-react';
import {
  getPedidos, listarServicios, desplegarPedido, iniciarServicio, detenerServicio,
  reiniciarServicio, eliminarServicio, getStatusServicio, getCatedras, getCatedrasMias,
  getTemplates, reactivarServicio, actualizarServicio, listarOperaciones,
} from '../services/api';
import { PageHead, StatusPill, Empty, Dialog } from '../components/ui';
import RenovarServicioModal from '../components/RenovarServicioModal';
import AccesoServicio from '../components/AccesoServicio';
import RegularizarServicioModal from '../components/RegularizarServicioModal';

const CFG = {
  running: { label: 'Corriendo', kind: 'ok' },
  stopped: { label: 'Detenido', kind: 'off' },
  paused:  { label: 'Pausado', kind: 'warn' },
  error:   { label: 'Error', kind: 'bad' },
};

const INTERVALO_REFRESCO_MS = 10000;
const EMPTY = [];

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

function CoberturaServicio({ servicio, isAdmin, onModificar, disabled }) {
  const labels = { con_cobertura: 'Dentro del período autorizado', receso: 'En receso · datos conservados',
    esperando_inicio: 'Esperando fecha inicial', vencido: 'Período finalizado · datos conservados', sin_regularizar: 'Fechas de uso pendientes de revisión' };
  return <div className="col gap-1">
    <span className="card-meta">{labels[servicio.estado_cobertura] || 'Cobertura sin confirmar'}</span>
    {servicio.fin_efectivo_at && <span className="card-meta">Cobertura actual hasta {new Date(servicio.fin_efectivo_at).toLocaleString('es-AR')} (fin exclusivo).</span>}
    {servicio.proximo_inicio && <span className="card-meta">Próximo inicio: {new Date(servicio.proximo_inicio).toLocaleString('es-AR')}. La reactivación requiere capacidad y una acción explícita.</span>}
    {servicio.periodos_autorizados?.length > 0 && <details>
      <summary>Períodos autorizados</summary>
      <ul>{servicio.periodos_autorizados.map((periodo) => <li key={periodo.id}>
        {periodo.desde} al {periodo.hasta}, inclusive ({periodo.zona_horaria}).
        {isAdmin && <button className="btn btn-ghost btn-sm" disabled={disabled} onClick={() => onModificar(periodo)}>Solicitar modificación</button>}
      </li>)}</ul>
    </details>}
  </div>;
}

export default function Servicios({ user }) {
  const [accionando, setAccionando] = useState(null);
  const [statusDetalle, setStatusDetalle] = useState(null);
  const [operationIds, setOperationIds] = useState([]);
  const [renovacion, setRenovacion] = useState(null);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [access, setAccess] = useState(null);
  const [regularizacion, setRegularizacion] = useState(null);
  const [revisionDetalle, setRevisionDetalle] = useState(null);
  const [resultadoPreferencia, setResultadoPreferencia] = useState(null);
  const statusRequest = useRef(0);
  const intentKeys = useRef({});
  const claveIntencion = (tipo, id) => {
    const key = `${tipo}:${id}`;
    if (!intentKeys.current[key]) intentKeys.current[key] = crypto.randomUUID();
    return intentKeys.current[key];
  };
  const registrarOrden = (response, tipo, id) => {
    const operationId = response.data?.operation_id;
    if (operationId) setOperationIds((current) => [...new Set([...current, operationId])]);
    delete intentKeys.current[`${tipo}:${id}`];
  };
  const registrarConflicto = (err) => {
    const id = err.response?.data?.detail?.operation_id;
    if (id) setOperationIds((current) => [...new Set([...current, id])]);
  };

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
    if (tipo) setActionError('');
    setAccionando(v);
  };

  const enCurso = (tipo, id) => accionando?.tipo === tipo && accionando?.id === id;

  const scope = `${user?.id || ''}:${user?.rol || ''}`;
  const common = { refreshMs: INTERVALO_REFRESCO_MS, canRefresh: () => !accionandoRef.current };
  const srvRemote = useRemoteData((options) => listarServicios({ ...options,
    params: filtroTipo ? { modelo_servicio: filtroTipo } : {} }), {
    ...common, key: `servicios:${scope}:${filtroTipo}`, errorMessage: 'No se pudieron consultar los servicios.' });
  const pedRemote = useRemoteData((options) => getPedidos('aprobado', options), {
    ...common, key: `pedidos:${scope}`, enabled: isAdmin, errorMessage: 'No se pudieron consultar los pedidos aprobados.' });
  const catRemote = useRemoteData((options) => isAdmin ? getCatedras(options) : getCatedrasMias(options), {
    ...common, key: `catedras:${scope}`, errorMessage: 'No se pudieron consultar las cátedras.' });
  const tplRemote = useRemoteData((options) => getTemplates(false, null, options), {
    ...common, key: `perfiles:${scope}`, errorMessage: 'No se pudo consultar el catálogo de perfiles.' });
  const opRemote = useRemoteData((options) => listarOperaciones({ abiertas: true }, options), {
    ...common, key: `operaciones:${scope}`, errorMessage: 'No se pudieron consultar las operaciones.' });
  const servicios = srvRemote.data || EMPTY;
  const pedidosAprobados = pedRemote.data || EMPTY;
  const catedras = catRemote.data || EMPTY;
  const templates = tplRemote.data || EMPTY;
  const loading = srvRemote.loading && srvRemote.data === null;
  const actualizadoAt = srvRemote.updatedAt;
  const { reload: reloadServices } = srvRemote;
  const { reload: reloadOrders } = pedRemote;
  const { reload: reloadCategories } = catRemote;
  const { reload: reloadProfiles } = tplRemote;
  const { reload: reloadOperations } = opRemote;
  const fetchData = useCallback(() => Promise.all([reloadServices(), reloadOrders(), reloadCategories(),
    reloadProfiles(), reloadOperations()]), [reloadServices, reloadOrders, reloadCategories, reloadProfiles, reloadOperations]);
  useEffect(() => {
    const ids = [...(srvRemote.data || EMPTY).map((row) => row.operation_id), ...(opRemote.data || EMPTY).map((row) => row.operation_id)].filter(Boolean);
    setOperationIds((current) => [...new Set([...current, ...ids])]);
  }, [srvRemote.data, opRemote.data]);
  const operaciones = useOperacion(operationIds, fetchData);

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
    if (!s.modelo_servicio) return { label: 'Tipo pendiente de revisión', kind: 'warn' };
    if (s.modelo_servicio === 'saas') return { label: 'SaaS', kind: 'accent' };
    if (s.modelo_servicio === 'paas') return { label: 'PaaS', kind: 'accent' };
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

  const handleDesplegar = async (pedidoId) => {
    if (accionandoRef.current || !confirm(`¿Desplegar pedido #${pedidoId} en Proxmox?`)) return;
    marcarAccion('deploy', pedidoId);
    try {
      registrarOrden(await desplegarPedido(pedidoId, {}, claveIntencion('deploy', pedidoId)), 'deploy', pedidoId);
      await fetchData();
    } catch (err) {
      registrarConflicto(err);
      setActionError(`Error: ${mensajeError(err, 'No se confirmó la acción. Volvé a consultar el servicio.')}`);
    } finally {
      marcarAccion(null);
    }
  };

  const handleReactivar = async (id) => {
    if (accionandoRef.current) return;
    marcarAccion('reactivar', id);
    try {
      registrarOrden(await reactivarServicio(id, claveIntencion('reactivar', id)), 'reactivar', id);
      await fetchData();
    } catch (err) {
      registrarConflicto(err);
      const d = err.response?.data?.detail;
      setActionError(d?.codigo === 'sin_capacidad' ? d.mensaje : (typeof d === 'string' ? d : 'No se confirmó el inicio del servicio.'));
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleExento = async (s) => {
    if (accionandoRef.current) return;
    const activando = !s.exento_pausado;
    if (activando && !confirm(
      'Marcar "siempre activo" excluye este servicio del apagado automático por falta de uso.\n\n' +
      'Usalo cuando el servicio deba seguir arriba aunque no registre actividad.'
    )) return;
    setResultadoPreferencia(null);
    marcarAccion('exento', s.id);
    try {
      await actualizarServicio(s.id, { exento_pausado: activando });
      setResultadoPreferencia({ id: s.id, mensaje: activando
        ? 'Siempre activo habilitado: no se pausará por falta de uso. No enciende el servicio ni cambia sus fechas autorizadas.'
        : 'Siempre activo deshabilitado: vuelve a aplicarse la pausa por falta de uso.' });
      await fetchData();
    } catch (err) {
      registrarConflicto(err);
      setResultadoPreferencia({ id: s.id, error: true,
        mensaje: mensajeError(err, 'No se pudo confirmar el cambio. Volvé a consultar el servicio antes de repetirlo.') });
    } finally {
      marcarAccion(null);
    }
  };

  const handleRenovar = (servicio, periodo = null) => {
    setNotice('');
    setRenovacion({ servicio, periodo });
  };

  const accionSimple = (verbo, fn, confirmMsg) => async (id) => {
    if (accionandoRef.current || (confirmMsg && !confirm(confirmMsg))) return;
    marcarAccion(verbo, id);
    try {
      registrarOrden(await fn(id, claveIntencion(verbo, id)), verbo, id);
      await fetchData();
    } catch (err) {
      registrarConflicto(err);
      setActionError(mensajeError(err, 'No se confirmó la acción. Volvé a consultar el servicio.'));
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
    if (accionandoRef.current || !confirm(aviso)) return;
    marcarAccion('delete', s.id);
    try {
      registrarOrden(await eliminarServicio(s.id, claveIntencion('delete', s.id)), 'delete', s.id);
      await fetchData();
    } catch (err) {
      registrarConflicto(err);
      setActionError(mensajeError(err, 'No se confirmó la acción. Volvé a consultar el servicio.'));
      await fetchData();
    } finally {
      marcarAccion(null);
    }
  };

  const handleStatus = async (id) => {
    const request = ++statusRequest.current;
    setStatusDetalle({ servicioId: id, loading: true });
    try {
      const { data } = await getStatusServicio(id);
      if (statusRequest.current === request) setStatusDetalle({ servicioId: id, data });
    } catch {
      if (statusRequest.current === request) setStatusDetalle({ servicioId: id,
        error: 'No se pudo consultar el estado del servicio. La conexión con la infraestructura puede no estar disponible. Intentá nuevamente o consultá al administrador.' });
    }
  };

  const cerrarEstado = () => {
    statusRequest.current += 1;
    setStatusDetalle(null);
  };

  // Filtrado de servicios
  const serviciosFiltrados = useMemo(() => {
    return servicios.filter((s) => {
      const tpl = templateDe(s);
      if (filtroCatedra && String(s.catedra_id) !== String(filtroCatedra)) {
        return false;
      }
      if (filtroTipo && s.modelo_servicio !== filtroTipo) return false;
      if (busqueda.trim()) {
        const q = busqueda.trim().toLowerCase();
        const nombreTpl = (s.nombre_snapshot || tpl?.nombre || '').toLowerCase();
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
          <button className="btn btn-secondary" onClick={fetchData} disabled={srvRemote.loading}>
            <RefreshCw size={15} /> Actualizar
          </button>
          <span className="card-meta">
            {actualizadoAt ? `Última consulta confirmada: ${actualizadoAt.toLocaleString('es-AR')}` : 'Consultando servicios…'}
          </span>
        </div>
      </PageHead>

      <EstadoConsulta remote={srvRemote} nombre="servicios" mostrarCarga />
      <EstadoConsulta remote={pedRemote} nombre="pedidos aprobados" />
      <EstadoConsulta remote={catRemote} nombre="cátedras" />
      <EstadoConsulta remote={tplRemote} nombre="catálogo" />
      <EstadoConsulta remote={opRemote} nombre="operaciones" />
      <AlertasServicio user={user} />
      {actionError && <p role="alert" className="callout bad">{actionError}</p>}
      {notice && <p role="status" className="callout ok">{notice}</p>}
      {isAdmin && regularizacion && <RegularizarServicioModal key={regularizacion.id} servicio={regularizacion} user={user}
        onClose={() => setRegularizacion(null)} onConfirmed={(data) => {
          if (data.operation_id) setOperationIds((current) => [...new Set([...current, data.operation_id])]);
          setNotice(data.estado === 'registro_duplicado_archivado' ? `Registro duplicado archivado. Principal #${data.principal_id}.`
            : `Regularización registrada. El acceso sigue sin verificar.${data.operation_id ? ' Pausa solicitada; esperando confirmación.' : ''}`);
          fetchData();
        }} />}
      {renovacion && <RenovarServicioModal servicio={renovacion.servicio} periodo={renovacion.periodo} user={user}
        onClose={() => setRenovacion(null)} onCreated={(data) => {
          setNotice(`Solicitud de ${renovacion.periodo ? 'modificación' : 'renovación'} #${data.pedido_id} pendiente de aprobación.`);
          fetchData();
        }} />}
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

      {Object.keys(operaciones).length > 0 && (
        <section aria-label="Operaciones de infraestructura" aria-live="polite" className="card" style={{ padding: 16, marginBottom: 16 }}>
          {Object.values(operaciones).map((op) => (
            <p key={op.operation_id} role="status">
              {op.servicio_id ? `Servicio #${op.servicio_id}` : op.pedido_id ? `Pedido #${op.pedido_id}` : 'Operación'}: {textoOperacion(op)}
              {op.error_detalle_seguro && <span> {op.error_detalle_seguro}</span>}
            </p>
          ))}
        </section>
      )}

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
            aria-label="Listado de servicios" aria-busy={srvRemote.loading}
            data-modelo={filtroTipo}
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
                  const operacion = Object.values(operaciones).find((op) => op.servicio_id === s.id && operacionAbierta(op));
                  const ocupada = Boolean(operacion) || Boolean(s.operation_id && !operaciones[s.operation_id]) || (accionando !== null
                    && accionando.tipo !== 'deploy' && accionando.id === s.id);
                  const permite = (accion) => !ocupada && Boolean(s.acciones_habilitadas?.includes(accion));
                  const motivoAccion = (accion) => {
                    if (ocupada) return 'Esperá a que termine la operación en curso.';
                    if (s.regularizacion_pendiente) return 'Administración debe revisar los datos y las fechas de este servicio.';
                    if (accion === 'restart' && s.estado !== 'running') return 'El servicio debe estar encendido para reiniciarlo.';
                    return s.motivo_bloqueo || 'Esta acción no está disponible para el estado actual del servicio.';
                  };
                  const abreHaciaArriba = serviciosFiltrados.length > 1 && idx >= serviciosFiltrados.length - 1;

                  return (
                    <tr key={s.id} data-servicio-id={s.id} data-modelo={s.modelo_servicio}>
                      {isAdmin && (
                        <td className="cell-strong tabnum" style={{ color: 'var(--color-accent-700)' }}>
                          {s.proxmox_vmid || '—'}
                        </td>
                      )}
                      <td className="nowrap">
                        <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                          <div className="row gap-2" style={{ alignItems: 'center' }}>
                            <span className="cell-strong">
                              {s.nombre_snapshot || tpl?.nombre || s.hostname || `Servicio #${s.id}`}
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
                          <button className="btn btn-secondary btn-sm" onClick={() => setAccess(s)}>Ver acceso</button>

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
                              <Spinner size={11} /> {operacion ? textoOperacion(operacion) : EN_CURSO[accionando?.tipo] || 'Operación pendiente…'}
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
                          <CoberturaServicio servicio={s} isAdmin={isAdmin} onModificar={(periodo) => handleRenovar(s, periodo)} disabled={ocupada || !s.acciones_habilitadas?.includes('renovar')} />
                          {s.regularizacion_pendiente ? <button type="button" className="btn btn-secondary btn-sm"
                            aria-haspopup="dialog" onClick={() => setRevisionDetalle(s)}>
                            <CircleAlert size={14} aria-hidden="true" /> Pendiente de Revisión
                          </button> : s.motivo_bloqueo && <span className="card-meta">{s.motivo_bloqueo}</span>}
                          {isAdmin && s.regularizacion_legacy && s.regularizacion_pendiente && <button
                            className="btn btn-secondary btn-sm" disabled={ocupada} onClick={() => { setNotice(''); setRegularizacion(s); }}>
                            Regularizar registro
                          </button>}
                          <span className="card-meta">{s.confirmado_at ? `Última confirmación: ${new Date(s.confirmado_at).toLocaleString('es-AR')}` : 'Sin confirmación registrada'} · {s.fuente_observacion === 'worker' ? 'Observación del sistema' : 'Sin observación reciente'}</span>
                          {resultadoPreferencia?.id === s.id && <p className={`service-action-feedback ${resultadoPreferencia.error ? 'bad' : ''}`}
                            role={resultadoPreferencia.error ? 'alert' : 'status'}>{resultadoPreferencia.mensaje}</p>}
                        </div>
                      </td>

                      <td className="tabnum nowrap">{fmtFecha(s.deployed_at)}</td>

                      <td>
                        <div className="row gap-1" style={{ justifyContent: 'flex-end', position: 'relative' }}>
                          {s.existe_en_proxmox === false ? (
                            isAdmin ? (
                              <button className="btn-icon danger" onClick={() => handleEliminar(s)}
                                disabled={!permite('delete')} aria-busy={busy('delete')} title="Dar de baja">
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
                                  disabled={!permite('start')}
                                  aria-label="Reanudar / Reactivar servicio"
                                  aria-busy={busy('reactivar')}
                                  title={permite('start') ? 'Reanudar / Reactivar servicio' : motivoAccion('start')}
                                >
                                  {busy('reactivar') ? <Spinner size={14} /> : <Play size={16} />}
                                </button>
                              ) : s.estado === 'running' ? (
                                <button
                                  className="btn-icon warn"
                                  onClick={() => handleStop(s.id)}
                                  disabled={!permite('stop')}
                                  aria-label="Pausar / Detener servicio"
                                  aria-busy={busy('stop')}
                                  title={permite('stop') ? 'Pausar / Detener servicio' : motivoAccion('stop')}
                                >
                                  {busy('stop') ? <Spinner size={14} /> : <Pause size={16} />}
                                </button>
                              ) : (
                                <button
                                  className="btn-icon ok"
                                  onClick={() => handleStart(s.id)}
                                  disabled={!permite('start')}
                                  aria-label="Iniciar servicio"
                                  aria-busy={busy('start')}
                                  title={permite('start') ? 'Iniciar servicio' : motivoAccion('start')}
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
                                    {(s.regularizacion_pendiente || ocupada) && <p className="service-menu-note">
                                      {ocupada ? 'Hay una operación en curso. Esperá su confirmación.' : 'Algunas acciones requieren que administración revise los datos del servicio.'}
                                    </p>}
                                    {/* Reiniciar */}
                                    <button
                                      className="menu-item"
                                      onClick={() => {
                                        setMenuAccionesAbierto(null);
                                        handleRestart(s.id);
                                      }}
                                      disabled={!permite('restart')}
                                      title={!permite('restart') ? motivoAccion('restart') : undefined}
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
                                      disabled={!permite('renovar')}
                                      title={!permite('renovar') ? motivoAccion('renovar') : undefined}
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
                                      <span>{isAdmin ? 'Estado en Proxmox' : 'Consultar estado'}</span>
                                    </button>

                                    {/* Dar de baja */}
                                    {isAdmin && (
                                      <>
                                        <div style={{ height: 1, background: 'var(--color-divider)', margin: '4px 0' }} />
                                        <button
                                          className="menu-item danger"
                                          onClick={() => {
                                            setMenuAccionesAbierto(null);
                                            handleEliminar(s);
                                          }}
                                          disabled={!permite('delete')}
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
            {loading ? 'Cargando…' : (srvRemote.error ? 'No se pudo confirmar el listado de servicios.' : hayFiltrosActivos ? 'No se encontraron servicios que coincidan con los filtros.' : 'No hay servicios desplegados aún.')}
          </Empty>
        )}
      </div>

      {access && <Dialog wide title={`Acceso: ${access.nombre_snapshot || `Servicio #${access.id}`}`} onClose={() => setAccess(null)}>
        <AccesoServicio servicio={access} user={user} onVerified={fetchData} />
      </Dialog>}

      {revisionDetalle && <Dialog title="Pendiente de Revisión" onClose={() => setRevisionDetalle(null)}
        actions={<button type="button" className="btn btn-secondary" onClick={() => setRevisionDetalle(null)}>Entendido</button>}>
        <div className="col gap-3">
          <p><strong>{revisionDetalle.nombre_snapshot || revisionDetalle.hostname || `Servicio #${revisionDetalle.id}`}</strong></p>
          <p>Administración debe confirmar qué recurso corresponde a este servicio y sus fechas de uso. Hasta completar esa revisión, no se permite iniciar, reiniciar ni renovar.</p>
          <p>{isAdmin ? 'Usá «Regularizar registro» si está disponible. Si requiere reconciliación, revisá el registro antes de continuar.' : 'Pedile al administrador del portal que revise este servicio.'}</p>
        </div>
      </Dialog>}

      {statusDetalle && (
        <Dialog wide title="Estado del servicio" onClose={cerrarEstado}>
          {statusDetalle.loading && <p role="status"><Spinner /> Consultando el estado del servicio…</p>}
          {statusDetalle.error && <div className="col gap-3">
            <p role="alert">{statusDetalle.error}</p>
            <button className="btn btn-secondary" onClick={() => handleStatus(statusDetalle.servicioId)}>Reintentar consulta</button>
          </div>}
          {statusDetalle.data && <div className="col gap-3">
            <p>Estado consultado: <strong>{CFG[statusDetalle.data.proxmox_status?.status]?.label || 'Sin confirmar'}</strong>.</p>
            <p>Esta consulta no inicia ni reinicia el servicio.</p>
            {isAdmin && <details><summary>Detalles técnicos</summary><pre style={{
            fontSize: 12, color: 'var(--text-body)', overflowX: 'auto',
            background: 'color-mix(in srgb, var(--color-text) 6%, transparent)',
            padding: 'var(--space-3)', borderRadius: 'var(--radius-md)',
          }}>
            {JSON.stringify(statusDetalle.data.proxmox_status, null, 2)}
          </pre></details>}
          </div>}
        </Dialog>
      )}
    </div>
  );
}
