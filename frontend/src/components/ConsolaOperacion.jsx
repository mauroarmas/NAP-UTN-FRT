import { AlertCircle, AlertTriangle, ArrowDown, Check, Copy, Download, Loader2, Pause, Play, RefreshCw, X } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useConsolaOperacion from '../hooks/useConsolaOperacion';
import { activateModal } from '../utils/modalFocus';

export default function ConsolaOperacion({ operationId, onClose, intervalMs = 1000 }) {
  const {
    metadata,
    items,
    loading,
    loadingPrevious,
    error,
    revoked,
    hasMorePrevious,
    fetchPrevious,
    exportarRegistro,
  } = useConsolaOperacion(operationId, { intervalMs });

  const [isPaused, setIsPaused] = useState(false);
  const [newMessagesCount, setNewMessagesCount] = useState(0);
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);

  const scrollRef = useRef(null);
  const lastItemSeqRef = useRef(null);
  const layerRef = useRef(null);
  const panelRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useLayoutEffect(() => {
    onCloseRef.current = onClose;
  });

  useLayoutEffect(() => {
    return activateModal({
      panel: panelRef.current,
      layer: layerRef.current,
      previous: document.activeElement,
      dismiss: () => onCloseRef.current?.(),
    });
  }, []);

  // Auto-scroll when new items arrive and not paused
  useEffect(() => {
    if (!scrollRef.current || items.length === 0) return;

    const latestSeq = items[items.length - 1].seq;
    if (lastItemSeqRef.current === null) {
      lastItemSeqRef.current = latestSeq;
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      return;
    }

    if (latestSeq > lastItemSeqRef.current) {
      if (isPaused) {
        setNewMessagesCount((prev) => prev + (latestSeq - lastItemSeqRef.current));
      } else {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
      lastItemSeqRef.current = latestSeq;
    }
  }, [items, isPaused]);

  // Handle user scroll to detect manual review of history
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight <= 30;

    if (!isAtBottom && !isPaused) {
      setIsPaused(true);
    } else if (isAtBottom && isPaused) {
      setIsPaused(false);
      setNewMessagesCount(0);
    }
  };

  const resumeScroll = () => {
    setIsPaused(false);
    setNewMessagesCount(0);
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  const handleCopy = async () => {
    setExporting(true);
    try {
      const result = await exportarRegistro();
      if (!result) return;
      await navigator.clipboard.writeText(result.texto);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignorar o error capturado por hook
    } finally {
      setExporting(false);
    }
  };

  const handleDownload = async () => {
    setExporting(true);
    try {
      const result = await exportarRegistro();
      if (!result) return;
      const blob = new Blob([result.texto], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `consola-${operationId.slice(0, 8)}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Ignorar o error capturado por hook
    } finally {
      setExporting(false);
    }
  };

  const estadoBadgeClass =
    metadata?.estado === 'confirmada'
      ? 'badge-success'
      : metadata?.estado === 'fallida'
        ? 'badge-danger'
        : metadata?.estado === 'incierta'
          ? 'badge-warning'
          : 'badge-info';

  return createPortal(
    <div
      ref={layerRef}
      className="consola-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Consola de operación"
      tabIndex={-1}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current?.();
      }}
    >
      <div ref={panelRef} className="consola-container" tabIndex={-1}>
        {/* Header */}
        <header className="consola-header">
          <div className="consola-header__info">
            <span className="consola-title">Consola de operación</span>
            <span className="consola-id" title={operationId}>
              {operationId.slice(0, 8)}…
            </span>
            {metadata && (
              <>
                <span className={`badge ${estadoBadgeClass}`}>{metadata.estado}</span>
                <span className="consola-meta-pill">Fase: {metadata.fase}</span>
                <span className="consola-meta-pill">Intento #{metadata.intento_efectivo}</span>
              </>
            )}
          </div>

          <div className="consola-header__actions">
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={handleCopy}
              disabled={exporting || items.length === 0}
              aria-label="Copiar consola"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              <span>{copied ? 'Copiado' : 'Copiar'}</span>
            </button>

            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={handleDownload}
              disabled={exporting || items.length === 0}
              aria-label="Descargar registro"
            >
              <Download size={14} />
              <span>Descargar</span>
            </button>

            <button
              type="button"
              className="btn btn-sm btn-icon"
              onClick={onClose}
              aria-label="Cerrar consola"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Notices & Banners */}
        {metadata?.truncated && (
          <div className="consola-notice is-warning" role="alert">
            <AlertTriangle size={15} />
            <span>
              Aviso: Se omitieron {metadata.dropped_messages || ''} mensajes por límite de almacenamiento. Mostrando desde secuencia #{metadata.first_retained_seq}.
            </span>
          </div>
        )}

        {metadata?.expired && (
          <div className="consola-notice is-danger" role="alert">
            <AlertCircle size={15} />
            <span>
              El registro de consola expiró tras 30 días de retención.
              {metadata.resultado_final?.texto && ` Resultado final: ${metadata.resultado_final.texto}`}
            </span>
          </div>
        )}

        {error && !revoked && (
          <div className="consola-notice is-subtle">
            <RefreshCw size={14} className="library-spinner" />
            <span>Error temporal de conexión. Reintentando consulta en segundo plano…</span>
          </div>
        )}

        {revoked && (
          <div className="consola-notice is-danger" role="alert">
            <AlertCircle size={15} />
            <span>Acceso revocado: No tenés permisos administrativos para ver esta consola.</span>
          </div>
        )}

        {/* Terminal Body */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="consola-terminal"
          style={{
            backgroundColor: '#000000',
            color: '#ffffff',
            fontFamily: 'monospace',
            padding: '12px',
            overflowY: 'auto',
            maxHeight: '480px',
            minHeight: '280px',
          }}
          tabIndex={0}
          aria-label="Terminal de salida de consola"
        >
          {hasMorePrevious && (
            <div style={{ textAlign: 'center', marginBottom: '8px' }}>
              <button
                type="button"
                className="btn btn-xs btn-outline"
                onClick={fetchPrevious}
                disabled={loadingPrevious}
                aria-label="Cargar mensajes anteriores"
              >
                {loadingPrevious ? 'Cargando…' : '▲ Cargar mensajes anteriores'}
              </button>
            </div>
          )}

          {loading && items.length === 0 && !revoked && (
            <div style={{ color: '#888', fontStyle: 'italic', padding: '8px 0' }}>
              Iniciando visualización de consola…
            </div>
          )}

          {items.map((it) => (
            <div key={it.seq} className="consola-line" style={{ display: 'flex', gap: '8px', lineHeight: '1.4' }}>
              <span style={{ color: '#666', userSelect: 'none', flexShrink: 0 }}>
                {String(it.seq).padStart(4, ' ')}
              </span>
              <span
                style={{
                  color: it.stream === 'stderr' ? '#ff6b6b' : it.stream === 'sistema' ? '#6bc5ff' : '#ffffff',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {it.texto_depurado}
              </span>
            </div>
          ))}

          {metadata?.resultado_final && items.length === 0 && (
            <div style={{ padding: '8px 0', color: '#ffb74d' }}>
              {metadata.resultado_final.texto}
            </div>
          )}
        </div>

        {/* Footer controls & Pause pill */}
        <footer className="consola-footer">
          <div className="consola-footer__status">
            {isPaused ? (
              <button
                type="button"
                className="btn btn-xs btn-warning"
                onClick={resumeScroll}
                aria-label="Reanudar desplazamiento"
              >
                <ArrowDown size={13} />
                <span>Pausado · {newMessagesCount > 0 ? `${newMessagesCount} nuevos · ` : ''}Ir al final</span>
              </button>
            ) : (
              <span className="consola-footer__autoscroll-hint">
                <Play size={11} /> Auto-desplazamiento activo
              </span>
            )}
          </div>

          <div className="consola-footer__count">
            {items.length} mensaje{items.length === 1 ? '' : 's'} retenido{items.length === 1 ? '' : 's'}
          </div>
        </footer>
      </div>
    </div>,
    document.body
  );
}
