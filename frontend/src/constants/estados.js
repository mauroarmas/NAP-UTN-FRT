// Vocabulario de estados compartido entre pantallas.
// ESTADO_PEDIDO_CONFIG: single source of truth para el estado técnico de un pedido (8 estados).
// ESTADO_SERVICIO_SIMPLE: traducción a 3 categorías en lenguaje simple, solo para la vista de
// cátedra (spec 002-panel-catedra-simple, principio VI de la constitución). La vista de
// administrador/técnica sigue usando el detalle completo de EstadoServicio en Servicios.jsx.

export const ESTADO_PEDIDO_CONFIG = {
  solicitado:    { label: 'Solicitado',    badge: 'info',    icon: '📨' },
  en_revision:   { label: 'En Revisión',   badge: 'warning', icon: '🔍' },
  aprobado:      { label: 'Aprobado',      badge: 'success', icon: '✅' },
  en_despliegue: { label: 'En Despliegue', badge: 'info',    icon: '🚀' },
  activo:        { label: 'Activo',        badge: 'success', icon: '🟢' },
  rechazado:     { label: 'Rechazado',     badge: 'error',   icon: '❌' },
  error:         { label: 'Error',         badge: 'error',   icon: '⚠️' },
  suspendido:    { label: 'Suspendido',    badge: 'neutral',  icon: '⏸️' },
};

export const ESTADO_SERVICIO_SIMPLE = {
  running: { label: 'Activo',         badge: 'success', icon: '🟢' },
  stopped: { label: 'Apagado',        badge: 'neutral', icon: '⏹️' },
  paused:  { label: 'Apagado',        badge: 'neutral', icon: '⏸️' },
  error:   { label: 'Con problemas',  badge: 'error',   icon: '⚠️' },
};
