import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Square, CalendarClock, Send } from 'lucide-react';
import {
  getPedidos, listarServicios, getCatedra, getCatedrasMias, getTemplates,
  iniciarServicio, detenerServicio, reactivarServicio, renovarServicio,
} from '../services/api';
import { ESTADO_PEDIDO_CONFIG, ESTADO_SERVICIO_SIMPLE } from '../constants/estados';
import { PageHead, StatusPill, Empty } from './ui';

const INTERVALO_REFRESCO_MS = 10000;
const PILL_KIND = { info: 'accent', success: 'ok', warning: 'warn', error: 'bad', neutral: 'off' };

export default function PanelCatedra({ user }) {
  const navigate = useNavigate();
  const [pedidos, setPedidos] = useState([]);
  const [servicios, setServicios] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [catedra, setCatedra] = useState(null);
  const [misCatedras, setMisCatedras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accionando, setAccionando] = useState(null);
  const accionandoRef = useRef(null);

  const cargarServicios = async () => {
    try {
      const { data } = await listarServicios();
      setServicios(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const r = await Promise.allSettled([getPedidos(), listarServicios(), getTemplates(), getCatedrasMias()]);
        if (r[0].status === 'fulfilled') setPedidos(r[0].value.data);
        if (r[1].status === 'fulfilled') setServicios(r[1].value.data);
        if (r[2].status === 'fulfilled') setTemplates(r[2].value.data);
        if (r[3].status === 'fulfilled') {
          const mias = r[3].value.data;
          setMisCatedras(mias);
          const detalles = await Promise.allSettled(mias.map((c) => getCatedra(c.id)));
          const total = detalles.reduce((acc, d) => {
            if (d.status !== 'fulfilled') return acc;
            const v = d.value.data;
            return {
              vcpus_en_uso: acc.vcpus_en_uso + v.vcpus_en_uso,
              ram_en_uso_mb: acc.ram_en_uso_mb + v.ram_en_uso_mb,
              storage_en_uso_gb: acc.storage_en_uso_gb + v.storage_en_uso_gb,
              servicios_activos: acc.servicios_activos + v.servicios_activos,
            };
          }, { vcpus_en_uso: 0, ram_en_uso_mb: 0, storage_en_uso_gb: 0, servicios_activos: 0 });
          setCatedra(mias.length > 0 ? total : null);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    })();

    const timer = setInterval(() => { if (!accionandoRef.current) cargarServicios(); }, INTERVALO_REFRESCO_MS);
    return () => clearInterval(timer);
  }, []);

  const ejecutar = async (id, accion, llamada, manejoError) => {
    accionandoRef.current = `${accion}-${id}`;
    setAccionando(`${accion}-${id}`);
    try {
      await llamada(id);
    } catch (err) {
      if (manejoError) manejoError(err);
      else alert(err.response?.data?.detail || err.message);
    } finally {
      await cargarServicios();
      accionandoRef.current = null;
      setAccionando(null);
    }
  };

  const encender = (id) => ejecutar(id, 'start', iniciarServicio);
  const apagar = (id) => { if (confirm('¿Apagar el servicio?')) ejecutar(id, 'stop', detenerServicio); };
  const reactivar = (id) => ejecutar(id, 'reactivar', reactivarServicio, (err) => {
    const d = err.response?.data?.detail;
    alert(d?.codigo === 'sin_capacidad' ? d.mensaje : (typeof d === 'string' ? d : err.message));
  });
  const renovar = (s) => {
    if (!confirm(
      `Vas a pedir que extiendan la fecha de ${s.hostname || `servicio #${s.id}`}.\n\n` +
      'La solicitud queda pendiente de aprobación. Mientras tanto el servicio sigue funcionando.'
    )) return;
    ejecutar(s.id, 'renovar', async () => {
      await renovarServicio(s.id);
      alert('Pedido de renovación enviado. Vas a ver el estado en "Mis Pedidos".');
    });
  };

  const DIAS_PARA_AVISAR = 30;
  const venceProximamente = (iso) => {
    if (!iso) return false;
    return (new Date(iso) - new Date()) / 86400000 <= DIAS_PARA_AVISAR;
  };

  const pedidosRecientes = [...pedidos]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5);

  const templateNombre = (id) => templates.find((t) => t.id === id)?.nombre || `Template #${id}`;
  const fmt = (iso) => iso
    ? new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '—';

  const irACatalogo = () => navigate('/catalogo');
  const sinDatos = !loading && pedidos.length === 0 && servicios.length === 0;

  const consumoItems = catedra ? [
    { label: 'vCPUs en uso', valor: `${catedra.vcpus_en_uso}` },
    { label: 'RAM en uso', valor: `${catedra.ram_en_uso_mb} MB` },
    { label: 'Disco en uso', valor: `${catedra.storage_en_uso_gb} GB` },
    { label: 'Servicios activos', valor: `${catedra.servicios_activos}` },
  ] : [];

  const subtitulo = misCatedras.length
    ? `${misCatedras.map((c) => c.nombre).join(' · ')} — ${user?.nombre || ''}`
    : `Bienvenido, ${user?.nombre || ''}.`;

  return (
    <div className="fade-in">
      <PageHead title="Inicio" subtitle={subtitulo}>
        {misCatedras.length > 0 && (
          <button className="btn-send" onClick={irACatalogo}>
            <Send size={17} /><span>Nuevo pedido</span>
          </button>
        )}
      </PageHead>

      {loading ? (
        <p className="text-muted">Cargando…</p>
      ) : misCatedras.length === 0 ? (
        <div className="card">
          <Empty
            icon={<Send size={22} />}
            hint="Pedile a un administrador que te asigne una o que la cree: sin cátedra no se pueden solicitar servicios."
          >
            Todavía no tenés ninguna cátedra asignada.
          </Empty>
        </div>
      ) : sinDatos ? (
        <div className="card">
          <Empty icon={<Send size={22} />}>
            Todavía no pediste ningún servicio.
            <div style={{ marginTop: 'var(--space-3)' }}>
              <button className="btn btn-primary" onClick={irACatalogo}>Ir al catálogo</button>
            </div>
          </Empty>
        </div>
      ) : (
        <>
          {catedra && (
            <div className="grid cols-4 mb-6">
              {consumoItems.map((item, i) => (
                <div className={`stat stat--${['accent', 'ok', 'warn', 'accent'][i]}`} key={item.label}>
                  <div className="stat__kicker">{item.label}</div>
                  <div className="stat__value tabnum">{item.valor}</div>
                </div>
              ))}
            </div>
          )}

          <div className="card mb-4">
            <div className="card-header">
              <div className="card-title">Mis Servicios</div>
              <button className="btn btn-secondary btn-sm" onClick={cargarServicios}>Actualizar</button>
            </div>
            {servicios.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead><tr><th>Servicio</th><th>Estado</th><th className="right">Acciones</th></tr></thead>
                  <tbody>
                    {servicios.map((s) => {
                      const cfg = ESTADO_SERVICIO_SIMPLE[s.estado] || { label: s.estado, badge: 'neutral' };
                      const corriendo = s.estado === 'running';
                      const busy = (k) => accionando === `${k}-${s.id}`;
                      return (
                        <tr key={s.id}>
                          <td className="cell-strong">{s.hostname || `Servicio #${s.id}`}</td>
                          <td>
                            <div className="col gap-1" style={{ alignItems: 'flex-start' }}>
                              <StatusPill kind={PILL_KIND[cfg.badge] || 'off'}>{cfg.label}</StatusPill>
                              {s.existe_en_proxmox === false ? (
                                <span className="card-meta" style={{ color: 'var(--st-bad)' }}>ya no existe en el servidor</span>
                              ) : s.estado_sincronizado === false && (
                                <span className="card-meta">sin confirmar</span>
                              )}
                              {s.pausado_auto_at && (
                                <span className="card-meta">lo pausamos porque no se usaba. Tus datos están intactos; el disco sigue reservado.</span>
                              )}
                              {!s.pausado_auto_at && s.pausa_programada_at && (
                                <span className="card-meta" style={{ color: 'var(--st-warn)' }}>
                                  si no se usa, lo vamos a pausar el {new Date(s.pausa_programada_at).toLocaleDateString('es-AR')}. Usarlo antes cancela la pausa.
                                </span>
                              )}
                              {s.vence_at && (
                                <span className="card-meta" style={{ color: venceProximamente(s.vence_at) ? 'var(--st-warn)' : undefined }}>
                                  disponible hasta el {new Date(s.vence_at).toLocaleDateString('es-AR')}
                                  {venceProximamente(s.vence_at) && ' — pedí la renovación si lo seguís necesitando'}
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <div className="row gap-1" style={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                              {s.existe_en_proxmox === false ? (
                                <span className="card-meta">Avisá al administrador</span>
                              ) : corriendo ? (
                                <>
                                  <button className="pill-btn warn" onClick={() => apagar(s.id)} disabled={busy('stop')}>
                                    <Square size={12} /> Apagar
                                  </button>
                                  {venceProximamente(s.vence_at) && (
                                    <button className="pill-btn" onClick={() => renovar(s)} disabled={busy('renovar')}>
                                      <CalendarClock size={13} /> Renovar
                                    </button>
                                  )}
                                </>
                              ) : s.pausado_auto_at ? (
                                <>
                                  <button className="pill-btn ok" onClick={() => reactivar(s.id)} disabled={busy('reactivar')}>
                                    <Play size={13} /> Reactivar
                                  </button>
                                  {venceProximamente(s.vence_at) && (
                                    <button className="pill-btn" onClick={() => renovar(s)} disabled={busy('renovar')}>
                                      <CalendarClock size={13} /> Renovar
                                    </button>
                                  )}
                                </>
                              ) : (
                                <button className="pill-btn ok" onClick={() => encender(s.id)} disabled={busy('start')}>
                                  <Play size={13} /> Encender
                                </button>
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
              <Empty icon={<Send size={20} />}>Todavía no tenés servicios desplegados.</Empty>
            )}
          </div>

          <div className="card">
            <div className="card-title">Mis Pedidos Recientes</div>
            {pedidosRecientes.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead><tr><th>#</th><th>Servicio pedido</th><th>Estado</th><th>Fecha</th></tr></thead>
                  <tbody>
                    {pedidosRecientes.map((p) => {
                      const cfg = ESTADO_PEDIDO_CONFIG[p.estado] || { label: p.estado, badge: 'neutral' };
                      return (
                        <tr key={p.id}>
                          <td className="cell-strong tabnum">{p.id}</td>
                          <td>{templateNombre(p.template_id)}</td>
                          <td><StatusPill kind={PILL_KIND[cfg.badge] || 'off'}>{cfg.label}</StatusPill></td>
                          <td className="tabnum">{fmt(p.created_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty icon={<Send size={20} />}>No hay pedidos recientes.</Empty>
            )}
          </div>
        </>
      )}
    </div>
  );
}
