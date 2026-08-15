import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
export const getCatedra = (id) => api.get(`/catedras/${id}`);
export const createCatedra = (data) => api.post('/catedras/', data);
export const updateCatedra = (id, data) => api.patch(`/catedras/${id}`, data);

// Proxmox
export const getProxmoxStatus = () => api.get('/proxmox/status');
export const getProxmoxNodes = () => api.get('/proxmox/nodes');
export const getProxmoxResources = () => api.get('/proxmox/resources');
export const getProxmoxTemplates = (storage = 'local') => api.get('/proxmox/templates', { params: { storage } });

// Pedidos
export const getPedidos = (estado) => api.get('/pedidos/', { params: estado ? { estado } : {} });
export const getPedido = (id) => api.get(`/pedidos/${id}`);
export const createPedido = (data) => api.post('/pedidos/', data);
export const cambiarEstadoPedido = (id, data) => api.patch(`/pedidos/${id}/estado`, data);
export const getEstadosPedido = () => api.get('/pedidos/estados');

// Templates
export const getTemplates = () => api.get('/templates/');
export const getTemplate = (id) => api.get(`/templates/${id}`);
export const createTemplate = (data) => api.post('/templates/', data);

// Servicios / Orquestación
export const listarServicios = () => api.get('/servicios/');
export const obtenerServicio = (id) => api.get(`/servicios/${id}`);
export const desplegarPedido = (pedidoId, data = {}) => api.post(`/servicios/desplegar/${pedidoId}`, data);
export const iniciarServicio = (id) => api.post(`/servicios/${id}/start`);
export const detenerServicio = (id) => api.post(`/servicios/${id}/stop`);
export const eliminarServicio = (id) => api.delete(`/servicios/${id}`);
export const getStatusServicio = (id) => api.get(`/servicios/${id}/status`);

// Usuarios
export const getUsuarios = () => api.get('/usuarios/');
export const createUsuario = (data) => api.post('/usuarios/', data);
export const updateUsuario = (id, data) => api.patch(`/usuarios/${id}`, data);
export const deleteUsuario = (id) => api.delete(`/usuarios/${id}`);

// Métricas
export const getResumenMetricas = () => api.get('/metricas/resumen');
export const capturarMetricas = () => api.post('/metricas/capturar');
export const capturarServicio = (id) => api.post(`/metricas/capturar/${id}`);
export const getHistorialMetricas = (id, limit = 60) => api.get(`/metricas/${id}/historial`, { params: { limit } });
export const getUltimoSnapshot = (id) => api.get(`/metricas/${id}/ultimo`);

// Health
export const healthCheck = () => api.get('/health');

export default api;
