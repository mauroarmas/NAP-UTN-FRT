// El contrato nuevo conserva datos estructurados; los mensajes de la UI son texto.
export function mensajeError(error, fallback = 'No se pudo completar la acción') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (typeof detail?.mensaje === 'string' && detail.mensaje) return detail.mensaje;
  return fallback;
}
