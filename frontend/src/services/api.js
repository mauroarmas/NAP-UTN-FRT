import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});
let csrfValue = null;
let csrfPending = null;
export const getCsrf = async () => {
  if (csrfValue) return csrfValue;
  if (!csrfPending) csrfPending = api.get('/auth/csrf').then(({ data }) => {
    csrfValue = data.csrf_token;
    return csrfValue;
  }).finally(() => { csrfPending = null; });
  return csrfPending;
};
api.interceptors.request.use(async (config) => {
  if (!['get', 'head', 'options'].includes((config.method || 'get').toLowerCase())) {
    if (config.url === '/auth/login') config.headers['X-NAP-Request'] = '1';
    else config.headers['X-CSRF-Token'] = await getCsrf();
  }
  return config;
});
api.interceptors.response.use((response) => {
  if (response.data?.sesion_rotada || response.data?.estado === 'sesion_finalizada' || response.config.url === '/auth/logout') csrfValue = null;
  return response;
}, (error) => {
  if (error.response?.status === 401) {
    csrfValue = null;
    if (error.config?.url !== '/auth/login') window.dispatchEvent(new Event('nap:session-invalid'));
  }
  if (error.response?.data?.detail?.codigo === 'csrf_invalido') csrfValue = null;
  if (error.response?.data?.detail?.codigo === 'habilitacion_pendiente') window.dispatchEvent(new Event('nap:session-refresh'));
  return Promise.reject(error);
});

