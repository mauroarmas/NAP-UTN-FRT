import { useCallback, useEffect, useRef, useState } from 'react';
import { obtenerConsolaOperacion } from '../services/api';

export default function useConsolaOperacion(operationId, options = {}) {
  const { active = true, intervalMs = 1000 } = options;

  const [metadata, setMetadata] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingPrevious, setLoadingPrevious] = useState(false);
  const [error, setError] = useState(null);
  const [revoked, setRevoked] = useState(false);

  const itemsRef = useRef([]);
  itemsRef.current = items;
  const metadataRef = useRef(null);
  metadataRef.current = metadata;

  const abortControllerRef = useRef(null);

  const mergeItems = useCallback((newItems) => {
    if (!newItems || newItems.length === 0) return;
    setItems((prev) => {
      const existingSeqs = new Set(prev.map((it) => it.seq));
      const filtered = newItems.filter((it) => !existingSeqs.has(it.seq));
      if (filtered.length === 0) return prev;
      const combined = [...prev, ...filtered];
      combined.sort((a, b) => a.seq - b.seq);
      return combined;
    });
  }, []);

  const prependItems = useCallback((olderItems) => {
    if (!olderItems || olderItems.length === 0) return;
    setItems((prev) => {
      const existingSeqs = new Set(prev.map((it) => it.seq));
      const filtered = olderItems.filter((it) => !existingSeqs.has(it.seq));
      if (filtered.length === 0) return prev;
      const combined = [...filtered, ...prev];
      combined.sort((a, b) => a.seq - b.seq);
      return combined;
    });
  }, []);

  // Polling loop
  useEffect(() => {
    if (!operationId || !active || revoked) return;

    let timer = null;
    let isCancelled = false;

    const poll = async () => {
      if (isCancelled) return;

      const currentItems = itemsRef.current;
      const lastSeq = currentItems.length > 0 ? currentItems[currentItems.length - 1].seq : null;

      const params = {};
      if (lastSeq !== null) {
        params.after = lastSeq;
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const { data } = await obtenerConsolaOperacion(operationId, params, {
          signal: controller.signal,
        });

        if (isCancelled) return;

        setMetadata(data);
        setError(null);
        setLoading(false);

        if (data.items && data.items.length > 0) {
          mergeItems(data.items);
        }
      } catch (err) {
        if (isCancelled || err.name === 'CanceledError' || err.name === 'AbortError') return;

        const status = err.response?.status;
        if (status === 401 || status === 403) {
          setRevoked(true);
          setItems([]);
          setError(new Error('Acceso revocado'));
          return;
        }

        // Error temporal o de red: conservar último estado y líneas
        setError(err);
        setLoading(false);
      } finally {
        if (!isCancelled && !revoked) {
          timer = setTimeout(poll, intervalMs);
        }
      }
    };

    poll();

    return () => {
      isCancelled = true;
      if (timer) clearTimeout(timer);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [operationId, active, intervalMs, revoked, mergeItems]);

  // Cargar mensajes anteriores
  const fetchPrevious = useCallback(async () => {
    if (!operationId || loadingPrevious || itemsRef.current.length === 0) return;

    const firstSeq = itemsRef.current[0].seq;
    const meta = metadataRef.current;
    if (meta && firstSeq <= meta.first_retained_seq) return;

    setLoadingPrevious(true);
    try {
      const { data } = await obtenerConsolaOperacion(operationId, { before: firstSeq });
      if (data.items && data.items.length > 0) {
        prependItems(data.items);
      }
    } catch (err) {
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        setRevoked(true);
        setItems([]);
        setError(new Error('Acceso revocado'));
      }
    } finally {
      setLoadingPrevious(false);
    }
  }, [operationId, loadingPrevious, prependItems]);

  // Exportar texto depurado completo congelando through_seq
  const exportarRegistro = useCallback(async () => {
    if (!operationId || revoked) return null;
    const currentMeta = metadataRef.current;
    const throughSeq = currentMeta?.last_seq || (itemsRef.current.length > 0 ? itemsRef.current[itemsRef.current.length - 1].seq : 0);

    let allItems = [];
    let afterCursor = 0;
    let hasMore = true;

    try {
      while (hasMore) {
        const { data } = await obtenerConsolaOperacion(operationId, {
          after: afterCursor,
          through_seq: throughSeq,
          limit_bytes: 65536,
        });

        if (!data.items || data.items.length === 0) break;
        allItems = [...allItems, ...data.items];
        afterCursor = data.items[data.items.length - 1].seq;

        if (afterCursor >= throughSeq || !data.has_more) {
          hasMore = false;
        }
      }

      const texto = allItems
        .map((it) => `[${it.captured_at || ''}] [${it.stream}] ${it.texto_depurado}`)
        .join('\n');

      return {
        texto,
        truncated: currentMeta?.truncated || false,
        expired: currentMeta?.expired || false,
        droppedMessages: currentMeta?.dropped_messages || 0,
        totalItems: allItems.length,
      };
    } catch (err) {
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        setRevoked(true);
        setItems([]);
        setError(new Error('Acceso revocado'));
      }
      throw err;
    }
  }, [operationId, revoked]);

  const hasMorePrevious = Boolean(
    metadata && items.length > 0 && items[0].seq > metadata.first_retained_seq
  );

  return {
    metadata,
    items,
    loading,
    loadingPrevious,
    error,
    revoked,
    hasMorePrevious,
    fetchPrevious,
    exportarRegistro,
  };
}
