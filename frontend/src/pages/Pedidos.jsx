import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Send, Info } from 'lucide-react';
import {
  getPedidos, getPedido, cambiarEstadoPedido, desplegarPedido, reintentarPedido,
  getTemplates, getCatedras, getCatedrasMias, evaluarPedido, aprobarPedido, rechazarPedido,
  revertirAprobacion,
} from '../services/api';
import PanelCapacidad from '../components/PanelCapacidad';
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

const tipoTemplate = (t) => (t?.tipo === 'qemu' ? 'Máquina Virtual' : t?.tipo === 'lxc' ? 'Contenedor LXC' : 'Servicio');

export default function Pedidos({ user }) {
  const navigate = useNavigate();
  const [pedidos, setPedidos] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [catedras, setCatedras] = useState([]);
  const [misCatedras, setMisCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [query, setQuery] = useState('');

  const [detalle, setDetalle] = useState(null);
  const [transicionando, setTransicionando] = useState(false);
  const [comentario, setComentario] = useState('');
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [evaluacion, setEvaluacion] = useState(null);
  const [justificacion, setJustificacion] = useState('');
  const [motivoReversion, setMotivoReversion] = useState('');

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
  const templateNombre = (id) => templateDe(id)?.nombre || `Template #${id}`;
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
      [`#${p.id}`, templateNombre(p.template_id), catedraNombre(p.catedra_id), ESTADO_CONFIG[p.estado]?.label]
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
        <button className="btn-send" onClick={() => navigate('/catalogo')}>
          <Send size={17} />
          <span>Nuevo pedido</span>
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
                      <span className="tag">{tipoTemplate(tpl)}</span>
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
          onRechazar={handleRechazar}
          onActualizarCapacidad={() => cargarEvaluacion(detalle.id)}
          onTransicion={handleTransicion}
          onDesplegar={handleDesplegar}
          onReintentar={handleReintentar}
        />
      )}
    </div>
  );
}

