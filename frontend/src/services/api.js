import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor: agregar token a cada request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor: manejar 401 (token expirado)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (username, password) =>
  api.post('/auth/login', new URLSearchParams({ username, password }), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

export const getMe = () => api.get('/auth/me');

// Cátedras
export const getCatedras = () => api.get('/catedras/');
// Las cátedras de la persona autenticada. Reemplaza al viejo `/mi-catedra`:
// una persona puede tener varias, así que ya no hay una "mi cátedra" en singular.
export const getCatedrasMias = () => api.get('/catedras/mias');
// Para el selector del alta de usuario: solo las que no tienen responsable.
export const getCatedrasSinTitular = () => api.get('/catedras/', { params: { sin_titular: true } });
export const getCatedra = (id) => api.get(`/catedras/${id}`);
export const createCatedra = (data) => api.post('/catedras/', data);
export const updateCatedra = (id, data, { confirmar = false } = {}) =>
  api.patch(`/catedras/${id}`, data, { params: confirmar ? { confirmar: true } : {} });

// Proxmox
export const getProxmoxStatus = () => api.get('/proxmox/status');
export const getProxmoxNodes = () => api.get('/proxmox/nodes');
export const getProxmoxResources = () => api.get('/proxmox/resources');
// Espacio por storage. Ojo: no es lo mismo que el disco del nodo (ese es solo
// su sistema de archivos raíz); los contenedores viven en el storage con
// contenido rootdir/images.
export const getProxmoxStorage = () => api.get('/proxmox/storage');
export const getProxmoxTemplates = (storage = 'local') => api.get('/proxmox/templates', { params: { storage } });

// Pedidos
export const getPedidos = (estado) => api.get('/pedidos/', { params: estado ? { estado } : {} });
export const getPedido = (id) => api.get(`/pedidos/${id}`);
export const createPedido = (data) => api.post('/pedidos/', data);
export const cambiarEstadoPedido = (id, data) => api.patch(`/pedidos/${id}/estado`, data);
export const getEstadosPedido = () => api.get('/pedidos/estados');
export const reintentarPedido = (id, data = {}) => api.post(`/pedidos/${id}/reintentar`, data);

// Aprobación con reserva de capacidad.
// `evaluarPedido` trae los números y un `capacidad_token`; hay que devolverlo al
// aprobar. Si la capacidad cambió en el medio, el backend responde 409 y hay que
// reconfirmar sobre los valores nuevos en lugar de decidir con datos viejos.
export const evaluarPedido = (id) => api.get(`/pedidos/${id}/evaluacion`);
export const aprobarPedido = (id, data = {}) => api.post(`/pedidos/${id}/aprobar`, data);
export const rechazarPedido = (id, motivo) => api.post(`/pedidos/${id}/rechazar`, { motivo });

// Capacidad del clúster (admin). No se cachea: un número viejo acá es
// exactamente el problema que el modelo de reserva existe para evitar.
export const getCapacidad = () => api.get('/capacidad/');

// Templates
export const getTemplates = (incluirRetiradas = false) =>
  api.get('/templates/', { params: incluirRetiradas ? { incluir_retiradas: true } : {} });
export const getTemplate = (id) => api.get(`/templates/${id}`);
export const createTemplate = (data) => api.post('/templates/', data);
export const updateTemplate = (id, data) => api.patch(`/templates/${id}`, data);
// Retirar no borra: la plantilla sale del catálogo pero los pedidos y servicios
// que la referencian la siguen resolviendo.
export const retirarTemplate = (id) => api.patch(`/templates/${id}`, { activo: false });
export const reactivarTemplate = (id) => api.patch(`/templates/${id}`, { activo: true });

// Servicios / Orquestación
export const listarServicios = () => api.get('/servicios/');
export const obtenerServicio = (id) => api.get(`/servicios/${id}`);
export const desplegarPedido = (pedidoId, data = {}) => api.post(`/servicios/desplegar/${pedidoId}`, data);
export const iniciarServicio = (id) => api.post(`/servicios/${id}/start`);
export const detenerServicio = (id) => api.post(`/servicios/${id}/stop`);
export const reiniciarServicio = (id) => api.post(`/servicios/${id}/restart`);
export const eliminarServicio = (id) => api.delete(`/servicios/${id}`);
// Reactivar un servicio que el sistema pausó. La cátedra lo hace sola: si
// necesitara aprobación, el pausado automático sería una denegación encubierta.
export const reactivarServicio = (id) => api.post(`/servicios/${id}/reactivar`);
// `exento_pausado` lo maneja la cátedra; `vence_at`, solo el administrador.
export const actualizarServicio = (id, data) => api.patch(`/servicios/${id}`, data);
// Pedir extender la fecha de fin. Crea un pedido de renovación que el
// administrador resuelve con la misma pantalla que un pedido nuevo.
export const renovarServicio = (id) => api.post(`/servicios/${id}/renovar`);
export const getServiciosPausados = () => api.get('/servicios/pausados');
export const getServiciosExentosInactivos = () => api.get('/servicios/exentos-inactivos');
export const getStatusServicio = (id) => api.get(`/servicios/${id}/status`);
// URL base de Proxmox, para que el admin abra la consola nativa en otra pestaña.
export const getBaseConsolaProxmox = () => api.get('/servicios/consola/proxmox-base');
// Consola embebida — EN PAUSA, sin uso hoy. Ver DUDAS-ENTREVISTA.md.

// Usuarios
export const getUsuarios = (incluirBajas = false) =>
  api.get('/usuarios/', { params: incluirBajas ? { incluir_bajas: true } : {} });
export const createUsuario = (data) => api.post('/usuarios/', data);
export const updateUsuario = (id, data) => api.patch(`/usuarios/${id}`, data);
// Retirar, no borrar: el backend decide entre baja lógica y borrado real según
// la persona tenga historial o no, y devuelve 200 con el resultado (antes 204).
export const retirarUsuario = (id) => api.delete(`/usuarios/${id}`);
export const deleteUsuario = retirarUsuario;

// Métricas
export const getResumenMetricas = () => api.get('/metricas/resumen');
export const capturarMetricas = () => api.post('/metricas/capturar');
export const capturarServicio = (id) => api.post(`/metricas/capturar/${id}`);
export const getHistorialMetricas = (id, limit = 60) => api.get(`/metricas/${id}/historial`, { params: { limit } });
export const getUltimoSnapshot = (id) => api.get(`/metricas/${id}/ultimo`);

// Administración: trabajos periódicos y bitácora de la migración
export const getJobs = () => api.get('/admin/jobs');
export const ejecutarJob = (nombre) => api.post(`/admin/jobs/${nombre}`);
export const getAccesosPerdidos = () => api.get('/admin/migracion/accesos-perdidos');

// Health
export const healthCheck = () => api.get('/health');

export default api;
