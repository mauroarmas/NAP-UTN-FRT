import { useEffect, useRef, useState } from 'react';
import { buscarAplicaciones, getCategoriasAplicaciones } from '../services/api';
import { mensajeError } from '../utils/errors';
import { Search, Box, ArrowRight, LoaderCircle, Sparkles } from 'lucide-react';

export default function BibliotecaAplicaciones({ onSelected, onContinue, onBusyChange, onManualEntry }) {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [next, setNext] = useState(null);
  const running = useRef(false);
  const errorRef = useRef(null);
  const active = useRef(true);

  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);

  const loadCategories = async () => {
    setCategoriesLoading(true);
    try {
      const { data } = await getCategoriasAplicaciones();
      if (!active.current) return;
      if (Array.isArray(data?.items) && data.items.length > 0) {
        setCategories(data.items);
      }
    } catch {
      // Si el proveedor no tiene categorías, no es bloqueante
    } finally {
      if (active.current) setCategoriesLoading(false);
    }
  };

  useEffect(() => {
    active.current = true;
    loadCategories();
    return () => {
      active.current = false;
    };
  }, []);

  useEffect(() => {
    if (error) {
      errorRef.current?.scrollIntoView?.({ block: 'nearest' });
      errorRef.current?.focus({ preventScroll: true });
    }
  }, [error]);

  const search = async (cursor) => {
    if (running.current) return;
    const term = q.trim();
    if (!term && !category) return;
    running.current = true;
    setBusy(true);
    setError('');
    setStatus('');
    try {
      const params = {
        ...(term ? { q: term } : {}),
        ...(category ? { categoria: category } : {}),
        ...(cursor ? { cursor } : {}),
      };
      const { data } = await buscarAplicaciones(params);
      if (!active.current) return;
      if (cursor) {
        setItems((current) => [...current, ...data.items]);
      } else {
        setItems(data.items);
      }
      setNext(data.next_cursor || null);
      if (!data.items.length) {
        setStatus('Sin coincidencias en Docker Hub. Probá con otro nombre o ingresá la referencia directamente.');
      }
    } catch (err) {
      if (active.current) {
        setError(mensajeError(err, 'No se pudo consultar Docker Hub. Podés reintentar o ingresar la referencia manualmente.'));
      }
    } finally {
      running.current = false;
      if (active.current) setBusy(false);
    }
  };

  const choose = (row) => {
    onSelected?.(row);
    onContinue?.(row);
  };

  return (
    <section className="app-library" aria-labelledby="biblioteca-title">
      <form
        className="library-search"
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <div className="field library-search-main">
          <label htmlFor="biblioteca-q">Nombre de aplicación</label>
          <div className="library-search-input">
            <Search size={19} />
            <input
              id="biblioteca-q"
              className="input"
              placeholder="Ej.: whoami, postgres, redis, nginx…"
              value={q}
              maxLength={100}
              onChange={(event) => {
                setQ(event.target.value);
                setNext(null);
              }}
            />
          </div>
        </div>

        {categories.length > 0 && (
          <div className="field library-search-category">
            <label htmlFor="biblioteca-category">Categoría</label>
            <select
              id="biblioteca-category"
              className="input"
              value={category}
              disabled={categoriesLoading || busy}
              onChange={(event) => {
                setCategory(event.target.value);
                setNext(null);
              }}
            >
              <option value="">Todas las categorías</option>
              {categories.map((name) => (
                <option value={name} key={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        )}

        <button
          className="btn btn-primary library-search-button"
          aria-label="Buscar"
          disabled={busy || (!q.trim() && !category)}
        >
          <Search size={17} />
          Buscar
        </button>
      </form>

      {error && (
        <div role="alert" tabIndex={-1} ref={errorRef} className="callout bad">
          <p>{error}</p>
          {onManualEntry && (
            <button
              type="button"
              className="btn btn-secondary mt-2"
              onClick={onManualEntry}
            >
              Ingresar referencia manualmente
            </button>
          )}
        </div>
      )}

      {busy && (
        <p role="status" className="library-notice">
          <LoaderCircle size={16} className="library-spinner spin" />
          Buscando en Docker Hub…
        </p>
      )}

      {status && <p role="status" className="library-notice">{status}</p>}

      <div className="library-workspace">
        <div className="library-discovery">
          <h2 id="biblioteca-title">
            {items.length ? 'Resultados' : 'Biblioteca de aplicaciones (Docker Hub)'}
            {items.length > 0 && <span className="library-count">{items.length}</span>}
          </h2>

          {!items.length && !status && !busy && !error && (
            <div className="library-empty">
              <Search size={32} />
              <p>Buscá una aplicación en Docker Hub para agregarla al catálogo.</p>
            </div>
          )}

          <div className="library-results">
            {items.map((row) => {
              const isOfficial = row.procedencia === 'oficial' || row.distintivos?.includes('oficial');
              return (
                <article className="library-app" key={row.repositorio || row.nombre}>
                  <div className="library-app-heading">
                    <span className="library-app-icon">
                      <Box size={28} />
                    </span>
                    <div>
                      <h3>{row.nombre}</h3>
                      <span className={`library-app-status ${isOfficial ? 'is-ready' : 'is-community'}`}>
                        {isOfficial ? 'Oficial' : 'Comunidad'}
                      </span>
                    </div>
                  </div>
                  {row.descripcion && <p className="library-app-description">{row.descripcion}</p>}
                  <button
                    type="button"
                    className="btn btn-primary library-app-action"
                    disabled={busy}
                    aria-label={`Agregar ${row.nombre}`}
                    onClick={() => choose(row)}
                  >
                    Agregar servicio
                    <ArrowRight size={16} />
                  </button>
                </article>
              );
            })}
          </div>

          {next && (
            <div className="mt-4 text-center">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => search(next)}
              >
                Más resultados
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
