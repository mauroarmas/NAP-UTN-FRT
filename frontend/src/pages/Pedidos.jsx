import { mensajeError } from '../utils/errors.js';
import { useState, useEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import useRemoteData from '../hooks/useRemoteData';
import EstadoConsulta from '../components/EstadoConsulta';
import ProgresoDespliegue from '../components/ProgresoDespliegue';
import useOperacion, { operacionAbierta, textoOperacion } from '../hooks/useOperacion';
import {
  Search, Send, Info, CheckCircle2, XCircle, AlertTriangle, RefreshCw,
  Clock, History, Calendar, Server, Users, FileText, ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  getPedidos, getPedido, desplegarPedido, reintentarPedido,
  getTemplates, getCatedras, getCatedrasMias, rechazarPedido,
  revertirAprobacion, cancelarPedido,
} from '../services/api';
import NuevoPedidoModal from '../components/NuevoPedidoModal';
import AprobarPedidoModal from '../components/AprobarPedidoModal';
import AjustePedidoModal from '../components/AjustePedidoModal';
import ReenviarPedidoModal from '../components/ReenviarPedidoModal';
import ConsolaOperacion from '../components/ConsolaOperacion';
import { PageHead, StatusPill, Dialog, Empty } from '../components/ui';
import { ESTADO_PEDIDO_CONFIG as ESTADO_CONFIG, PASOS_PEDIDO } from '../constants/estados';

// Una aprobación revertida y un rechazo original terminan en el mismo estado.
// Para la cátedra no son lo mismo: un pedido que estaba aprobado y deja de
// estarlo en silencio es indistinguible de una falla del portal, así que hay
// que decirlo con todas las letras (FR-010).
//
// La fuente autoritativa es el historial —una transición de aprobado a
// rechazado con autor persona—, pero el listado no lo trae. Ahí se cae al
// prefijo que el backend antepone al motivo, fijado en el contrato de la 005.
const EMPTY = [];
const PREFIJO_REVERSION = 'Aprobación revertida';

const entradaDeReversion = (historial) =>
  (historial || []).filter(
    (h) => h.estado_anterior === 'aprobado' && h.estado_nuevo === 'rechazado' && h.usuario_id != null,
  ).slice(-1)[0];

const fueRevertido = (p) =>
  Boolean(entradaDeReversion(p.historial)) || Boolean(p.motivo_rechazo?.startsWith(PREFIJO_REVERSION));

// El motivo llega como "Aprobación revertida: <lo que escribió el admin>". La
// etiqueta ya la pone la interfaz, así que acá sobra repetirla.
const motivoLimpio = (texto) =>
  texto?.startsWith(PREFIJO_REVERSION) ? texto.slice(texto.indexOf(':') + 1).trim() : texto;

// El historial en palabras. Las tres formas de llegar a rechazado se leen
// distinto —rechazo original, reversión humana, vencimiento automático— y el
// sistema aparece nombrado como autor donde corresponde (FR-009).
const describirEntrada = (h) => {
  if (h.estado_anterior === 'nuevo') return 'La cátedra creó el pedido';
  if (h.estado_nuevo === 'aprobado') return 'Un administrador lo aprobó y reservó la capacidad';
  if (h.estado_nuevo === 'rechazado' && h.estado_anterior === 'aprobado') {
    return h.usuario_id == null
      ? 'Venció la reserva sin desplegarse y la capacidad se liberó sola'
      : 'Un administrador deshizo la aprobación y liberó la capacidad';
  }
  if (h.estado_nuevo === 'rechazado') return 'Un administrador lo rechazó';
  const desde = ESTADO_CONFIG[h.estado_anterior]?.label || h.estado_anterior;
  const hasta = ESTADO_CONFIG[h.estado_nuevo]?.label || h.estado_nuevo;
  return `${desde} → ${hasta}`;
};

const PILL_KIND = { info: 'accent', success: 'ok', warning: 'warn', error: 'bad', neutral: 'off' };
const kindDe = (estado) => PILL_KIND[ESTADO_CONFIG[estado]?.badge] || 'off';

const specsDe = (p, template) => {
  const snapshot = p.asignacion_snapshot;
  if (snapshot) return `${snapshot.vcpus} vCPU · ${snapshot.ram_mb} MiB · ${snapshot.disk_gb} GiB`;
  if (template && ['solicitado', 'requiere_ajuste'].includes(p.estado)) return `Referencia del perfil: ${template.default_vcpus} vCPU · ${template.default_ram_mb} MiB · ${template.default_disk_gb} GiB`;
  return 'Asignación histórica pendiente de regularización';
};

const tipoTemplate = (t, modelo) => {
  if (t?.tipo === 'qemu') return 'Máquina Virtual';
  if (t?.tipo === 'lxc') return 'Contenedor LXC';
  if (modelo === 'saas') return 'Software (SaaS)';
  if (modelo === 'paas') return 'Plataforma (PaaS)';
  return 'Servicio';
};

const formatFechaCorta = (fechaStr) => {
  if (!fechaStr) return '';
  const parts = String(fechaStr).split(/[-T ]/);
  if (parts.length >= 3 && parts[0].length === 4) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return fechaStr;
};

const vigenciaLabel = (p) => {
  const tipo = p?.vigencia?.tipo || p?.vigencia_tipo;
  if (!tipo) return null;
  const labels = {
    primer_cuatrimestre: '1° Cuatrimestre',
    segundo_cuatrimestre: '2° Cuatrimestre',
    anual: 'Ciclo Anual',
    personalizado:
      p.vigencia?.desde && p.vigencia?.hasta
        ? `${formatFechaCorta(p.vigencia.desde)} al ${formatFechaCorta(p.vigencia.hasta)}`
        : 'Personalizado',
  };
  const year = p.vigencia?.anio_lectivo || p.anio_lectivo;
  return `${labels[tipo] || tipo}${year ? ` ${year}` : ''}`;
};

function VigenciaPedido({ pedido, formatDate }) {
  const period = pedido.vigencia_aprobada;
  return <div className="col gap-1 card-meta">
    {period && <span>Período aprobado: {formatFechaCorta(period.desde)} al {formatFechaCorta(period.hasta)}, inclusive ({period.zona_horaria}).</span>}
    {pedido.tipo === 'alta' && pedido.estado === 'aprobado' && <>
      <span>{pedido.compromiso_capacidad?.estado === 'reservado' && pedido.compromiso_capacidad.expira_at
        ? `Reserva hasta ${formatDate(pedido.compromiso_capacidad.expira_at)}.` : 'Sin reserva vigente comprobada.'}</span>
      <span>{pedido.despliegue_habilitado ? 'Fecha habilitada: administración puede solicitar el despliegue.' : period ? `Despliegue sujeto a la fecha inicial (${formatFechaCorta(period.desde)}) y a una reserva vigente.` : 'La vigencia requiere regularización antes del despliegue.'} El despliegue requiere una acción explícita.</span>
    </>}
  </div>;
}

const modeloServicioBadge = (modelo) => {
  const m = (modelo || 'iaas').toLowerCase();
  if (m === 'saas') return { label: 'SaaS', kind: 'accent' };
  if (m === 'paas') return { label: 'PaaS', kind: 'warn' };
  return { label: 'IaaS', kind: 'neutral' };
};

const parseDescripcionPedido = (p) => {
  const raw = (
    p?.descripcion_requerimientos ||
    p?.parametros_extra?.justificacion_uso ||
    p?.parametros_extra?.descripcion ||
    p?.parametros_extra?.justificacion ||
    ''
  ).trim();

  let titulo = p?.parametros_extra?.titulo || null;
  let software = p?.parametros_extra?.software_solicitado || null;
  let justificacion = raw;

  // Extraer [Servicio Solicitado: ...]
  const servMatch = justificacion.match(/\[Servicio Solicitado:\s*([^\]]+)\]/i);
  if (servMatch) {
    if (!software) software = servMatch[1].trim();
    justificacion = justificacion.replace(servMatch[0], '').trim();
  }

  // Extraer [Propósito: ...]
  const propMatch = justificacion.match(/\[Propósito:\s*([^\]]+)\]/i);
  if (propMatch) {
    if (!titulo) titulo = propMatch[1].trim();
    justificacion = justificacion.replace(propMatch[0], '').trim();
  }

  return {
    titulo,
    software,
    justificacion,
    raw,
  };
};

