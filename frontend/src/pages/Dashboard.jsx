import { useState, useEffect } from 'react';
import { Globe, Server, Building2, Boxes } from 'lucide-react';
import { getCatedras, getProxmoxStatus, getProxmoxResources, getProxmoxStorage } from '../services/api';
import PanelCatedra from '../components/PanelCatedra';
import { PageHead, StatusPill, Empty } from '../components/ui';

export default function Dashboard({ user }) {
  const [catedras, setCatedras] = useState([]);
  const [proxmox, setProxmox] = useState(null);
  const [resources, setResources] = useState([]);
  const [storages, setStorages] = useState([]);
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.rol === 'admin';

  useEffect(() => {
    if (!isAdmin) return;
    (async () => {
      try {
        const r = await Promise.allSettled([
          getCatedras(), getProxmoxStatus(), getProxmoxResources(), getProxmoxStorage(),
        ]);
        if (r[0].status === 'fulfilled') setCatedras(r[0].value.data);
        if (r[1].status === 'fulfilled') setProxmox(r[1].value.data);
        if (r[2].status === 'fulfilled') setResources(r[2].value.data);
        if (r[3].status === 'fulfilled') setStorages(r[3].value.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    })();
  }, [isAdmin]);

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
      <PageHead title="Inicio" subtitle="Vista general — clúster Proxmox VE" />

      <div className="grid cols-4 mb-6">
        <div className="stat stat--accent">
          <div className="stat__kicker"><span className="stat__glyph"><Globe size={16} /></span> Clúster</div>
          <div><StatusPill kind={conectado ? 'ok' : 'bad'}>{conectado ? 'Conectado' : 'Desconectado'}</StatusPill></div>
          <div className="stat__meta">Proxmox VE</div>
        </div>
        <div className="stat stat--ok">
          <div className="stat__kicker"><span className="stat__glyph ok"><Server size={16} /></span> Nodos</div>
          <div className="stat__value">{loading ? '—' : proxmox?.nodes?.length || 0}</div>
          <div className="stat__meta">en el clúster</div>
        </div>
        <div className="stat stat--accent">
          <div className="stat__kicker"><span className="stat__glyph"><Building2 size={16} /></span> Cátedras</div>
          <div className="stat__value">{catedrasActivas} <small>/ {catedras.length}</small></div>
          <div className="stat__meta">activas</div>
        </div>
        <div className="stat stat--warn">
          <div className="stat__kicker"><span className="stat__glyph warn"><Boxes size={16} /></span> Recursos</div>
          <div className="stat__value">{loading ? '—' : nContenedores}</div>
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
              {formatBytes(storages.reduce((a, s) => a + s.usado_bytes, 0))} de {formatBytes(storages.reduce((a, s) => a + s.total_bytes, 0))}
            </span>
          </div>
          <div className="grid cols-3">
            {storages.map((s) => {
              const p = pct(s.usado_bytes, s.total_bytes);
              return (
                <div key={`${s.node}-${s.storage}`}>
                  <div className="card-meta" style={{ marginBottom: 6 }}>
                    {s.storage}
                    {s.aloja_contenedores && <span className="tag" style={{ marginLeft: 6 }}>contenedores</span>}
                  </div>
                  <div className="meter"><div className={`meter__fill ${barClass(p)}`} style={{ width: `${p}%` }} /></div>
                  <div className="card-meta tabnum" style={{ marginTop: 4 }}>
                    {formatBytes(s.usado_bytes)} de {formatBytes(s.total_bytes)} ({p.toFixed(0)} %)
                  </div>
                  <div className="card-meta" style={{ marginTop: 2, opacity: 0.7 }}>{s.tipo} · {s.contenido} · nodo {s.node}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && !conectado && (
        <div className="card mb-4">
          <Empty icon={<Server size={22} />} hint="Verificá que la VM de Proxmox esté encendida.">
            No se pudo conectar con Proxmox VE.
          </Empty>
        </div>
      )}
    </div>
  );
}
