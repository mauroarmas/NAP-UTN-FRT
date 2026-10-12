import { Cpu, HardDrive, Zap, CheckCircle2, AlertTriangle } from 'lucide-react';

/**
 * Panel moderno de proyección de capacidad del clúster para la evaluación administrativa.
 * Muestra el balance libre actual, requerimientos solicitados y proyección si se aprueba.
 */

const MAGNITUDES = [
  { clave: 'vcpus', etiqueta: 'vCPUs', icon: Cpu },
  { clave: 'ram_mb', etiqueta: 'RAM', icon: Zap },
  { clave: 'storage_gb', etiqueta: 'Disco', icon: HardDrive },
];

function formatValor(clave, val) {
  if (val == null) return '0';
  if (clave === 'ram_mb') {
    if (Math.abs(val) >= 1024) {
      const gb = val / 1024;
      const gbStr = gb % 1 === 0 ? gb.toString() : gb.toFixed(1);
      return `${gbStr} GB`;
    }
    return `${val} MB`;
  }
  if (clave === 'vcpus') return `${val} vCPU`;
  if (clave === 'storage_gb') return `${val} GB`;
  return String(val);
}

export default function PanelCapacidad({ evaluacion }) {
  if (!evaluacion) return null;

  const {
    capacidad,
    costo,
    libre_si_aprueba: libreDespues,
    excede_capacidad: excede,
    consumo_catedra: consumoCatedra,
    pedido,
  } = evaluacion;

  return (
    <div className="panel-capacidad-moderno">
      {/* Estado global de capacidad */}
      <div className={`capacidad-status-pill ${excede ? 'warn' : 'ok'}`}>
        {excede ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
        <span>
          {excede
            ? 'Atención: Este pedido excede la capacidad disponible. Se requerirá justificación administrativa para aprobarlo.'
            : 'El clúster dispone de recursos libres para absorber este despliegue.'}
        </span>
      </div>

      {/* Grid de métricas clave */}
      <div className="capacidad-cards-grid">
        {MAGNITUDES.map(({ clave, etiqueta, icon: Icon }) => {
          const quedaria = libreDespues[clave];
          const libre = capacidad.libre[clave];
          const pide = costo[clave];
          const insuficiente = quedaria < 0;

          return (
            <div
              key={clave}
              className={`capacidad-metric-card ${insuficiente ? 'is-excedido' : ''}`}
            >
              <div className="capacidad-metric-header">
                <span className="capacidad-metric-title">
                  <Icon size={14} /> {etiqueta}
                </span>
                <span
                  className={`tag ${insuficiente ? 'bad' : 'ok'}`}
                  style={{ fontSize: 10, padding: '1px 6px' }}
                >
                  {insuficiente ? 'Déficit' : 'Suficiente'}
                </span>
              </div>

              <div className="capacidad-metric-body">
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase' }}>
                    Quedarían libres
                  </div>
                  <div
                    className="capacidad-metric-value"
                    style={{ color: insuficiente ? 'var(--st-bad)' : 'var(--text-strong)' }}
                  >
                    {formatValor(clave, quedaria)}
                  </div>
                </div>
              </div>

              <div className="capacidad-metric-footer">
                <div>Pide: <strong>{formatValor(clave, pide)}</strong></div>
                <div>Libre actual: <strong>{formatValor(clave, libre)}</strong></div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Información contextual del clúster y cátedra */}
      <div className="capacidad-footer-meta">
        <div>
          <strong>Cátedra {pedido?.catedra?.nombre || ''}:</strong>{' '}
          Uso actual de {consumoCatedra.vcpus} vCPU · {formatValor('ram_mb', consumoCatedra.ram_mb)} · {consumoCatedra.storage_gb} GB en despliegues activos.
        </div>
        <div>
          <strong>Total físico clúster:</strong> {capacidad.fisica.vcpus} vCPU ({capacidad.reservado.vcpus} reservados) · {formatValor('ram_mb', capacidad.fisica.ram_mb)} ({formatValor('ram_mb', capacidad.reservado.ram_mb)} reservados por pedidos no desplegados).
        </div>
        {capacidad.ram_en_riesgo_mb > 0 && (
          <div style={{ color: 'var(--st-warn)' }}>
            ⚠️ {formatValor('ram_mb', capacidad.ram_en_riesgo_mb)} de RAM en riesgo si se reactivaran servicios en pausa a la vez.
          </div>
        )}
      </div>
    </div>
  );
}
