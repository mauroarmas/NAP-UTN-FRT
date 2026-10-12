import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Send, Info, CheckCircle2, XCircle, AlertTriangle, RefreshCw,
  Clock, History, Calendar, Server, Users, FileText, ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  getPedidos, getPedido, cambiarEstadoPedido, desplegarPedido, reintentarPedido,
  getTemplates, getCatedras, getCatedrasMias, evaluarPedido, aprobarPedido, rechazarPedido,
  revertirAprobacion, cancelarPedido,
} from '../services/api';
import PanelCapacidad from '../components/PanelCapacidad';
import NuevoPedidoModal from '../components/NuevoPedidoModal';
import AprobarPedidoModal from '../components/AprobarPedidoModal';
import AjustePedidoModal from '../components/AjustePedidoModal';
import ReenviarPedidoModal from '../components/ReenviarPedidoModal';
import { PageHead, StatusPill, Dialog, Empty } from '../components/ui';
import { ESTADO_PEDIDO_CONFIG as ESTADO_CONFIG, PASOS_PEDIDO } from '../constants/estados';

// Transiciones que decide un admin a mano. "en_despliegue" no aparece nunca acá:
// es transitorio y solo lo asigna el orquestador durante un despliegue real.
const TRANSICIONES = {
  solicitado:    [],
  aprobado:      [],
  en_despliegue: [],
  activo:        ['suspendido'],
  error:         ['rechazado'],
  suspendido:    ['activo'],
  rechazado:     [],
};