const descripcionPedido = (p) => {
  const parsed = parseDescripcionPedido(p);
  if (parsed.titulo && parsed.justificacion) {
    return `${parsed.titulo} — ${parsed.justificacion}`;
  }
  return parsed.titulo || parsed.justificacion || parsed.raw;
};

export default function Pedidos({ user }) {
  const location = useLocation();
  const navigate = useNavigate();
  const pedidoDesdeAviso = Number(new URLSearchParams(location.search).get('pedido'));
  const [filtroEstado, setFiltroEstado] = useState('');
  const [query, setQuery] = useState('');
  const [modalNuevoAbierto, setModalNuevoAbierto] = useState(false);
  const [modalAprobarAbierto, setModalAprobarAbierto] = useState(false);
  const [modalAjusteAbierto, setModalAjusteAbierto] = useState(false);
  const [modalReenviarAbierto, setModalReenviarAbierto] = useState(false);
  const [consolaOperationId, setConsolaOperationId] = useState(null);

  const [detalle, setDetalle] = useState(null);
  const [transicionando, setTransicionando] = useState(false);
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [operationIds, setOperationIds] = useState([]);
  const [notice, setNotice] = useState('');
  const [detalleSinActualizar, setDetalleSinActualizar] = useState(false);
  const pendingPedidos = useRef(false);
  const intentKeys = useRef({});
  const busyRef = useRef(false);
  const claveIntencion = (tipo, id, payload = '') => {
    const target = `${tipo}:${id}`;
    if (intentKeys.current[target]?.payload !== payload) intentKeys.current[target] = { payload, key: crypto.randomUUID() };
    return intentKeys.current[target].key;
  };
  const registrarOrden = (data) => {
    if (data?.operation_id) setOperationIds((current) => [...new Set([...current, data.operation_id])]);
  };
  const [motivoReversion, setMotivoReversion] = useState('');

  const handleCancelarPedido = async (pedidoId) => {
    if (busyRef.current) return;
    const motivo = prompt('Motivo de cancelación (obligatorio):');
    if (!motivo?.trim()) return;
    busyRef.current = true;
    setTransicionando(true);
    try {
      await cancelarPedido(pedidoId, motivo.trim(), claveIntencion('cancelar', pedidoId, motivo.trim()));
      delete intentKeys.current[`cancelar:${pedidoId}`];
      await actualizarDetalle(pedidoId);
    } catch (err) {
      alert(mensajeError(err, 'Error al cancelar el pedido'));
    } finally {
      busyRef.current = false;
      setTransicionando(false);
    }
  };

  const isAdmin = user?.rol === 'admin';

  const scope = `${user?.id || ''}:${user?.rol || ''}`;
  const pedidosRemote = useRemoteData((options) => getPedidos(filtroEstado || null, options), {
    key: `pedidos:${scope}:${filtroEstado}`, refreshMs: 5000,
    canRefresh: () => pendingPedidos.current && !busyRef.current && !modalAprobarAbierto && !modalAjusteAbierto && !modalReenviarAbierto,
    errorMessage: 'No se pudieron consultar los pedidos.' });
  const pedidos = pedidosRemote.data || EMPTY;
  pendingPedidos.current = pedidos.some((p) => p.estado === 'en_despliegue' || p.operation_id);
  const loading = pedidosRemote.loading && !pedidosRemote.data;
  const fetchPedidos = pedidosRemote.reload;
  useEffect(() => {
    if (pedidosRemote.data) setOperationIds((current) => [...new Set([...current,
      ...pedidosRemote.data.map((p) => p.operation_id).filter(Boolean)])]);
  }, [pedidosRemote.data]);
  const templatesRemote = useRemoteData((options) => getTemplates(true, null, options), {
    key: `perfiles-pedidos:${scope}`, errorMessage: 'No se pudieron consultar los perfiles.' });
  const categoriesRemote = useRemoteData((options) => isAdmin ? getCatedras(options) : getCatedrasMias(options), {
    key: `catedras-pedidos:${scope}`, errorMessage: 'No se pudieron consultar las cátedras.' });
  const templates = templatesRemote.data || EMPTY;
  const catedras = isAdmin ? categoriesRemote.data || EMPTY : EMPTY;
  const misCatedras = isAdmin ? EMPTY : categoriesRemote.data || EMPTY;

  const fuente = isAdmin ? catedras : misCatedras;
  const templateDe = (id) => templates.find((t) => t.id === id);
  const templateNombre = (id) => (id ? (templateDe(id)?.nombre || `Template #${id}`) : 'Servicio a Medida');
  const catedraNombre = (id) => fuente.find((c) => c.id === id)?.nombre || `Cátedra #${id}`;
  const catedraResponsable = (id) => fuente.find((c) => c.id === id)?.titular?.nombre;

  const formatDate = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  const visibles = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pedidos;
    return pedidos.filter((p) =>
      [`#${p.id}`, templateNombre(p.template_id), catedraNombre(p.catedra_id), ESTADO_CONFIG[p.estado]?.label, descripcionPedido(p), p.modelo_servicio || '', vigenciaLabel(p) || '']
        .join(' ').toLowerCase().includes(q));
  }, [pedidos, query, templates, catedras, misCatedras]);

  // ---- Detalle / decisiones ----
  const actualizarDetalle = async (id) => {
    await Promise.all([fetchPedidos(), verDetalle(id)]);
  };
  const operaciones = useOperacion(operationIds, () => {
    fetchPedidos();
    if (detalle) verDetalle(detalle.id);
  });
  const operacionDelPedido = (p) => p.operation_id ? operaciones[p.operation_id] : Object.values(operaciones)
    .filter((op) => op.pedido_id === p.id && op.tipo === 'desplegar')
    .sort((a, b) => (Date.parse(a.creado_at) || 0) - (Date.parse(b.creado_at) || 0)).at(-1);

  useEffect(() => {
    if (!Number.isSafeInteger(pedidoDesdeAviso) || pedidoDesdeAviso <= 0) return;
    const controller = new AbortController();
    getPedido(pedidoDesdeAviso, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      setDetalle(data); setDetalleSinActualizar(false);
      if (data.operation_id) setOperationIds((current) => [...new Set([...current, data.operation_id])]);
    }).catch(() => { if (!controller.signal.aborted) setNotice('No se pudo abrir el pedido de esta notificación.'); });
    return () => controller.abort();
  }, [pedidoDesdeAviso, scope]);

  const detalleId = detalle?.id;
  const seguimiento = detalle?.estado === 'en_despliegue' && !modalAprobarAbierto && !modalAjusteAbierto && !modalReenviarAbierto;
  useEffect(() => {
    if (!detalleId || !seguimiento) return;
    let running = false;
    const controller = new AbortController();
    const poll = async () => {
      if (document.hidden || running || busyRef.current) return;
      running = true;
      try {
        const { data } = await getPedido(detalleId, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setDetalle(data); setDetalleSinActualizar(false);
          if (data.operation_id) setOperationIds((current) => [...new Set([...current, data.operation_id])]);
        }
      } catch { if (!controller.signal.aborted) setDetalleSinActualizar(true); }
      finally { running = false; }
    };
    const timer = setInterval(poll, 5000);
    document.addEventListener('visibilitychange', poll);
    return () => { clearInterval(timer); controller.abort(); document.removeEventListener('visibilitychange', poll); };
  }, [detalleId, seguimiento, scope]);

  const verDetalle = async (id) => {
    try {
      const { data } = await getPedido(id);
      setDetalle(data);
      setDetalleSinActualizar(false);
      setMotivoRechazo('');
      setMotivoReversion('');
      registrarOrden(data);
    } catch {
      alert('Error al cargar detalle');
    }
  };

  const cerrarDetalle = () => {
    if (pedidoDesdeAviso) navigate('/pedidos', { replace: true });
    setDetalle(null);
    setMotivoRechazo('');
    setMotivoReversion('');
  };

  const handleRechazar = async () => {
    if (busyRef.current) return;
    if (!motivoRechazo.trim()) {
      alert('Ingresá un motivo de rechazo: la cátedra lo va a ver.');
      return;
    }
    busyRef.current = true;
    setTransicionando(true);
    try {
      await rechazarPedido(detalle.id, motivoRechazo, claveIntencion('rechazar', detalle.id, motivoRechazo));
      delete intentKeys.current[`rechazar:${detalle.id}`];
      await actualizarDetalle(detalle.id);
    } catch (err) {
      alert(mensajeError(err, 'Error al rechazar el pedido'));
    } finally {
      busyRef.current = false;
      setTransicionando(false);
    }
  };

  const handleRevertir = async () => {
    if (busyRef.current) return;
    if (!motivoReversion.trim()) {
      alert('Escribí por qué deshacés la aprobación: la cátedra lo va a ver.');
      return;
    }
    if (!confirm(`¿Deshacer la aprobación del pedido #${detalle.id}?\n\nLa capacidad que había reservado vuelve a estar libre en el acto.`)) return;
    busyRef.current = true;
    setTransicionando(true);
    try {
      const { data } = await revertirAprobacion(detalle.id, motivoReversion, claveIntencion('revertir', detalle.id, motivoReversion));
      delete intentKeys.current[`revertir:${detalle.id}`];
      const c = data.capacidad_liberada;
      await actualizarDetalle(detalle.id);
      alert(c && (c.vcpus || c.ram_mb || c.storage_gb)
        ? `Aprobación deshecha. Volvieron a estar libres ${c.vcpus} vCPU, ${c.ram_mb} MB de RAM y ${c.storage_gb} GB de disco.`
        : 'Aprobación deshecha. Consultá el detalle actualizado de la decisión.');
    } catch (err) {
      // El backend ya redacta un mensaje distinto para cada uno de los cuatro
      // conflictos; volcarlo crudo perdería justamente eso.
      const d = err.response?.data?.detail;
      alert(d?.mensaje || (typeof d === 'string' ? d : 'Error al deshacer la aprobación'));
    } finally {
      busyRef.current = false;
      setTransicionando(false);
    }
  };

  const handleDesplegar = async (pedidoId) => {
    if (busyRef.current || !confirm(`¿Solicitar el despliegue del pedido #${pedidoId}?`)) return;
    busyRef.current = true;
    setTransicionando(true);
    try {
      const { data } = await desplegarPedido(pedidoId, {}, claveIntencion('deploy', pedidoId));
      registrarOrden(data);
      delete intentKeys.current[`deploy:${pedidoId}`];
      await verDetalle(pedidoId);
      fetchPedidos();
    } catch (err) {
      registrarOrden(err.response?.data?.detail);
      alert(mensajeError(err, 'Error al desplegar el pedido'));
    } finally {
      busyRef.current = false;
      setTransicionando(false);
    }
  };

  const handleReintentar = async (pedidoId) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setTransicionando(true);
    try {
      const { data } = await reintentarPedido(pedidoId, {}, claveIntencion('retry', pedidoId));
      registrarOrden(data);
      delete intentKeys.current[`retry:${pedidoId}`];
      await verDetalle(pedidoId);
      fetchPedidos();
    } catch (err) {
      registrarOrden(err.response?.data?.detail);
      alert(mensajeError(err, 'Error al reintentar el despliegue'));
    } finally {
      busyRef.current = false;
      setTransicionando(false);
    }
  };

  const filtroLabel = filtroEstado ? ESTADO_CONFIG[filtroEstado]?.label : 'Todos los estados';

  return (
    <div className="fade-in">
      <PageHead title="Pedidos" subtitle="Gestión y seguimiento de solicitudes de servicio.">
        <div className="input-search">
          <Search size={16} />
          <input
            className="input"
            style={{ minWidth: 250 }}
            placeholder="Buscar por Nº, cátedra, servicio…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select
          className="input"
          style={{ minWidth: 190 }}
          aria-label="Filtrar pedidos por estado"
          value={filtroEstado}
          onChange={(e) => setFiltroEstado(e.target.value)}
        >
          <option value="">Todos los estados</option>
          {Object.entries(ESTADO_CONFIG).map(([key, cfg]) => (
            <option key={key} value={key}>{cfg.label}</option>
          ))}
        </select>
        <button className="btn-send" onClick={() => setModalNuevoAbierto(true)}>
          <Send size={17} />
          <span>Nueva Solicitud</span>
        </button>
      </PageHead>
      {notice && <div className="callout" role="status"><CheckCircle2 size={18}/><span>{notice}</span><button type="button" className="btn btn-ghost" onClick={() => setNotice('')}>Cerrar aviso</button></div>}

      <EstadoConsulta remote={pedidosRemote} nombre="pedidos" />
      <EstadoConsulta remote={templatesRemote} nombre="perfiles" />
      <EstadoConsulta remote={categoriesRemote} nombre="cátedras" />
      <div className="row between" style={{ marginBottom: 'var(--space-4)', alignItems: 'baseline' }}>
        <div className="section-label">Listado</div>
        <span className="section-count">{visibles.length} pedidos · {filtroLabel}</span>
      </div>

      {visibles.length === 0 ? (
        <div className="card">
          <Empty icon={<Search size={22} />}>
            {loading ? 'Cargando…' : pedidosRemote.error ? 'No se pudo confirmar el listado.' : 'Ningún pedido coincide con la búsqueda.'}
          </Empty>
        </div>
      ) : (
        <div className="col gap-3" aria-label="Listado de pedidos" aria-busy={loading} data-estado={filtroEstado}>
          {visibles.map((p) => {
            const tpl = templateDe(p.template_id);
            const cfg = ESTADO_CONFIG[p.estado] || {};
            const paso = cfg.paso ?? -1;
            const responsable = catedraResponsable(p.catedra_id);
            return (
              <div key={p.id} data-pedido-id={p.id} data-estado={p.estado} className="card" style={{ gap: 'var(--space-4)' }}>
                <div className="row between wrap" style={{ alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row wrap gap-2" style={{ alignItems: 'baseline' }}>
                      <span className="section-count">#{p.id}</span>
                      <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 'var(--font-heading-weight)', fontSize: 19 }}>
                        {p.asignacion_snapshot?.nombre || (!p.template_id && parseDescripcionPedido(p).software) || templateNombre(p.template_id)}
                        {p.asignacion_snapshot?.definition_version && <small className="block">Versión autorizada: {p.asignacion_snapshot.definition_version}</small>}
                      </span>
                      {(() => {
                        const mb = modeloServicioBadge(p.modelo_servicio);
                        return <span className={`tag ${mb.kind}`}>{mb.label}</span>;
                      })()}
                      <span className="tag">{tipoTemplate(tpl, p.modelo_servicio)}</span>
                      {vigenciaLabel(p) && <span className="tag neutral">{vigenciaLabel(p)}</span>}
                      {p.tipo === 'renovacion' && <span className="tag neutral">Renovación</span>}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-soft)', marginTop: 8 }}>
                      {catedraNombre(p.catedra_id)}
                      {responsable && ` · ${responsable}`}
                      {` · ${formatDate(p.created_at)}`}
                    </div>
                    <div className="tabnum" style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>
                      {specsDe(p, tpl)}
                    </div>
                    {descripcionPedido(p) && (
                      <div style={{ fontSize: 13, color: 'var(--text-soft)', marginTop: 6, fontStyle: 'italic' }}>
                        “{descripcionPedido(p)}”
                      </div>
                    )}
                  </div>
                  <div className="row gap-3" style={{ flex: 'none' }}>
                    <StatusPill kind={fueRevertido(p) ? 'warn' : kindDe(p.estado)}>
                      {fueRevertido(p) ? 'Aprobación deshecha' : (p.tipo === 'renovacion' && p.estado === 'activo' ? 'Renovación registrada' : cfg.label || p.estado)}
                    </StatusPill>
                    <button className="btn btn-ghost btn-sm" onClick={() => verDetalle(p.id)}>Ver detalle</button>
                  </div>
                </div>

                {p.tipo !== 'renovacion' && ['en_despliegue', 'error'].includes(p.estado)
                  ? (
                    <div>
                      <ProgresoDespliegue pedido={p} operacion={operacionDelPedido(p)} isAdmin={isAdmin} compact/>
                      {isAdmin && (p.operation_id || operacionDelPedido(p)?.operation_id) && (
                        <div style={{ marginTop: '4px' }}>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs"
                            onClick={() => setConsolaOperationId(p.operation_id || operacionDelPedido(p)?.operation_id)}
                          >
                            Ver consola
                          </button>
                        </div>
                      )}
                    </div>
                  )
                  : p.operation_id && <p role="status">{textoOperacion(operaciones[p.operation_id])}</p>}
                <VigenciaPedido pedido={p} formatDate={formatDate} />
                {p.tipo !== 'renovacion' && p.estado !== 'en_despliegue' && paso >= 0 && paso < 3 && (
                  <div className="stepper">
                    {PASOS_PEDIDO.map((label, i) => (
                      <div className="stepper__col" key={label}>
                        <div className="stepper__track">
                          <span className={`stepper__dot ${paso > i ? 'done' : paso === i ? 'current' : ''}`} />
                          {i !== PASOS_PEDIDO.length - 1 && (
                            <span className={`stepper__line ${paso > i ? 'done' : ''}`} />
                          )}
                        </div>
                        <div className={`stepper__label ${paso >= i ? 'active' : ''}`}>{label}</div>
                      </div>
                    ))}
                  </div>
                )}

                {p.motivo_rechazo && (
                  <div className={`callout ${fueRevertido(p) ? 'warn' : 'bad'}`}>
                    <Info size={15} />
                    {fueRevertido(p) ? (
                      <span>
                        <strong>Este pedido estaba aprobado y la aprobación se deshizo.</strong>{' '}
                        {motivoLimpio(p.motivo_rechazo)} Podés volver a pedir lo mismo cuando quieras.
                      </span>
                    ) : (
                      <span>{p.motivo_rechazo}</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {detalle && !modalAprobarAbierto && !modalAjusteAbierto && !modalReenviarAbierto && (
        <DetalleDialog
          detalle={detalle}
          isAdmin={isAdmin}
          templateDe={templateDe}
          templateNombre={templateNombre}
          catedraNombre={catedraNombre}
          formatDate={formatDate}
          onClose={cerrarDetalle}
          transicionando={transicionando || Boolean(detalle.operation_id && (!operaciones[detalle.operation_id] || operacionAbierta(operaciones[detalle.operation_id])))}
          operacion={operacionDelPedido(detalle)}
          sinActualizar={detalleSinActualizar}
          onVerConsola={(opId) => setConsolaOperationId(opId)}
          motivoRechazo={motivoRechazo}
          setMotivoRechazo={setMotivoRechazo}
          motivoReversion={motivoReversion}
          setMotivoReversion={setMotivoReversion}
          onRevertir={handleRevertir}
          onAbrirAprobar={() => setModalAprobarAbierto(true)}
          onAbrirAjuste={() => setModalAjusteAbierto(true)}
          onAbrirReenviar={() => setModalReenviarAbierto(true)}
          onCancelarPedido={handleCancelarPedido}
          onRechazar={handleRechazar}
          onDesplegar={handleDesplegar}
          onReintentar={handleReintentar}
        />
      )}

      <NuevoPedidoModal
        open={modalNuevoAbierto}
        onClose={() => setModalNuevoAbierto(false)}
        onCreated={() => {
          fetchPedidos();
        }}
        user={user}
      />

      <AprobarPedidoModal
        open={modalAprobarAbierto}
        pedido={detalle}
        templates={templates}
        onClose={() => setModalAprobarAbierto(false)}
        onAprobado={(result) => {
          registrarOrden(result);
          setNotice(result.operation_id ? 'Pedido aprobado. El despliegue está en marcha; podés seguir su avance en el detalle.' : 'Pedido aprobado. Los recursos quedaron reservados.');
          actualizarDetalle(detalle.id);
        }}
      />

      <AjustePedidoModal
        user={user}
        open={modalAjusteAbierto}
        pedido={detalle}
        onClose={() => setModalAjusteAbierto(false)}
        onAjusteSolicitado={(result) => {
          registrarOrden(result);
          actualizarDetalle(detalle.id);
        }}
      />

      <ReenviarPedidoModal
        user={user}
        open={modalReenviarAbierto}
        pedido={detalle}
        onClose={() => setModalReenviarAbierto(false)}
        onReenviado={(result) => {
          registrarOrden(result);
          actualizarDetalle(detalle.id);
        }}
      />

      {consolaOperationId && (
        <ConsolaOperacion
          operationId={consolaOperationId}
          onClose={() => setConsolaOperationId(null)}
        />
      )}
    </div>
  );
}

export function DetalleDialog({
  detalle, isAdmin, templateDe, templateNombre, catedraNombre, formatDate, onClose, transicionando,
  operacion, sinActualizar, onVerConsola,
  motivoRechazo, setMotivoRechazo, onAbrirAprobar, onAbrirAjuste, onAbrirReenviar, onCancelarPedido, onRechazar,
  onDesplegar, onReintentar, motivoReversion, setMotivoReversion, onRevertir,
}) {
  const [mostrarRechazo, setMostrarRechazo] = useState(false);
  const [historialAbierto, setHistorialAbierto] = useState(false);

  const cfg = ESTADO_CONFIG[detalle.estado] || {};
  const revertido = fueRevertido(detalle);
  const kind = revertido ? 'warn' : kindDe(detalle.estado);
  const puedeRevertir = isAdmin && detalle.estado === 'aprobado' && !detalle.servicio_id && !transicionando;

  const parsed = parseDescripcionPedido(detalle);
  const tpl = templateDe ? templateDe(detalle.template_id) : null;
  const nombreCabecera = detalle.asignacion_snapshot?.nombre || parsed.software || templateNombre(detalle.template_id);
  const specs = specsDe(detalle, tpl);

  return (
    <Dialog
      wide
      title={`Pedido #${detalle.id} — ${nombreCabecera}`}
      onClose={onClose}
    >
      {/* 1. Header Ribbon con Estado, Modelo, Cátedra, Vigencia y Fecha */}
      <div className="detalle-header-ribbon">
        <div className="row wrap between gap-2" style={{ width: '100%' }}>
          <div className="row wrap gap-2" style={{ alignItems: 'center' }}>
            <StatusPill kind={kind}>
              {revertido ? 'Aprobación deshecha' : (detalle.tipo === 'renovacion' && detalle.estado === 'activo' ? 'Renovación registrada' : cfg.label || detalle.estado)}
            </StatusPill>
            <span className={`tag ${modeloServicioBadge(detalle.modelo_servicio).kind}`}>
              {modeloServicioBadge(detalle.modelo_servicio).label}
            </span>
            <span className="tag neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Users size={12} />
              {catedraNombre(detalle.catedra_id)}
            </span>
            {vigenciaLabel(detalle) && (
              <span className="tag neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Calendar size={12} />
                {vigenciaLabel(detalle)}
              </span>
            )}
          </div>
          {detalle.created_at && (
            <div style={{ fontSize: 12, color: 'var(--text-faint)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Clock size={12} />
              <span>{formatDate(detalle.created_at)}</span>
            </div>
          )}
        </div>
      </div>

      {/* 2. Contenido Destacado de la Solicitud (Propósito, Software, Justificación) */}
      <div className="detalle-content-card">
        <div className="row between wrap gap-2" style={{ marginBottom: 6 }}>
          <div className="row gap-2" style={{ alignItems: 'center' }}>
            <FileText size={16} style={{ color: 'var(--color-accent)' }} />
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-strong)' }}>
              {parsed.titulo || 'Detalles de la Solicitud'}
            </span>
          </div>
          {parsed.software && (
            <span className="tag accent" style={{ fontSize: 12 }}>
              Software: {parsed.software}
            </span>
          )}
        </div>

        <p className="card-meta" style={{ marginTop: 8 }}>Justificación pedagógica</p>
        {parsed.justificacion ? (
          <div
            style={{
              fontSize: 13.5,
              lineHeight: 1.6,
              color: 'var(--text-body)',
              background: 'var(--color-bg)',
              border: '1px solid var(--color-divider)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 14px',
              whiteSpace: 'pre-wrap',
              marginTop: 6,
            }}
          >
            {parsed.justificacion}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--text-faint)', fontStyle: 'italic', marginTop: 4 }}>
            Sin justificación provista por la cátedra.
          </div>
        )}

        {specs && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-soft)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Server size={13} />
            <span>Recursos asignados: <strong>{specs}</strong></span>
          </div>
        )}
      </div>

      {/* 3. Avisos / Observaciones previas si existen */}
      {detalle.observaciones_ajuste && (
        <div className="callout warn" style={{ marginBottom: 'var(--space-3)' }}>
          <AlertTriangle size={16} />
          <div>
            <strong>Aclaración solicitada por administración:</strong>
            <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{detalle.observaciones_ajuste}</div>
          </div>
        </div>
      )}

      {detalle.motivo_rechazo && (
        <div className={`callout ${revertido ? 'warn' : 'bad'}`} style={{ marginBottom: 'var(--space-3)' }}>
          <Info size={16} />
          <div>
            {revertido ? (
              <span>
                <strong>Aprobación deshecha:</strong> {motivoLimpio(detalle.motivo_rechazo)} La capacidad que tenía reservada volvió a estar libre.
              </span>
            ) : (
              <span><strong>Motivo de rechazo:</strong> {detalle.motivo_rechazo}</span>
            )}
          </div>
        </div>
      )}

      <VigenciaPedido pedido={detalle} formatDate={formatDate} />
      {sinActualizar && <p role="alert" className="callout warn">No se pudo actualizar el pedido. Mostramos el último estado y volveremos a consultar.</p>}
      {detalle.tipo !== 'renovacion' && ['en_despliegue', 'error'].includes(detalle.estado)
        ? (
          <div>
            <ProgresoDespliegue pedido={detalle} operacion={operacion} isAdmin={isAdmin}/>
            {isAdmin && (detalle.operation_id || operacion?.operation_id) && (
              <div style={{ marginTop: '8px' }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => onVerConsola?.(detalle.operation_id || operacion?.operation_id)}
                >
                  Ver consola
                </button>
              </div>
            )}
          </div>
        )
        : detalle.operation_id && (
          <div>
            <p role="status">{textoOperacion(operacion)}</p>
            {isAdmin && (
              <div style={{ marginTop: '4px' }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => onVerConsola?.(detalle.operation_id || operacion?.operation_id)}
                >
                  Ver consola
                </button>
              </div>
            )}
          </div>
        )}
      {detalle.tipo === 'renovacion' && detalle.estado === 'activo' && <p>Las nuevas condiciones quedaron registradas. Consultá el estado del servicio para saber si está encendido.</p>}
      {isAdmin && detalle.estado === 'solicitado' && (
        <div className="decision-container">
          <p>Revisá recursos, fechas y capacidad antes de confirmar la asignación.</p>
          <div className="row gap-2 wrap">
            <button className="btn btn-primary" onClick={onAbrirAprobar} disabled={transicionando}><CheckCircle2 size={15} /> Revisar y aprobar…</button>
            <button className="btn btn-warning" onClick={onAbrirAjuste} disabled={transicionando}>Pedir aclaración</button>
            <button className="btn btn-ghost" onClick={() => setMostrarRechazo(!mostrarRechazo)} disabled={transicionando}><XCircle size={15} /> Rechazar…</button>
          </div>
          {mostrarRechazo && <div className="col gap-2">
            <label htmlFor="reject-reason">Motivo de rechazo (visible para la cátedra)</label>
            <textarea id="reject-reason" value={motivoRechazo} maxLength={2000} onChange={(e) => setMotivoRechazo(e.target.value)} disabled={transicionando} />
            <button className="btn btn-danger" onClick={onRechazar} disabled={transicionando || !motivoRechazo.trim()}>Confirmar rechazo</button>
          </div>}
        </div>
      )}

      {isAdmin && detalle.estado === 'error' && <section className="decision-container">
        <p>El cierre exige ausencia confirmada o una operación sin envío, sin recursos ni compromisos pendientes.</p>
        <label htmlFor="reject-error-reason">Motivo de cierre del pedido fallido</label>
        <textarea id="reject-error-reason" value={motivoRechazo} maxLength={2000} onChange={(e) => setMotivoRechazo(e.target.value)} disabled={transicionando} />
        <button className="btn btn-danger" onClick={onRechazar} disabled={transicionando || !motivoRechazo.trim()}>Cerrar pedido fallido como rechazado</button>
      </section>}

      {/* 5. Acciones de Ajuste (cuando requiere ajuste) */}
      {detalle.estado === 'requiere_ajuste' && (
        <div className="decision-container">
          <div className="section-label" style={{ margin: 0, fontSize: '0.84rem' }}>Aclaración pendiente</div>
          <p className="text-muted" style={{ margin: 0 }}>
            Revisá las observaciones, completá la información y reenviá el pedido para que administración lo evalúe nuevamente.
          </p>
          <div className="row gap-2 wrap" style={{ paddingTop: 'var(--space-2)' }}>
            <button className="btn btn-primary btn-sm" onClick={onAbrirReenviar} disabled={transicionando}>
              {isAdmin ? 'Modificar y reenviar solicitud' : 'Responder aclaración'}
            </button>
            {isAdmin && <button className="btn btn-danger btn-sm" onClick={() => onCancelarPedido(detalle.id)} disabled={transicionando}>
              Cancelar solicitud
            </button>}
          </div>
        </div>
      )}

      {/* 6. Deshacer aprobación */}
      {puedeRevertir && (
        <div className="decision-container" style={{ borderColor: 'var(--st-warn-bd)' }}>
          <div className="section-label" style={{ margin: 0, fontSize: '0.84rem', color: 'var(--st-warn)' }}>
            Deshacer la aprobación
          </div>
          <p className="text-muted" style={{ margin: 0 }}>
            Libera en el acto la capacidad que este pedido tiene reservada, sin esperar a que la
            reserva venza sola. La cátedra ve el motivo y puede volver a pedir lo mismo.
          </p>
          <div className="field" style={{ margin: 0 }}>
            <label style={{ fontSize: 12 }}>Motivo (la cátedra lo va a ver):</label>
            <input
              className="input"
              placeholder="Ej: Aprobado por error / cambio de cronograma"
              value={motivoReversion}
              onChange={(e) => setMotivoReversion(e.target.value)}
            />
          </div>
          <div className="row right" style={{ paddingTop: 'var(--space-2)' }}>
            <button className="btn btn-danger btn-sm" onClick={onRevertir} disabled={transicionando}>
              Deshacer aprobación y liberar capacidad
            </button>
          </div>
        </div>
      )}

      {/* 7. Otras transiciones de administración (Desplegar, Reintentar, etc.) */}
      {isAdmin && (detalle.estado === 'aprobado' || detalle.estado === 'error') && (
        <div className="decision-container">
          <div className="section-label" style={{ margin: 0, fontSize: '0.84rem' }}>Acciones Operativas</div>
          <div className="row gap-2 wrap" style={{ paddingTop: 'var(--space-2)' }}>
            {detalle.estado === 'aprobado' && (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onDesplegar(detalle.id)}
                disabled={transicionando || (detalle.estado === 'aprobado' && !detalle.despliegue_habilitado)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <Server size={14} /> Desplegar en Proxmox
              </button>
            )}
            {detalle.estado === 'error' && (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onReintentar(detalle.id)}
                disabled={transicionando || (detalle.estado === 'aprobado' && !detalle.despliegue_habilitado)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <RefreshCw size={14} /> Reintentar despliegue
              </button>
            )}
          </div>
        </div>
      )}

      {/* 8. Historial de Estados y Auditoría (Plegable al final) */}
      <div style={{ marginTop: 'var(--space-3)', borderTop: '1px solid var(--color-divider)', paddingTop: 'var(--space-3)' }}>
        <button
          type="button"
          onClick={() => setHistorialAbierto(!historialAbierto)}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 12px',
            fontSize: 13,
            color: 'var(--text-soft)',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-divider)',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
          }}
        >
          <div className="row gap-2" style={{ alignItems: 'center' }}>
            <History size={14} />
            <span style={{ fontWeight: 500 }}>
              Historial de estados y auditoría ({detalle.historial?.length || 0} eventos)
            </span>
          </div>
          {historialAbierto ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {historialAbierto && (
          <div className="col gap-2 mt-2" style={{ padding: '4px 0' }}>
            {detalle.historial?.map((h) => (
              <div
                key={h.id}
                className="row between"
                style={{
                  padding: '8px 12px',
                  borderLeft: '2px solid var(--color-accent)',
                  background: 'var(--color-surface)',
                  borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                }}
              >
                <div style={{ fontSize: 12 }}>
                  <span style={{ fontWeight: 500, color: 'var(--text-strong)' }}>{describirEntrada(h)}</span>
                  {h.usuario_id == null && <span className="tag neutral" style={{ marginLeft: 6, fontSize: 10 }}>Automático</span>}
                  {h.comentario && <span style={{ color: 'var(--text-soft)' }}> · {h.comentario}</span>}
                </div>
                <span className="nowrap" style={{ fontSize: 11, color: 'var(--text-faint)' }}>{formatDate(h.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}