// Auth
export const login = (username, password) =>
  api.post('/auth/login', new URLSearchParams({ username, password }), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

export const getMe = () => api.get('/auth/me');
export const logout = () => api.post('/auth/logout');
export const verificarIngresoTotp = (desafio_id, codigo_totp) => api.post('/auth/2fa/challenge/verify', { desafio_id, codigo_totp });
export const preparar2FA = (data = {}) => api.post('/auth/2fa/setup', data);
export const confirmar2FA = (data) => api.post('/auth/2fa/verify', data);
export const prepararReemplazo2FA = (data) => api.post('/auth/2fa/replacement/setup', data);
export const confirmarReemplazo2FA = (data) => api.post('/auth/2fa/replacement/verify', data);
export const cancelarSetup2FA = (desafio_id) => api.delete('/auth/2fa/setup', { data: { desafio_id } });
export const recuperar2FA = (data) => api.post('/auth/2fa/recovery', data);
export const recuperar2FAAsistido = (data) => api.post('/auth/2fa/assisted-recovery', data);
export const regenerarCodigos2FA = (data) => api.post('/auth/2fa/recovery-codes/regenerate', data);
export const desactivar2FA = (data) => api.post('/auth/2fa/disable', data);
export const cambiarPasswordInicial = (nuevaPassword) =>
  api.post('/auth/cambiar-password-inicial', { nueva_password: nuevaPassword });

// Cátedras
export const getCatedras = (options = {}) => api.get('/catedras/', options);
// Las cátedras de la persona autenticada. Reemplaza al viejo `/mi-catedra`:
// una persona puede tener varias, así que ya no hay una "mi cátedra" en singular.
export const getCatedrasMias = (options = {}) => api.get('/catedras/mias', options);
// Para el selector del alta de usuario: solo las que no tienen responsable.
export const getCatedrasSinTitular = () => api.get('/catedras/', { params: { sin_titular: true } });
export const getCatedra = (id) => api.get(`/catedras/${id}`);
export const createCatedra = (data) => api.post('/catedras/', data);
export const updateCatedra = (id, data, { confirmar = false } = {}) =>
  api.patch(`/catedras/${id}`, data, { params: confirmar ? { confirmar: true } : {}, headers: { 'Idempotency-Key': crypto.randomUUID() } });

// Proxmox
export const getProxmoxStatus = () => api.get('/proxmox/status');
export const getProxmoxNodes = () => api.get('/proxmox/nodes');
export const getProxmoxResources = () => api.get('/proxmox/resources');
export const verificarInfraCatedra = (id, options = {}) => api.get(`/catedras/${id}/infraestructura`, options);
// Espacio por storage. Ojo: no es lo mismo que el disco del nodo (ese es solo
// su sistema de archivos raíz); los contenedores viven en el storage con
// contenido rootdir/images.
export const getProxmoxStorage = () => api.get('/proxmox/storage');
export const getProxmoxTemplates = (storage = 'local') => api.get('/proxmox/templates', { params: { storage } });

// Pedidos
export const getPedidos = (estado, options = {}) => api.get('/pedidos/', { ...options, params: estado ? { estado } : {} });
export const getPedido = (id, options = {}) => api.get(`/pedidos/${id}`, options);
export const createPedido = (data, clave = crypto.randomUUID()) => api.post('/pedidos/', data, ordenHeaders(clave));
export const getEstadosPedido = () => api.get('/pedidos/estados');
export const reintentarPedido = (id, data = {}, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/reintentar`, data, ordenHeaders(clave));

// Aprobación con reserva de capacidad.
// `evaluarPedido` trae los números y un `capacidad_token`; hay que devolverlo al
// aprobar. Si la capacidad cambió en el medio, el backend responde 409 y hay que
// reconfirmar sobre los valores nuevos en lugar de decidir con datos viejos.
export const evaluarPedido = (id, seleccion, signal) => api.post(`/pedidos/${id}/evaluacion`, seleccion, { signal });
export const aprobarPedido = (id, data = {}, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/aprobar`, data, ordenHeaders(clave));
export const rechazarPedido = (id, motivo, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/rechazar`, { motivo }, ordenHeaders(clave));
export const solicitarAjustePedido = (id, observaciones, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/solicitar-ajuste`, { observaciones }, ordenHeaders(clave));
export const reenviarPedido = (id, data = {}, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/reenviar`, data, ordenHeaders(clave));
export const cancelarPedido = (id, motivo, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/cancelar`, { motivo }, ordenHeaders(clave));

// Deshacer una aprobación antes del despliegue: libera la capacidad reservada en
// el acto, en lugar de esperar hasta 24 h al vencimiento automático. Es una
// operación con nombre propio y no un cambio de estado: mover el estado sin
// liberar la reserva dejaría capacidad comprometida sin nada detrás.
// Devuelve el pedido más `capacidad_liberada`, para poder decir cuánto volvió
// sin una segunda consulta que ya podría leer otro número.
export const revertirAprobacion = (id, motivo, clave = crypto.randomUUID()) => api.post(`/pedidos/${id}/revertir-aprobacion`, { motivo }, ordenHeaders(clave));

// Capacidad del clúster (admin). No se cachea: un número viejo acá es
// exactamente el problema que el modelo de reserva existe para evitar.
export const getCapacidad = () => api.get('/capacidad/');
export const getCalendario = (anio, signal) => api.get(`/calendarios/${anio}`, { signal });
export const getPeriodosCalendario = (anio) => api.get(`/calendarios/${anio}/periodos`);
export const guardarCalendario = (anio, data, clave = crypto.randomUUID()) => api.put(`/calendarios/${anio}`, data, ordenHeaders(clave));

// Templates
export const consultarPreparacion = (id) => api.get(`/biblioteca/incorporaciones/${id}/preparacion`);
export const agregarAplicacion = (id, data, clave) => api.post(`/biblioteca/incorporaciones/${id}/agregar`, data, ordenHeaders(clave));
export const sincronizarIaas = () => api.post('/templates/sincronizar-iaas');
export const prepararAplicacion = (id, data, clave) => api.post(`/biblioteca/incorporaciones/${id}/preparar`, data, ordenHeaders(clave));
export const confirmarFuncionamiento = (id, funciona, clave) => api.post(`/biblioteca/incorporaciones/${id}/confirmar-funcionamiento`, { funciona }, ordenHeaders(clave));
export const publicarAplicacion = (id, data, clave) => api.post(`/biblioteca/incorporaciones/${id}/publicar`, data, ordenHeaders(clave));
export const eliminarPreparacion = (id, clave) => api.post(`/biblioteca/incorporaciones/${id}/eliminar`, {}, ordenHeaders(clave));
export const getTamanos = () => api.get('/templates/tamanos');
export const getTemplates = (incluirRetiradas = false, modeloServicio = null, options = {}) =>
  api.get('/templates/', {
    ...options,
    params: {
      ...(incluirRetiradas ? { incluir_retiradas: true } : {}),
      ...(modeloServicio ? { modelo_servicio: modeloServicio } : {}),
    },
  });
export const getTemplate = (id) => api.get(`/templates/${id}`);
export const createTemplate = (data) => api.post('/templates/', data);
export const updateTemplate = (id, data) => api.patch(`/templates/${id}`, data);
// Retirar no borra: la plantilla sale del catálogo pero los pedidos y servicios
// que la referencian la siguen resolviendo.
export const retirarTemplate = (id) => api.delete(`/templates/${id}`);
export const deleteTemplate = (id) => api.delete(`/templates/${id}`);
export const reactivarTemplate = (id) => api.patch(`/templates/${id}`, { activo: true });

// Servicios / Orquestación
export const listarServicios = (options = {}) => api.get('/servicios/', options);
export const evaluarRegularizacion = (id, data = {}, options = {}) => api.post(`/servicios/${id}/regularizacion/evaluar`, data, options);
export const confirmarRegularizacion = (id, data, clave) => api.post(`/servicios/${id}/regularizacion`, data, ordenHeaders(clave));
export const archivarDuplicadoLegacy = (id, data, clave) => api.post(`/servicios/${id}/regularizacion/archivar-duplicado`, data, ordenHeaders(clave));
export const obtenerServicio = (id) => api.get(`/servicios/${id}`);
const ordenHeaders = (clave) => ({ headers: { 'Idempotency-Key': clave } });
export const desplegarPedido = (pedidoId, data = {}, clave = crypto.randomUUID()) => api.post(`/servicios/desplegar/${pedidoId}`, data, ordenHeaders(clave));
export const iniciarServicio = (id, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/start`, {}, ordenHeaders(clave));
export const detenerServicio = (id, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/stop`, {}, ordenHeaders(clave));
export const reiniciarServicio = (id, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/restart`, {}, ordenHeaders(clave));
export const eliminarServicio = (id, clave = crypto.randomUUID()) => api.delete(`/servicios/${id}`, ordenHeaders(clave));
// Reactivar un servicio que el sistema pausó. La cátedra lo hace sola: si
// necesitara aprobación, el pausado automático sería una denegación encubierta.
export const reactivarServicio = (id, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/reactivar`, {}, ordenHeaders(clave));
export const obtenerOperacion = (id, signal) => api.get(`/operaciones/${id}`, { signal });
export const listarOperaciones = async (params = {}, options = {}) => {
  const items = [];
  let cursor;
  do {
    const { data } = await api.get('/operaciones', { ...options, params: { ...params, limit: 100, cursor } });
    items.push(...data.items);
    cursor = data.next_cursor;
  } while (cursor);
  return { data: items };
};
// La exención de inactividad no cambia las vigencias aprobadas.
export const actualizarServicio = (id, data) => api.patch(`/servicios/${id}`, data);
// Pedir extender la fecha de fin. Crea un pedido de renovación que el
// administrador resuelve con la misma pantalla que un pedido nuevo.
export const renovarServicio = (id, data, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/renovar`, data, ordenHeaders(clave));
export const modificarVigencia = (id, periodoId, data, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/vigencias/${periodoId}/modificaciones`, data, ordenHeaders(clave));
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
export const updateUsuario = (id, data) => api.patch(`/usuarios/${id}`, data, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
// El retiro conserva identidad e historial y puede quedar pendiente de revocación.
export const retirarUsuario = (id, revision) => api.delete(`/usuarios/${id}`, { params: { revision_esperada: revision }, headers: { 'Idempotency-Key': crypto.randomUUID() } });
export const deleteUsuario = retirarUsuario;

// La evidencia se envía como texto para conservar las claves originales.
export const registrarEvidencia = (documento, clave = crypto.randomUUID()) => api.post('/evidencias', documento, ordenHeaders(clave));
export const getAccesoServicio = (id) => api.get(`/servicios/${id}/acceso`);
export const abrirAplicacionServicio = (id) => api.post(`/servicios/${id}/abrir-aplicacion`, {});
export const revelarAccesoServicio = (id) => api.post(`/servicios/${id}/acceso/revelar`, {});
export const verificarAccesoServicio = (id, data, clave = crypto.randomUUID()) => api.post(`/servicios/${id}/verificar-acceso`, data, ordenHeaders(clave));
export const getConsolaServicio = (id) => api.get(`/servicios/${id}/consola`);
export const getDefiniciones = (incluir_no_publicadas = false, modelo_servicio = null) => api.get('/definiciones', {
  params: { incluir_no_publicadas, ...(modelo_servicio ? { modelo_servicio } : {}) },
});
export const crearDefinicion = (data, clave = crypto.randomUUID()) => api.post('/definiciones', data, ordenHeaders(clave));
// Enviar texto conserva claves duplicadas para su rechazo en el servidor.
export const guardarManifest = (id, texto, clave = crypto.randomUUID()) => api.put(`/definiciones/${id}/manifest`, '{"manifest":' + texto + '}', ordenHeaders(clave));
export const validarDefinicion = (id, clave = crypto.randomUUID()) => api.post(`/definiciones/${id}/validar`, {}, ordenHeaders(clave));
export const publicarDefinicion = (id, clave = crypto.randomUUID()) => api.post(`/definiciones/${id}/publicar`, {}, ordenHeaders(clave));
export const retirarDefinicion = (id, motivo, clave = crypto.randomUUID()) => api.post(`/definiciones/${id}/retirar`, { motivo }, ordenHeaders(clave));
export const listarCambiosConsola = () => api.get('/admin/cambios-consola');
export const obtenerCambioConsola = (id) => api.get(`/admin/cambios-consola/${id}`);
export const confirmarRevocacionConsola = (id, evidencia_ref) => api.post(`/admin/cambios-consola/${id}/confirmar-revocacion`, { evidencia_ref }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
export const registrarFalloConsola = (id, motivo) => api.post(`/admin/cambios-consola/${id}/registrar-fallo`, { motivo }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });

// Métricas
export const getResumenMetricas = (options = {}) => api.get('/metricas/resumen', options);
export const capturarMetricas = () => api.post('/metricas/capturar');
export const capturarServicio = (id) => api.post(`/metricas/capturar/${id}`);
export const getHistorialMetricas = (id, limit = 60, params = {}, options = {}) => api.get(`/metricas/${id}/historial`, { ...options, params: { limit, ...params } });
export const getUltimoSnapshot = (id) => api.get(`/metricas/${id}/ultimo`);

// Administración: trabajos periódicos y bitácora de la migración
export const getJobs = () => api.get('/admin/jobs');
export const ejecutarJob = (nombre) => api.post(`/admin/jobs/${nombre}`);
export const getAccesosPerdidos = () => api.get('/admin/migracion/accesos-perdidos');

// Health
export const healthCheck = () => api.get('/health');

export default api;

// Alertas por alcance vigente; las consultas no disparan captura ni correo.
export const getAlertas = (params = {}, options = {}) => api.get('/alertas', { ...options, params });
export const getAvisos = (params = {}, options = {}) => api.get('/alertas/avisos', { ...options, params });
export const getEstadoCorreo = (params = {}, options = {}) => api.get('/alertas/correo', { ...options, params });

// Biblioteca: sólo descubrimiento e incorporación administrativa.
export const getCategoriasAplicaciones = () => api.get('/biblioteca/categorias');
export const buscarAplicaciones = (params) => api.get('/biblioteca/aplicaciones', { params });
export const listarIncorporaciones = (params = {}) => api.get('/biblioteca/incorporaciones', { params });
export const incorporarAplicacion = (body, key) => api.post('/biblioteca/incorporaciones', body, { headers: { 'Idempotency-Key': key } });
export const editarIncorporacion = (id, body, key) => api.patch(`/biblioteca/incorporaciones/${id}`, body, { headers: { 'Idempotency-Key': key } });
export const obtenerIncorporacion = (id) => api.get(`/biblioteca/incorporaciones/${id}`);
export const crearRevisionBiblioteca = (id, body, key) => api.post(`/biblioteca/incorporaciones/${id}/definicion`, body, { headers: { 'Idempotency-Key': key } });
export const listarEnsayos = (definitionId) => api.get(`/definiciones/${definitionId}/ensayos`);
export const obtenerEnsayo = (id) => api.get(`/ensayos/${id}`);
export const iniciarEnsayo = (id, body, key) => api.post(`/definiciones/${id}/ensayos`, body, { headers: { 'Idempotency-Key': key } });
export const accionEnsayo = (id, action, body, key) => api.post(`/ensayos/${id}/${action}`, body, { headers: { 'Idempotency-Key': key } });
export const revelarAccesoEnsayo = (id, resourceId, key) => api.post(`/ensayos/${id}/recursos/${resourceId}/revelar-acceso`, {}, { headers: { 'Idempotency-Key': key } });
export const publicarOferta = (id, body, key) => api.post(`/definiciones/${id}/publicar-oferta`, body, { headers: { 'Idempotency-Key': key } });