// Una aprobación revertida y un rechazo original terminan en el mismo estado.
// Para la cátedra no son lo mismo: un pedido que estaba aprobado y deja de
// estarlo en silencio es indistinguible de una falla del portal, así que hay
// que decirlo con todas las letras (FR-010).
//
// La fuente autoritativa es el historial —una transición de aprobado a
// rechazado con autor persona—, pero el listado no lo trae. Ahí se cae al
// prefijo que el backend antepone al motivo, fijado en el contrato de la 005.
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
  const [v, r, d] = [p.reserva_vcpus, p.reserva_ram_mb, p.reserva_disk_gb];
  if (v || r || d) return `${v} vCPU · ${r} MB · ${d} GB`;
  if (template) return `${template.default_vcpus} vCPU · ${template.default_ram_mb} MB · ${template.default_disk_gb} GB`;
  return '';
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
  if (!p?.vigencia_tipo) return null;
  const labels = {
    primer_cuatrimestre: '1° Cuatrimestre',
    segundo_cuatrimestre: '2° Cuatrimestre',
    anual: 'Ciclo Anual',
    personalizado:
      p.vigencia_desde && p.vigencia_hasta
        ? `${formatFechaCorta(p.vigencia_desde)} al ${formatFechaCorta(p.vigencia_hasta)}`
        : 'Personalizado',
  };
  return labels[p.vigencia_tipo] || p.vigencia_tipo;
};

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
  const navigate = useNavigate();
  const [pedidos, setPedidos] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [misCatedras, setMisCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [query, setQuery] = useState('');
  const [modalNuevoAbierto, setModalNuevoAbierto] = useState(false);
  const [modalAprobarAbierto, setModalAprobarAbierto] = useState(false);
  const [modalAjusteAbierto, setModalAjusteAbierto] = useState(false);
  const [modalReenviarAbierto, setModalReenviarAbierto] = useState(false);

  const [detalle, setDetalle] = useState(null);
  const [transicionando, setTransicionando] = useState(false);
  const [comentario, setComentario] = useState('');
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [evaluacion, setEvaluacion] = useState(null);
  const [justificacion, setJustificacion] = useState('');
  const [motivoReversion, setMotivoReversion] = useState('');

  const handleCancelarPedido = async (pedidoId) => {
    const motivo = prompt('¿Deseas indicar un motivo para la cancelación? (opcional)');
    if (motivo === null) return;
    setTransicionando(true);
    try {
      const { data } = await cancelarPedido(pedidoId, motivo || null);
      setDetalle(data);
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al cancelar el pedido');
    } finally {
      setTransicionando(false);
    }
  };

  const isAdmin = user?.rol === 'admin';

  const fetchPedidos = async () => {
    try {
      const { data } = await getPedidos(filtroEstado || null);
      setPedidos(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPedidos();
    getTemplates().then(({ data }) => setTemplates(data)).catch(console.error);
    if (isAdmin) getCatedras().then(({ data }) => setCatedras(data)).catch(console.error);
    else getCatedrasMias().then(({ data }) => setMisCatedras(data)).catch(console.error);
  }, [filtroEstado]);

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
  const cargarEvaluacion = async (pedidoId) => {
    setEvaluacion(null);
    setJustificacion('');
    try {
      const { data } = await evaluarPedido(pedidoId);
      setEvaluacion(data);
    } catch (err) {
      console.error(err);
    }
  };

  const verDetalle = async (id) => {
    try {
      const { data } = await getPedido(id);
      setDetalle(data);
      setEvaluacion(null);
      setComentario('');
      setMotivoRechazo('');
      setMotivoReversion('');
      if (isAdmin && data.estado === 'solicitado') await cargarEvaluacion(id);
    } catch {
      alert('Error al cargar detalle');
    }
  };

  const cerrarDetalle = () => {
    setDetalle(null);
    setEvaluacion(null);
    setComentario('');
    setMotivoRechazo('');
    setMotivoReversion('');
  };

  const handleAprobar = async () => {
    if (!evaluacion) return;
    if (evaluacion.excede_capacidad && !justificacion.trim()) {
      alert('Aprobar por encima de la capacidad libre requiere una justificación.');
      return;
    }

    const mensaje = evaluacion.excede_capacidad
      ? `¿Seguro que deseas aprobar directamente el pedido #${evaluacion.pedido.id}?\n\n` +
        `⚠️ ATENCIÓN: Este pedido excede la capacidad disponible física del clúster.\n` +
        `Se reservará la capacidad bajo tu justificación administrativa.`
      : `¿Seguro que deseas aprobar directamente el pedido #${evaluacion.pedido.id}?\n\n` +
        `Se reservará la capacidad en el clúster con la configuración predeterminada.`;

    if (!confirm(mensaje)) return;

    setTransicionando(true);
    try {
      const { data } = await aprobarPedido(evaluacion.pedido.id, {
        capacidad_token: evaluacion.capacidad_token,
        justificacion_capacidad: justificacion.trim() || null,
      });
      setDetalle(data);
      setEvaluacion(null);
      fetchPedidos();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d?.codigo === 'token_desactualizado') {
        alert('La capacidad del clúster cambió mientras mirabas este pedido.\n\nLos números se actualizaron: revisalos y confirmá de nuevo.');
        await cargarEvaluacion(evaluacion.pedido.id);
      } else if (d?.codigo === 'excede_capacidad') {
        alert(d.mensaje);
        await cargarEvaluacion(evaluacion.pedido.id);
      } else {
        alert(typeof d === 'string' ? d : 'Error al aprobar el pedido');
      }
    } finally {
      setTransicionando(false);
    }
  };

  const handleRechazar = async () => {
    if (!motivoRechazo.trim()) {
      alert('Ingresá un motivo de rechazo: la cátedra lo va a ver.');
      return;
    }
    setTransicionando(true);
    try {
      const { data } = await rechazarPedido(detalle.id, motivoRechazo);
      setDetalle(data);
      setEvaluacion(null);
      setMotivoRechazo('');
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al rechazar el pedido');
    } finally {
      setTransicionando(false);
    }
  };

  const handleRevertir = async () => {
    if (!motivoReversion.trim()) {
      alert('Escribí por qué deshacés la aprobación: la cátedra lo va a ver.');
      return;
    }
    if (!confirm(`¿Deshacer la aprobación del pedido #${detalle.id}?\n\nLa capacidad que había reservado vuelve a estar libre en el acto.`)) return;
    setTransicionando(true);
    try {
      const { data } = await revertirAprobacion(detalle.id, motivoReversion);
      const c = data.capacidad_liberada;
      setDetalle(data);
      setMotivoReversion('');
      fetchPedidos();
      alert(c && (c.vcpus || c.ram_mb || c.storage_gb)
        ? `Aprobación deshecha. Volvieron a estar libres ${c.vcpus} vCPU, ${c.ram_mb} MB de RAM y ${c.storage_gb} GB de disco.`
        : 'Aprobación deshecha. Esta renovación no tenía capacidad reservada, así que el saldo del clúster no cambia.');
    } catch (err) {
      // El backend ya redacta un mensaje distinto para cada uno de los cuatro
      // conflictos; volcarlo crudo perdería justamente eso.
      const d = err.response?.data?.detail;
      alert(d?.mensaje || (typeof d === 'string' ? d : 'Error al deshacer la aprobación'));
    } finally {
      setTransicionando(false);
    }
  };

  const handleTransicion = async (pedidoId, nuevoEstado) => {
    if (nuevoEstado === 'rechazado' && !motivoRechazo) {
      alert('Ingresá un motivo de rechazo');
      return;
    }
    setTransicionando(true);
    try {
      const { data } = await cambiarEstadoPedido(pedidoId, {
        nuevo_estado: nuevoEstado,
        comentario: comentario || null,
        motivo_rechazo: nuevoEstado === 'rechazado' ? motivoRechazo : null,
      });
      setDetalle(data);
      setComentario('');
      setMotivoRechazo('');
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al cambiar estado');
    } finally {
      setTransicionando(false);
    }
  };

  const handleDesplegar = async (pedidoId) => {
    if (!confirm(`¿Desplegar el pedido #${pedidoId} en Proxmox?`)) return;
    setTransicionando(true);
    try {
      await desplegarPedido(pedidoId);
      await verDetalle(pedidoId);
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al desplegar el pedido');
    } finally {
      setTransicionando(false);
    }
  };

  const handleReintentar = async (pedidoId) => {
    setTransicionando(true);
    try {
      await reintentarPedido(pedidoId);
      await verDetalle(pedidoId);
      fetchPedidos();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error al reintentar el despliegue');
    } finally {
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

      <div className="row between" style={{ marginBottom: 'var(--space-4)', alignItems: 'baseline' }}>
        <div className="section-label">Listado</div>
        <span className="section-count">{visibles.length} pedidos · {filtroLabel}</span>
      </div>

      {visibles.length === 0 ? (
        <div className="card">
          <Empty icon={<Search size={22} />}>
            {loading ? 'Cargando…' : 'Ningún pedido coincide con la búsqueda.'}
          </Empty>
        </div>
      ) : (
        <div className="col gap-3">
          {visibles.map((p) => {
            const tpl = templateDe(p.template_id);
            const cfg = ESTADO_CONFIG[p.estado] || {};
            const paso = cfg.paso ?? -1;
            const responsable = catedraResponsable(p.catedra_id);
            return (
              <div key={p.id} className="card" style={{ gap: 'var(--space-4)' }}>
                <div className="row between wrap" style={{ alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row wrap gap-2" style={{ alignItems: 'baseline' }}>
                      <span className="section-count">#{p.id}</span>
                      <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 'var(--font-heading-weight)', fontSize: 19 }}>
                        {templateNombre(p.template_id)}
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
                      {fueRevertido(p) ? 'Aprobación deshecha' : (cfg.label || p.estado)}
                    </StatusPill>
                    <button className="btn btn-ghost btn-sm" onClick={() => verDetalle(p.id)}>Ver detalle</button>
                  </div>
                </div>

                {paso >= 0 && paso < 3 && (
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

      {detalle && (
        <DetalleDialog
          detalle={detalle}
          isAdmin={isAdmin}
          templateDe={templateDe}
          templateNombre={templateNombre}
          catedraNombre={catedraNombre}
          formatDate={formatDate}
          onClose={cerrarDetalle}
          transicionando={transicionando}
          evaluacion={evaluacion}
          justificacion={justificacion}
          setJustificacion={setJustificacion}
          comentario={comentario}
          setComentario={setComentario}
          motivoRechazo={motivoRechazo}
          setMotivoRechazo={setMotivoRechazo}
          motivoReversion={motivoReversion}
          setMotivoReversion={setMotivoReversion}
          onRevertir={handleRevertir}
          onAprobar={handleAprobar}
          onAbrirAprobar={() => setModalAprobarAbierto(true)}
          onAbrirAjuste={() => setModalAjusteAbierto(true)}
          onAbrirReenviar={() => setModalReenviarAbierto(true)}
          onCancelarPedido={handleCancelarPedido}
          onRechazar={handleRechazar}
          onActualizarCapacidad={() => cargarEvaluacion(detalle.id)}
          onTransicion={handleTransicion}
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
        evaluacion={evaluacion}
        templates={templates}
        onClose={() => setModalAprobarAbierto(false)}
        onAprobado={(pActualizado) => {
          setDetalle(pActualizado);
          fetchPedidos();
        }}
        onRecargarCapacidad={() => detalle && cargarEvaluacion(detalle.id)}
      />

      <AjustePedidoModal
        open={modalAjusteAbierto}
        pedido={detalle}
        onClose={() => setModalAjusteAbierto(false)}
        onAjusteSolicitado={(pActualizado) => {
          setDetalle(pActualizado);
          fetchPedidos();
        }}
      />

      <ReenviarPedidoModal
        open={modalReenviarAbierto}
        pedido={detalle}
        onClose={() => setModalReenviarAbierto(false)}
        onReenviado={(pActualizado) => {
          setDetalle(pActualizado);
          fetchPedidos();
        }}
      />
    </div>
  );
}

function DetalleDialog({
  detalle, isAdmin, templateDe, templateNombre, catedraNombre, formatDate, onClose, transicionando,
  evaluacion, justificacion, setJustificacion, comentario, setComentario,
  motivoRechazo, setMotivoRechazo, onAprobar, onAbrirAprobar, onAbrirAjuste, onAbrirReenviar, onCancelarPedido, onRechazar, onActualizarCapacidad,
  onTransicion, onDesplegar, onReintentar, motivoReversion, setMotivoReversion, onRevertir,
}) {
  const [mostrarRechazo, setMostrarRechazo] = useState(false);
  const [historialAbierto, setHistorialAbierto] = useState(false);

  const cfg = ESTADO_CONFIG[detalle.estado] || {};
  const revertido = fueRevertido(detalle);
  const kind = revertido ? 'warn' : kindDe(detalle.estado);
  const transiciones = TRANSICIONES[detalle.estado] || [];
  const puedeRevertir = isAdmin && detalle.estado === 'aprobado' && !detalle.servicio_id;

  const parsed = parseDescripcionPedido(detalle);
  const tpl = templateDe ? templateDe(detalle.template_id) : null;
  const nombreCabecera = parsed.software || templateNombre(detalle.template_id);
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
              {revertido ? 'Aprobación deshecha' : (cfg.label || detalle.estado)}
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
            <strong>Observaciones de ajuste solicitadas:</strong>
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

      {/* 4. Panel de Decisión y Capacidad (Solo Admin en estado Solicitado) */}
      {isAdmin && detalle.estado === 'solicitado' && (
        <div className="decision-container">
          <div className="row between" style={{ alignItems: 'center' }}>
            <div className="section-label" style={{ margin: 0, fontSize: '0.84rem' }}>
              Evaluación de Capacidad y Decisión
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ fontSize: 12, padding: '4px 8px', height: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5 }}
              onClick={onActualizarCapacidad}
              disabled={transicionando}
              title="Recalcular disponibilidad actual del clúster"
            >
              <RefreshCw size={13} className={transicionando ? 'spin' : ''} />
              Actualizar capacidad
            </button>
          </div>

          {evaluacion ? (
            <>
              <PanelCapacidad evaluacion={evaluacion} />

              {evaluacion.excede_capacidad && (
                <div className="field" style={{ marginTop: 4 }}>
                  <label style={{ fontWeight: 600, color: 'var(--st-warn)', fontSize: 13 }}>
                    Justificación obligatoria (por exceder capacidad física):
                  </label>
                  <input
                    className="input"
                    placeholder="Ej: Aprobado excepcionalmente para inicio de ciclo lectivo..."
                    value={justificacion}
                    onChange={(e) => setJustificacion(e.target.value)}
                  />
                </div>
              )}

              {/* Barra de Acciones de Decisión */}
              {!mostrarRechazo ? (
                <div
                  className="row between wrap gap-2"
                  style={{ paddingTop: 'var(--space-2)', borderTop: '1px solid var(--color-divider)' }}
                >
                  <div className="row gap-2 wrap">
                    <button
                      className="btn btn-primary"
                      onClick={onAbrirAprobar}
                      disabled={transicionando}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    >
                      <CheckCircle2 size={15} />
                      Aprobar pedido (opciones y despliegue)…
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={onAprobar}
                      disabled={transicionando}
                      title="Aprobación inmediata con parámetros predeterminados"
                    >
                      Aprobación directa
                    </button>
                    <button
                      className="btn btn-warning"
                      onClick={onAbrirAjuste}
                      disabled={transicionando}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    >
                      Solicitar ajuste
                    </button>
                  </div>
                  <button
                    className="btn btn-ghost"
                    style={{ color: 'var(--st-bad)', borderColor: 'var(--st-bad-bd)', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    onClick={() => setMostrarRechazo(true)}
                    disabled={transicionando}
                  >
                    <XCircle size={15} />
                    Rechazar…
                  </button>
                </div>
              ) : (
                <div className="rechazo-panel">
                  <div className="row between mb-2">
                    <strong style={{ fontSize: 13, color: 'var(--st-bad)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <XCircle size={14} /> Motivo del rechazo (será visible por la cátedra):
                    </strong>
                    <button
                      type="button"
                      onClick={() => { setMostrarRechazo(false); setMotivoRechazo(''); }}
                      style={{ fontSize: 12, cursor: 'pointer', background: 'none', border: 'none', color: 'var(--text-soft)' }}
                    >
                      Cancelar
                    </button>
                  </div>
                  <textarea
                    className="input textarea"
                    rows={2}
                    placeholder="Describe el motivo del rechazo para que la cátedra pueda comprender y corregir..."
                    value={motivoRechazo}
                    onChange={(e) => setMotivoRechazo(e.target.value)}
                    autoFocus
                  />
                  <div className="row gap-2 mt-2" style={{ justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => { setMostrarRechazo(false); setMotivoRechazo(''); }}
                      disabled={transicionando}
                    >
                      Volver
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={onRechazar}
                      disabled={transicionando || !motivoRechazo.trim()}
                    >
                      Confirmar Rechazo
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="row gap-2" style={{ padding: '12px 0', color: 'var(--text-soft)' }}>
              <RefreshCw size={14} className="spin" />
              <span>Consultando la capacidad del clúster…</span>
            </div>
          )}
        </div>
      )}

      {/* 5. Acciones de Ajuste (cuando requiere ajuste) */}
      {detalle.estado === 'requiere_ajuste' && (
        <div className="decision-container">
          <div className="section-label" style={{ margin: 0, fontSize: '0.84rem' }}>Acciones de Ajuste</div>
          <p className="text-muted" style={{ margin: 0 }}>
            Este pedido requiere adecuación según las observaciones del administrador antes de poder ser evaluado nuevamente.
          </p>
          <div className="row gap-2 wrap" style={{ paddingTop: 'var(--space-2)' }}>
            <button className="btn btn-primary btn-sm" onClick={onAbrirReenviar} disabled={transicionando}>
              Modificar y reenviar solicitud
            </button>
            <button className="btn btn-danger btn-sm" onClick={() => onCancelarPedido(detalle.id)} disabled={transicionando}>
              Cancelar solicitud
            </button>
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
      {isAdmin && (transiciones.length > 0 || detalle.estado === 'aprobado' || detalle.estado === 'error') && (
        <div className="decision-container">
          <div className="section-label" style={{ margin: 0, fontSize: '0.84rem' }}>Acciones Operativas</div>
          {transiciones.length > 0 && (
            <>
              <div className="field" style={{ margin: 0 }}>
                <input className="input" placeholder="Comentario (opcional)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
              </div>
              {transiciones.includes('rechazado') && (
                <div className="field" style={{ margin: 0 }}>
                  <input className="input" placeholder="Motivo de rechazo (requerido si rechaza)" value={motivoRechazo} onChange={(e) => setMotivoRechazo(e.target.value)} />
                </div>
              )}
            </>
          )}
          <div className="row gap-2 wrap" style={{ paddingTop: 'var(--space-2)' }}>
            {detalle.estado === 'aprobado' && (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onDesplegar(detalle.id)}
                disabled={transicionando}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <Server size={14} /> Desplegar en Proxmox
              </button>
            )}
            {detalle.estado === 'error' && (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onReintentar(detalle.id)}
                disabled={transicionando}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <RefreshCw size={14} /> Reintentar despliegue
              </button>
            )}
            {transiciones.map((est) => (
              <button
                key={est}
                className={`btn btn-sm ${est === 'rechazado' ? 'btn-danger' : 'btn-primary'}`}
                onClick={() => onTransicion(detalle.id, est)}
                disabled={transicionando}
              >
                {ESTADO_CONFIG[est]?.label}
              </button>
            ))}
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
