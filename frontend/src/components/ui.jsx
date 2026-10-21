import { useId, useLayoutEffect, useRef } from 'react';
import { activateModal } from '../utils/modalFocus';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

// Piezas compartidas del sistema de diseño. Cada una es fina a propósito:
// envuelve una convención de marcado, no una abstracción.

export function PageHead({ kicker, title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>
        {kicker && <div className="page-head__kicker">{kicker}</div>}
        <h1 className="page-title" tabIndex={-1}>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {children && <div className="row wrap">{children}</div>}
    </div>
  );
}

// Pill de estado. `kind`: ok | warn | bad | off | accent.
const PILL = {
  ok:     { fg: 'var(--st-ok)',           bg: 'var(--st-ok-bg)',   bd: 'var(--st-ok-bd)',   dot: 'var(--st-ok)' },
  warn:   { fg: 'var(--st-warn)',         bg: 'var(--st-warn-bg)', bd: 'var(--st-warn-bd)', dot: 'var(--st-warn)' },
  bad:    { fg: 'var(--st-bad)',          bg: 'var(--st-bad-bg)',  bd: 'var(--st-bad-bd)',  dot: 'var(--st-bad)' },
  off:    { fg: 'var(--st-off)',          bg: 'var(--st-off-bg)',  bd: 'var(--st-off-bd)',  dot: 'var(--st-off)' },
  accent: { fg: 'var(--color-accent-700)', bg: 'var(--accent-tint)', bd: 'var(--accent-tint-bd)', dot: 'var(--color-accent)' },
};

export function StatusPill({ kind = 'off', children, glow = true }) {
  const c = PILL[kind] || PILL.off;
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '3px 10px', borderRadius: 'var(--radius-pill)',
        fontSize: 11, fontWeight: 600, letterSpacing: '0.02em', whiteSpace: 'nowrap',
        color: c.fg, background: c.bg, border: `1px solid ${c.bd}`,
      }}
    >
      <span style={{
        width: 6, height: 6, borderRadius: '50%', background: c.dot,
        boxShadow: glow ? `0 0 0 3px ${c.bg}` : 'none',
      }} />
      {children}
    </span>
  );
}

// Barra de progreso con umbrales de color. `value`/`max` en las mismas unidades.
export function Meter({ value, max, tone }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const cls = tone || (pct > 85 ? 'bad' : pct > 65 ? 'warn' : 'ok');
  return (
    <div className="meter">
      <div className={`meter__fill ${cls}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Empty({ icon, children, hint }) {
  return (
    <div className="empty">
      {icon}
      <div className="empty-state-text">{children}</div>
      {hint && <div className="card-meta">{hint}</div>}
    </div>
  );
}

// Modal compartido: semántica, foco, fondo inerte y cierre deliberado.
export function Dialog({ title, onClose, children, actions, wide = false, closeDisabled = false, dismissible = true }) {
  const titleId = useId();
  const panel = useRef(null);
  const layer = useRef(null);
  const previous = useRef(document.activeElement);
  const callbacks = useRef({ onClose, closeDisabled, dismissible });
  useLayoutEffect(() => { callbacks.current = { onClose, closeDisabled, dismissible }; });
  const dismiss = () => {
    const current = callbacks.current;
    if (current.dismissible && !current.closeDisabled) current.onClose?.();
  };
  useLayoutEffect(() => activateModal({ panel: panel.current, layer: layer.current, previous: previous.current,
    dismiss: () => {
      const current = callbacks.current;
      if (current.dismissible && !current.closeDisabled) current.onClose?.();
    } }), []);
  return createPortal(
    <div ref={layer} className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) dismiss(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={closeDisabled || undefined}
        tabIndex={-1} className={`dialog ${wide ? 'wide' : ''}`}>
        <div className="dialog-head">
          <h2 id={titleId} className="dialog-title">{title}</h2>
          {dismissible && onClose && <button className="btn-icon" onClick={dismiss} disabled={closeDisabled} aria-label="Cerrar"><X size={16} /></button>}
        </div>
        <div className="dialog-body">{children}</div>
        {actions && <div className="dialog-actions">{actions}</div>}
      </div>
    </div>, document.body,
  );
}

// Iniciales para avatares.
export const iniciales = (nombre) =>
  (nombre || '')
    .trim()
    .split(/\s+/)
    .map((n) => n[0])
    .filter(Boolean)
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?';
