import { Globe, Server, Building2, Boxes, RefreshCw } from 'lucide-react';
import { getCatedras, getProxmoxStatus, getProxmoxResources, getProxmoxStorage } from '../services/api';
import PanelCatedra from '../components/PanelCatedra';
import { PageHead, StatusPill, Empty } from '../components/ui';
import useRemoteData from '../hooks/useRemoteData';
import EstadoConsulta from '../components/EstadoConsulta';

const EMPTY = [];

export default function Dashboard({ user }) {
  const isAdmin = user?.rol === 'admin';
  const scope = `${user?.id || ''}:${user?.rol || ''}`;
  const options = { enabled: isAdmin, refreshMs: 30000 };
  const categories = useRemoteData(getCatedras, { ...options, key: `inicio-catedras:${scope}`, errorMessage: 'No se pudieron consultar las cátedras.' });
  const cluster = useRemoteData(getProxmoxStatus, { ...options, key: `inicio-cluster:${scope}`, errorMessage: 'No se pudo consultar el clúster Proxmox.' });
  const guests = useRemoteData(getProxmoxResources, { ...options, key: `inicio-recursos:${scope}`, errorMessage: 'No se pudieron consultar los recursos de Proxmox.' });
  const storage = useRemoteData(getProxmoxStorage, { ...options, key: `inicio-storage:${scope}`, errorMessage: 'No se pudo consultar el almacenamiento de Proxmox.' });
  const catedras = categories.data || EMPTY;
  const proxmox = cluster.data;
  const resources = guests.data || EMPTY;
  const storages = storage.data || EMPTY;
  const loading = [categories, cluster, guests, storage].some((remote) => remote.loading);
  const refresh = () => Promise.all([categories.reload(), cluster.reload(), guests.reload(), storage.reload()]);
  // A shared pool is visible from multiple nodes, but has one physical capacity.
  const pools = new Map();
  for (const row of storages) {
    const key = row.compartido ? `shared:${row.storage}` : `node:${row.node}:${row.storage}`;
    const prior = pools.get(key);
    if (!prior) pools.set(key, { ...row, key, nodes: [row.node] });
    else {
      prior.nodes.push(row.node);
      prior.usado_bytes = Math.max(prior.usado_bytes, row.usado_bytes);
      prior.total_bytes = Math.min(prior.total_bytes, row.total_bytes);
    }
  }
  const storagePools = [...pools.values()];

  if (!isAdmin) return <PanelCatedra user={user} />;

  // Proxmox informa en potencias de 1024 y rotula GiB/MiB: acá se hace igual.
  const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const gib = bytes / 1024 ** 3;
    return gib >= 1 ? `${gib.toFixed(1)} GiB` : `${(bytes / 1024 ** 2).toFixed(0)} MiB`;
  };
  const pct = (u, t) => (t > 0 ? (u / t) * 100 : 0);
  const barClass = (p) => (p > 85 ? 'bad' : p > 60 ? 'warn' : 'ok');

  const conectado = proxmox?.status === 'connected';
  const nContenedores = resources.filter((r) => r.type === 'lxc' || r.type === 'qemu').length;
  const catedrasActivas = catedras.filter((c) => c.activa).length;

  return (
    <div className="fade-in">
      <PageHead title="Inicio" subtitle="Vista general — clúster Proxmox VE">
        <button className="btn btn-secondary" disabled={loading} onClick={refresh}><RefreshCw size={16}/>Actualizar estado</button>
      </PageHead>
      <EstadoConsulta remote={cluster} nombre="clúster"/>
      <EstadoConsulta remote={guests} nombre="recursos"/>
      <EstadoConsulta remote={storage} nombre="almacenamiento"/>
      <EstadoConsulta remote={categories} nombre="cátedras"/>
      {cluster.updatedAt && <p className="card-meta">Última consulta de Proxmox: {cluster.updatedAt.toLocaleTimeString('es-AR')}. Se actualiza cada 30 segundos mientras esta pantalla está visible.</p>}

      <div className="grid cols-4 mb-6">
        <div className="stat stat--accent">
          <div className="stat__kicker"><span className="stat__glyph"><Globe size={16} /></span> Clúster</div>
          <div><StatusPill kind={cluster.error ? 'warn' : conectado ? 'ok' : 'off'}>{cluster.error ? 'Sin confirmar' : cluster.loading && !proxmox ? 'Consultando' : conectado ? 'Conectado' : 'Desconectado'}</StatusPill></div>
          <div className="stat__meta">Proxmox VE</div>
        </div>
        <div className="stat stat--ok">
          <div className="stat__kicker"><span className="stat__glyph ok"><Server size={16} /></span> Nodos</div>
          <div className="stat__value">{proxmox ? proxmox.nodes?.length : '—'}</div>
          <div className="stat__meta">en el clúster</div>
        </div>
        <div className="stat stat--accent">
          <div className="stat__kicker"><span className="stat__glyph"><Building2 size={16} /></span> Cátedras</div>
          <div className="stat__value">{categories.data ? <>{catedrasActivas} <small>/ {catedras.length}</small></> : '—'}</div>
          <div className="stat__meta">activas</div>
        </div>
        <div className="stat stat--warn">
          <div className="stat__kicker"><span className="stat__glyph warn"><Boxes size={16} /></span> Recursos</div>
          <div className="stat__value">{guests.data ? nContenedores : '—'}</div>
          <div className="stat__meta">VMs / contenedores</div>
        </div>
      </div>

      {proxmox?.nodes?.map((node) => {
        const cpuP = node.cpu * 100;
        const ramP = pct(node.mem, node.maxmem);
        const diskP = pct(node.disk, node.maxdisk);
        return (
          <div className="card mb-4" key={node.node}>
            <div className="card-header">
              <div className="card-title">{node.node}</div>
              <StatusPill kind={node.status === 'online' ? 'ok' : 'bad'}>{node.status}</StatusPill>
            </div>
            <div className="grid cols-3">
              {[
                { label: `CPU · ${node.maxcpu} cores`, p: cpuP, txt: `${cpuP.toFixed(1)} %` },
                { label: `RAM · ${formatBytes(node.maxmem)}`, p: ramP, txt: `${formatBytes(node.mem)} en uso` },
                { label: `Disco del sistema · ${formatBytes(node.maxdisk)}`, p: diskP, txt: `${formatBytes(node.disk)} en uso` },
              ].map((m) => (
                <div key={m.label}>
                  <div className="card-meta" style={{ marginBottom: 6 }}>{m.label}</div>
                  <div className="meter"><div className={`meter__fill ${barClass(m.p)}`} style={{ width: `${m.p}%` }} /></div>
                  <div className="card-meta tabnum" style={{ marginTop: 4 }}>{m.txt}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {storages.length > 0 && (
        <div className="card mb-4">
          <div className="card-header">
            <div className="card-title">Almacenamiento</div>
            <span className="section-count">
              {formatBytes(storagePools.reduce((a, s) => a + s.usado_bytes, 0))} de {formatBytes(storagePools.reduce((a, s) => a + s.total_bytes, 0))}
            </span>
          </div>
          <div className="grid cols-3">
            {storagePools.map((s) => {
              const p = pct(s.usado_bytes, s.total_bytes);
              return (
                <div key={s.key}>
                  <div className="card-meta" style={{ marginBottom: 6 }}>
                    {s.storage}
                    {s.compartido && <span className="tag" style={{ marginLeft: 6 }}>compartido</span>}
                    {s.aloja_contenedores && <span className="tag" style={{ marginLeft: 6 }}>contenedores</span>}
                  </div>
                  <div className="meter"><div className={`meter__fill ${barClass(p)}`} style={{ width: `${p}%` }} /></div>
                  <div className="card-meta tabnum" style={{ marginTop: 4 }}>
                    {formatBytes(s.usado_bytes)} de {formatBytes(s.total_bytes)} ({p.toFixed(0)} %)
                  </div>
                  <div className="card-meta" style={{ marginTop: 2, opacity: 0.7 }}>{s.tipo} · {s.contenido} · nodos {s.nodes.join(', ')}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && !conectado && (
        <div className="card mb-4">
          <Empty icon={<Server size={22} />} hint="Revisá la conexión, el certificado y los permisos de la cuenta de Proxmox.">
            No se pudo conectar con Proxmox VE.
          </Empty>
        </div>
      )}
    </div>
  );
}
