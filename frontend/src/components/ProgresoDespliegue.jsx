import { AlertTriangle, Check, CheckCircle2, Clock3, LoaderCircle } from 'lucide-react';
import { Link } from 'react-router-dom';

const STEPS = ['Preparar recursos', 'Crear instancia', 'Iniciar aplicación', 'Habilitar acceso'];

const ERROR_MESSAGES = {
  perfil_aplicacion_no_disponible: 'La infraestructura todavía no tiene habilitado Docker para esta aplicación.',
  application_profile_unavailable: 'La infraestructura todavía no tiene habilitado Docker para esta aplicación.',
  platform_changed: 'El nodo de infraestructura cambió su versión de sistema y requiere revalidar el perfil Docker.',
  dependency_unavailable: 'El nodo de infraestructura no tiene disponibles las dependencias para ejecutar la aplicación.',
  fuente_no_disponible: 'No se pudo descargar la imagen de la aplicación desde el registro.',
  limpieza_pendiente: 'Quedaron recursos pendientes de limpieza del intento anterior.',
};

function resolverMotivoFallo(pedido, operacion) {
  const rawCode = operacion?.error_codigo || pedido?.error_codigo || (() => {
    const eventos = Array.isArray(pedido?.historial) ? pedido.historial : [];
    for (let i = eventos.length - 1; i >= 0; i -= 1) {
      const comentario = eventos[i]?.comentario || '';
      const match = comentario.match(/revisi[oó]n:\s*([a-z0-9_]+)/i);
      if (match) return match[1];
    }
    return null;
  })();
  if (rawCode) {
    const normalized = String(rawCode).trim().toLowerCase();
    if (ERROR_MESSAGES[normalized]) return ERROR_MESSAGES[normalized];
  }
  if (operacion?.error_detalle_seguro && !ERROR_MESSAGES[String(operacion.error_detalle_seguro).trim().toLowerCase()]) {
    return operacion.error_detalle_seguro;
  }
  return 'Administración debe revisar lo ocurrido antes de reintentar.';
}

export default function ProgresoDespliegue({ pedido, operacion, isAdmin = false, compact = false }) {
  if (pedido.tipo === 'renovacion') return null;
  const active = pedido.estado === 'activo';
  const failed = pedido.estado === 'error' || operacion?.estado === 'fallida';
  const uncertain = operacion?.estado === 'incierta' || operacion?.error_consulta;
  const delivered = active ? 4 : operacion?.estado === 'confirmada' || operacion?.fase === 'finalizada' || (!pedido.operation_id && pedido.servicio_id && pedido.estado === 'en_despliegue') ? 3
    : ['bootstrap', 'verificacion', 'instalacion', 'configuracion', 'arranque', 'comprobacion'].includes(operacion?.fase) ? 2
      : ['lista', 'dispatch_started', 'tarea', 'creacion', 'entorno'].includes(operacion?.fase) ? 1 : 0;
  const waiting = delivered === 3 && !active && !failed && !uncertain;
  const working = !active && !failed && !uncertain && !waiting;
  const title = active ? 'Servicio disponible' : failed ? 'El despliegue necesita revisión'
    : operacion?.error_consulta ? 'No se pudo actualizar el avance' : uncertain ? 'Comprobando el estado de la instancia'
      : waiting ? 'Servicio iniciado · acceso pendiente'
        : ['Preparando el despliegue…', 'Creando la instancia…', 'Iniciando la aplicación…'][delivered] || 'Consultando el avance…';
  const description = active ? 'El servicio ya puede utilizarse.' : failed ? resolverMotivoFallo(pedido, operacion)
    : operacion?.error_consulta ? 'Mostramos el último estado conocido. Volveremos a consultar automáticamente.'
      : uncertain ? 'NAP está verificando el resultado. No hace falta volver a pedir el despliegue.'
        : waiting ? isAdmin ? 'La instancia está creada. Comprobá su acceso desde Servicios para completar la entrega.'
          : 'La instancia está creada. Administración debe completar la verificación del acceso.'
          : delivered === 1 ? 'Proxmox está creando el contenedor del servicio.'
            : delivered === 2 ? 'Configurando la aplicación y comprobando que inicie correctamente.'
              : 'Validando los recursos y la conexión. Podés cerrar esta ventana; el proceso continúa.';
  const Icon = active ? CheckCircle2 : failed || uncertain ? AlertTriangle : waiting ? Clock3 : LoaderCircle;
  const mode = active ? 'is-ready' : failed ? 'is-failed' : uncertain || waiting ? 'is-attention' : 'is-running';
  return <section className={`deployment-progress ${mode} ${compact ? 'is-compact' : ''}`} aria-label="Avance del despliegue">
    <div className="deployment-progress__heading" role="status"><Icon size={compact ? 17 : 23} className={working ? 'library-spinner' : ''}/>
      <div><strong>{title}</strong>{!compact && <p>{description}</p>}</div>
      <span className="deployment-progress__count">{delivered} de 4 etapas</span>
    </div>
    <div className="deployment-progress__bar" role="progressbar" aria-label="Etapas completadas del despliegue"
      aria-valuemin={0} aria-valuemax={4} aria-valuenow={delivered} aria-valuetext={`${delivered} de 4 etapas completadas. ${title}`}>
      <span style={{ width: `${delivered * 25}%` }}/>
    </div>
    {!compact && <ol className="deployment-progress__steps">{STEPS.map((label, index) => <li key={label} className={index < delivered ? 'is-done' : index === delivered ? 'is-current' : ''} aria-current={index === delivered && !active ? 'step' : undefined}>
      <span>{index < delivered ? <Check size={13}/> : index + 1}</span>{label}</li>)}</ol>}
    {compact && (uncertain || waiting || failed) && <p className="deployment-progress__hint">{description}</p>}
    {waiting && !compact && <Link className="btn btn-secondary" to="/servicios">{isAdmin ? 'Revisar servicio' : 'Ver mis servicios'}</Link>}
  </section>;
}