function DetalleDialog({
  detalle, isAdmin, templateNombre, catedraNombre, formatDate, onClose, transicionando,
  evaluacion, justificacion, setJustificacion, comentario, setComentario,
  motivoRechazo, setMotivoRechazo, onAprobar, onRechazar, onActualizarCapacidad,
  onTransicion, onDesplegar, onReintentar, motivoReversion, setMotivoReversion, onRevertir,
}) {
  const cfg = ESTADO_CONFIG[detalle.estado] || {};
  const revertido = fueRevertido(detalle);
  const kind = revertido ? 'warn' : kindDe(detalle.estado);
  const transiciones = TRANSICIONES[detalle.estado] || [];
  // Solo se deshace una aprobación que todavía no se desplegó: en cuanto hay
  // servicio, la vuelta atrás es una baja, no una decisión administrativa.
  const puedeRevertir = isAdmin && detalle.estado === 'aprobado' && !detalle.servicio_id;

  return (
    <Dialog
      wide
      title={`Pedido #${detalle.id} — ${templateNombre(detalle.template_id)}`}
      onClose={onClose}
    >
      <div className="grid cols-3 mb-4">
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>Estado</div>
          <StatusPill kind={kind}>{revertido ? 'Aprobación deshecha' : (cfg.label || detalle.estado)}</StatusPill>
        </div>
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>Cátedra</div>
          <div style={{ fontSize: 14 }}>{catedraNombre(detalle.catedra_id)}</div>
        </div>
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>Creado</div>
          <div style={{ fontSize: 14 }}>{formatDate(detalle.created_at)}</div>
        </div>
      </div>

      {detalle.motivo_rechazo && (
        <div className={`callout ${revertido ? 'warn' : 'bad'}`} style={{ marginBottom: 'var(--space-4)' }}>
          <Info size={15} />
          {revertido ? (
            <span>
              <strong>Este pedido estaba aprobado y la aprobación se deshizo.</strong>{' '}
              {motivoLimpio(detalle.motivo_rechazo)}{' '}
              La capacidad que tenía reservada volvió a estar libre, y se puede volver a pedir lo mismo
              cuando haga falta.
            </span>
          ) : (
            <span><strong>Motivo de rechazo:</strong> {detalle.motivo_rechazo}</span>
          )}
        </div>
      )}

      <div className="mb-4">
        <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Historial de estados</div>
        <div className="col gap-2">
          {detalle.historial?.map((h) => (
            <div key={h.id} className="row between" style={{ paddingLeft: 12, borderLeft: '2px solid var(--color-divider)' }}>
              <div style={{ fontSize: 12 }}>
                <span>{describirEntrada(h)}</span>
                {h.usuario_id == null && <span className="tag neutral" style={{ marginLeft: 6 }}>Automático</span>}
                {h.comentario && <span style={{ color: 'var(--text-soft)' }}> · {h.comentario}</span>}
              </div>
              <span className="nowrap" style={{ fontSize: 11, color: 'var(--text-faint)' }}>{formatDate(h.created_at)}</span>
            </div>
          ))}
        </div>
      </div>

      {isAdmin && detalle.estado === 'solicitado' && (
        <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 'var(--space-4)' }}>
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Decisión sobre este pedido</div>
          {evaluacion ? (
            <>
              <PanelCapacidad evaluacion={evaluacion} />
              {evaluacion.excede_capacidad && (
                <div className="field">
                  <label>Justificación (obligatoria para aprobar por encima de la capacidad)</label>
                  <input
                    className="input"
                    placeholder="Ej: se apaga el laboratorio viejo esta semana"
                    value={justificacion}
                    onChange={(e) => setJustificacion(e.target.value)}
                  />
                </div>
              )}
              <div className="field">
                <label>Motivo (si rechazás, la cátedra lo va a ver)</label>
                <input
                  className="input"
                  placeholder="Motivo del rechazo"
                  value={motivoRechazo}
                  onChange={(e) => setMotivoRechazo(e.target.value)}
                />
              </div>
              <div className="row gap-2 wrap">
                <button className="btn btn-primary btn-sm" onClick={onAprobar} disabled={transicionando}>
                  Aprobar y reservar
                </button>
                <button className="btn btn-danger btn-sm" onClick={onRechazar} disabled={transicionando}>
                  Rechazar
                </button>
                <button className="btn btn-secondary btn-sm" onClick={onActualizarCapacidad} disabled={transicionando}>
                  Actualizar capacidad
                </button>
              </div>
            </>
          ) : (
            <p className="text-muted">Consultando la capacidad del clúster…</p>
          )}
        </div>
      )}

      {puedeRevertir && (
        <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Deshacer la aprobación</div>
          <p className="text-muted" style={{ marginBottom: 'var(--space-2)' }}>
            Libera en el acto la capacidad que este pedido tiene reservada, sin esperar a que la
            reserva venza sola. La cátedra ve el motivo y puede volver a pedir lo mismo.
          </p>
          <div className="field">
            <label>Motivo (la cátedra lo va a ver)</label>
            <input
              className="input"
              placeholder="Ej: aprobé el template grande por error"
              value={motivoReversion}
              onChange={(e) => setMotivoReversion(e.target.value)}
            />
          </div>
          <button className="btn btn-danger btn-sm" onClick={onRevertir} disabled={transicionando}>
            Deshacer aprobación y liberar capacidad
          </button>
        </div>
      )}

      {isAdmin && (transiciones.length > 0 || detalle.estado === 'aprobado' || detalle.estado === 'error') && (
        <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Acciones</div>
          {transiciones.length > 0 && (
            <>
              <div className="field">
                <input className="input" placeholder="Comentario (opcional)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
              </div>
              {transiciones.includes('rechazado') && (
                <div className="field">
                  <input className="input" placeholder="Motivo de rechazo (requerido si rechaza)" value={motivoRechazo} onChange={(e) => setMotivoRechazo(e.target.value)} />
                </div>
              )}
            </>
          )}
          <div className="row gap-2 wrap">
            {detalle.estado === 'aprobado' && (
              <button className="btn btn-primary btn-sm" onClick={() => onDesplegar(detalle.id)} disabled={transicionando}>Desplegar</button>
            )}
            {detalle.estado === 'error' && (
              <button className="btn btn-primary btn-sm" onClick={() => onReintentar(detalle.id)} disabled={transicionando}>Reintentar despliegue</button>
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
    </Dialog>
  );
}
