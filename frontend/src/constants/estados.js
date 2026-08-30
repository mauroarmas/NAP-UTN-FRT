// Vocabulario de estados compartido entre pantallas.
// ESTADO_PEDIDO_CONFIG: single source of truth para el estado técnico de un pedido (7 estados).
// en_despliegue es transitorio: solo lo asigna el orquestador mientras dura el despliegue
// real contra Proxmox (ver pedido_service.TRANSICIONES_SISTEMA en el backend); no se ofrece
// como transición manual en ninguna pantalla.
// ESTADO_SERVICIO_SIMPLE: traducción a 3 categorías en lenguaje simple, solo para la vista de
// cátedra (spec 002-panel-catedra-simple, principio VI de la constitución). La vista de
// administrador/técnica sigue usando el detalle completo de EstadoServicio en Servicios.jsx.

// Etapas del avance de un pedido, para el stepper de la lista. `paso` es el
// índice en PASOS_PEDIDO; -1 es un estado terminal fuera del recorrido feliz.
export const PASOS_PEDIDO = ['Solicitado', 'Aprobado', 'En Despliegue', 'Activo'];

export const ESTADO_PEDIDO_CONFIG = {
  solicitado:    { label: 'Solicitado',    badge: 'info',    icon: '📨', paso: 0 },
  aprobado:      { label: 'Aprobado',      badge: 'success', icon: '✅', paso: 1 },
  en_despliegue: { label: 'En Despliegue', badge: 'info',    icon: '🚀', paso: 2 },
  activo:        { label: 'Activo',        badge: 'success', icon: '🟢', paso: 3 },
  rechazado:     { label: 'Rechazado',     badge: 'error',   icon: '❌', paso: -1 },
  error:         { label: 'Error',         badge: 'error',   icon: '⚠️', paso: -1 },
  suspendido:    { label: 'Suspendido',    badge: 'neutral', icon: '⏸️', paso: -1 },
};

// `stopped` y `paused` decían ambos "Apagado", lo que era razonable cuando la
// única forma de apagar un servicio era que alguien lo apagara. Ahora el
// sistema también lo hace por su cuenta (inactividad, vencimiento), y para la
// cátedra no es lo mismo: "lo apagué yo" no se responde igual que "me lo
// apagaron". Por eso se distinguen.
export const ESTADO_SERVICIO_SIMPLE = {
  running: { label: 'Activo',         badge: 'success', icon: '🟢' },
  stopped: { label: 'Apagado',        badge: 'neutral', icon: '⏹️' },
  paused:  { label: 'Pausado',        badge: 'warning', icon: '⏸️' },
  error:   { label: 'Con problemas',  badge: 'error',   icon: '⚠️' },
};
