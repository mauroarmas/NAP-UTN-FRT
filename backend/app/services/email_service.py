"""Servicio centralizado para generación y despacho de correos electrónicos."""

import logging
import smtplib
from email.message import EmailMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.usuario import Usuario, RolUsuario

logger = logging.getLogger(__name__)


def _generar_plantilla_html(titulo: str, subtitulo: str, cuerpo_html: str, boton_texto: str | None = None, boton_url: str | None = None) -> str:
    """Genera la estructura HTML institucional para correos con identidad UTN FRT."""
    settings = get_settings()
    url_accion = boton_url or settings.app_frontend_url

    boton_markup = ""
    if boton_texto and url_accion:
        boton_markup = f"""
        <div style="margin: 28px 0; text-align: center;">
            <a href="{url_accion}" style="background-color: #0d47a1; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block; font-size: 14px;">
                {boton_texto}
            </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>{titulo}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #333333;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f4f6f8; padding: 20px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 6px; overflow: hidden; border: 1px solid #e1e4e8; box-shadow: 0 2px 6px rgba(0,0,0,0.05);">
                    <!-- Header UTN FRT -->
                    <tr>
                        <td style="background-color: #0d47a1; padding: 24px 30px; text-align: left; color: #ffffff;">
                            <div style="font-size: 11px; letter-spacing: 1px; text-transform: uppercase; opacity: 0.85; font-weight: 600;">
                                Universidad Tecnológica Nacional · Facultad Regional Tucumán
                            </div>
                            <div style="font-size: 20px; font-weight: bold; margin-top: 4px;">
                                NAP — Nube Académica Personal
                            </div>
                            <div style="font-size: 13px; opacity: 0.9; margin-top: 2px;">
                                Portal de Gestión de Infraestructura
                            </div>
                        </td>
                    </tr>
                    <!-- Contenido -->
                    <tr>
                        <td style="padding: 30px;">
                            <h2 style="margin-top: 0; color: #1a202c; font-size: 18px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">
                                {subtitulo}
                            </h2>
                            <div style="font-size: 14px; line-height: 1.6; color: #4a5568;">
                                {cuerpo_html}
                            </div>
                            {boton_markup}
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 18px 30px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #718096; text-align: center;">
                            Este es un correo automático enviado por el Portal de Gestión de la UTN FRT.<br>
                            Si recibiste este mensaje por error o tienes consultas, comunícate con el Centro de Cómputos.
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def despachar_email(destinatarios: list[str], asunto: str, texto_plano: str, html_contenido: str, *, message_id: str | None = None) -> None:
    """Envía un correo electrónico de forma síncrona (destinado a ejecutarse en BackgroundTasks)."""
    if not destinatarios:
        logger.warning("No se proporcionaron destinatarios para el correo con asunto: %s", asunto)
        return

    settings = get_settings()
    remitente = settings.smtp_from or "noreply@frt.utn.edu.ar"

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = ", ".join(destinatarios)
    if message_id:
        msg["Message-ID"] = message_id
    msg.set_content(texto_plano)
    msg.add_alternative(html_contenido, subtype="html")

    if not settings.smtp_host:
        logger.info('Entrega pendiente: SMTP no configurado; no se registra el cuerpo')
        raise RuntimeError('SMTP no configurado')

    try:
        if settings.smtp_ssl:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)

        with server:
            if settings.smtp_tls and not settings.smtp_ssl:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info("Correo enviado exitosamente a %s con asunto: %s", destinatarios, asunto)
    except Exception as exc:
        logger.error("Entrega SMTP no confirmada")
        raise RuntimeError("Entrega SMTP no confirmada") from None


async def obtener_emails_administradores(db: AsyncSession) -> list[str]:
    """Obtiene la lista de correos de administradores activos que tienen habilitadas las notificaciones."""
    stmt = (
        select(Usuario.email)
        .where(
            Usuario.rol == RolUsuario.ADMIN,
            Usuario.activo.is_(True),
            Usuario.recibir_notificaciones_email.is_(True),
            Usuario.email.isnot(None),
        )
    )
    result = await db.execute(stmt)
    emails = [e for e in result.scalars().all() if e and e.strip()]
    return emails


def construir_bienvenida(nombre: str, username: str, password_provisoria: str):
    """Construye en memoria el mensaje; el secreto nunca va a logs ni al payload."""
    settings = get_settings()
    url_acceso = settings.app_frontend_url
    asunto = "Bienvenido a la Nube Académica Personal (UTN FRT) - Datos de acceso"

    texto_plano = f"""Estimado/a {nombre},

Te damos la bienvenida al Portal de Gestión de la Nube Académica Personal (NAP) de la UTN Facultad Regional Tucumán.

Tus credenciales de acceso inicial son:
- Usuario: {username}
- Contraseña provisoria: {password_provisoria}

Por razones de seguridad, al iniciar sesión por primera vez el sistema te solicitará cambiar obligatoriamente esta contraseña provisoria.

Acceso al portal:
{url_acceso}

Saludos cordiales,
Departamento Sistemas / Centro de Cómputos — UTN FRT
"""

    from html import escape
    nombre, username, password_provisoria = map(escape, [nombre, username, password_provisoria])
    cuerpo_html = f"""
    <p>Estimado/a <strong>{nombre}</strong>,</p>
    <p>Te damos la bienvenida al <strong>Portal de Gestión de la Nube Académica Personal (NAP)</strong> de la Facultad Regional Tucumán.</p>
    <p>Se ha generado una cuenta para tu acceso. A continuación se detallan tus credenciales de ingreso:</p>
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 15px; margin: 15px 0;">
        <p style="margin: 4px 0;"><strong>Usuario:</strong> <code>{username}</code></p>
        <p style="margin: 4px 0;"><strong>Contraseña provisoria:</strong> <code style="font-size: 15px; color: #0d47a1; font-weight: bold;">{password_provisoria}</code></p>
    </div>
    <div style="background-color: #fffaf0; border-left: 4px solid #dd6b20; padding: 10px 14px; margin: 15px 0; font-size: 13px; color: #7b341e;">
        <strong>Importante:</strong> Por motivos de seguridad institucional, cuando inicies sesión por primera vez el sistema te solicitará obligatoriamente cambiar esta contraseña provisoria por una clave personal definitiva antes de operar.
    </div>
    <p>Haz clic en el siguiente botón para ingresar al portal:</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo="Alta de Cuenta de Usuario",
        cuerpo_html=cuerpo_html,
        boton_texto="Ingresar al Portal",
        boton_url=url_acceso,
    )

    return asunto, texto_plano, html


def enviar_email_bienvenida(email: str, nombre: str, username: str, password_provisoria: str):
    asunto, texto, html = construir_bienvenida(nombre, username, password_provisoria)
    despachar_email([email], asunto, texto, html)


def enviar_email_nuevo_pedido(
    destinatarios: list[str],
    pedido_id: int,
    catedra_nombre: str,
    solicitante_nombre: str,
    modelo_servicio: str,
    es_reenvio: bool = False,
) -> None:
    """Notifica a los administradores sobre un nuevo pedido pendiente de revisión."""
    if not destinatarios:
        return

    settings = get_settings()
    url_pedidos = f"{settings.app_frontend_url}/pedidos"
    tipo_accion = "Pedido Reenviado para Revisión" if es_reenvio else "Nuevo Pedido Solicitado"
    asunto = f"[{tipo_accion}] Cátedra {catedra_nombre} (#{pedido_id})"

    texto_plano = f"""Estimado Administrador,

Se ha registrado una solicitud que requiere evaluación técnica:

- Pedido ID: #{pedido_id}
- Tipo: {tipo_accion}
- Cátedra: {catedra_nombre}
- Docente solicitante: {solicitante_nombre}
- Modelo de servicio: {modelo_servicio.upper()}

Puedes evaluar y aprobar o requerir ajustes desde el panel de pedidos:
{url_pedidos}

Departamento Sistemas / Centro de Cómputos — UTN FRT
"""

    cuerpo_html = f"""
    <p>Se ha recibido una solicitud de infraestructura académica que requiere revisión administrativa:</p>
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 15px; margin: 15px 0;">
        <p style="margin: 4px 0;"><strong>Identificador:</strong> Pedido #{pedido_id}</p>
        <p style="margin: 4px 0;"><strong>Cátedra:</strong> {catedra_nombre}</p>
        <p style="margin: 4px 0;"><strong>Docente:</strong> {solicitante_nombre}</p>
        <p style="margin: 4px 0;"><strong>Modelo de servicio:</strong> <span style="background: #e2e8f0; padding: 2px 6px; border-radius: 3px; font-weight: 600;">{modelo_servicio.upper()}</span></p>
        <p style="margin: 4px 0;"><strong>Estado:</strong> Solicitado (Pendiente de revisión)</p>
    </div>
    <p>Ingresa al portal para evaluar la capacidad disponible y resolver la solicitud:</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo=tipo_accion,
        cuerpo_html=cuerpo_html,
        boton_texto="Revisar Pedidos",
        boton_url=url_pedidos,
    )

    despachar_email(destinatarios, asunto, texto_plano, html)


def enviar_email_pedido_ajuste(
    email: str,
    nombre_docente: str,
    pedido_id: int,
    catedra_nombre: str,
    observaciones: str,
) -> None:
    """Notifica al docente cuando el administrador solicita ajustes sobre su pedido."""
    settings = get_settings()
    url_pedido = f"{settings.app_frontend_url}/pedidos"
    asunto = f"[Ajuste Requerido] Pedido #{pedido_id} - Cátedra {catedra_nombre}"

    texto_plano = f"""Estimado/a {nombre_docente},

El administrador ha evaluado tu pedido #{pedido_id} para la cátedra {catedra_nombre} y solicita ajustes antes de poder aprobarlo.

Observaciones del administrador:
"{observaciones}"

Por favor, ingresa al portal para editar los requerimientos y reenviar tu pedido:
{url_pedido}

Saludos cordiales,
Centro de Cómputos — UTN FRT
"""

    cuerpo_html = f"""
    <p>Estimado/a <strong>{nombre_docente}</strong>,</p>
    <p>El administrador ha revisado tu solicitud de recursos (<strong>Pedido #{pedido_id}</strong>) para la cátedra <strong>{catedra_nombre}</strong> y requiere algunas modificaciones antes de continuar.</p>
    <div style="background-color: #fffaf0; border-left: 4px solid #dd6b20; padding: 12px 16px; margin: 15px 0;">
        <strong style="color: #9c4221;">Observaciones del Administrador:</strong>
        <p style="margin: 8px 0 0 0; color: #7b341e; font-style: italic;">"{observaciones}"</p>
    </div>
    <p>Puedes ingresar al portal para modificar los parámetros o especificaciones del pedido y reenviarlo para su aprobación:</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo="Ajustes Solicitados en tu Pedido",
        cuerpo_html=cuerpo_html,
        boton_texto="Ver y Ajustar Pedido",
        boton_url=url_pedido,
    )

    despachar_email([email], asunto, texto_plano, html)


def enviar_email_pedido_rechazado(
    email: str,
    nombre_docente: str,
    pedido_id: int,
    catedra_nombre: str,
    motivo: str,
) -> None:
    """Notifica al docente sobre el rechazo formal de su pedido."""
    settings = get_settings()
    url_pedidos = f"{settings.app_frontend_url}/pedidos"
    asunto = f"[Pedido Rechazado] Pedido #{pedido_id} - Cátedra {catedra_nombre}"

    texto_plano = f"""Estimado/a {nombre_docente},

Te informamos que tu pedido #{pedido_id} para la cátedra {catedra_nombre} no ha podido ser aprobado.

Motivo de rechazo:
"{motivo}"

Puedes revisar el historial del pedido desde el portal:
{url_pedidos}

Saludos cordiales,
Centro de Cómputos — UTN FRT
"""

    cuerpo_html = f"""
    <p>Estimado/a <strong>{nombre_docente}</strong>,</p>
    <p>Te informamos que tu solicitud de recursos (<strong>Pedido #{pedido_id}</strong>) para la cátedra <strong>{catedra_nombre}</strong> ha sido rechazada.</p>
    <div style="background-color: #fff5f5; border-left: 4px solid #e53e3e; padding: 12px 16px; margin: 15px 0;">
        <strong style="color: #9b2c2c;">Motivo del Rechazo:</strong>
        <p style="margin: 8px 0 0 0; color: #742a2a;">"{motivo}"</p>
    </div>
    <p>Para más información o consultas técnicas sobre disponibilidad de capacidad, contacta al Centro de Cómputos.</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo="Pedido de Recursos Rechazado",
        cuerpo_html=cuerpo_html,
        boton_texto="Ver Pedidos",
        boton_url=url_pedidos,
    )

    despachar_email([email], asunto, texto_plano, html)


def enviar_email_servicio_activo(
    email: str,
    nombre_docente: str,
    pedido_id: int,
    servicio_id: int,
    servicio_nombre: str,
    catedra_nombre: str,
    url_acceso: str | None = None,
) -> None:
    """Notifica al docente cuando su servicio ha sido desplegado exitosamente y está activo."""
    settings = get_settings()
    url_servicio = f"{settings.app_frontend_url}/"
    asunto = f"[Servicio Activo] Tu servicio para {catedra_nombre} está disponible"

    texto_plano = f"""Estimado/a {nombre_docente},

¡Tu solicitud (Pedido #{pedido_id}) ha sido aprobada y el servicio ya se encuentra activo y operativo!

Detalles del servicio:
- Servicio: {servicio_nombre} (ID #{servicio_id})
- Cátedra: {catedra_nombre}
{f"- URL de acceso: {url_acceso}" if url_acceso else ""}

Puedes administrar y operar tu contenedor/servicio directamente desde el portal:
{url_servicio}

Saludos cordiales,
Centro de Cómputos — UTN FRT
"""

    cuerpo_html = f"""
    <p>Estimado/a <strong>{nombre_docente}</strong>,</p>
    <p>¡Buenas noticias! Tu solicitud de infraestructura correspondiente al <strong>Pedido #{pedido_id}</strong> ha sido aprobada y desplegada satisfactoriamente.</p>
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 4px; padding: 15px; margin: 15px 0;">
        <p style="margin: 4px 0;"><strong>Servicio:</strong> {servicio_nombre}</p>
        <p style="margin: 4px 0;"><strong>Cátedra:</strong> {catedra_nombre}</p>
        <p style="margin: 4px 0;"><strong>Estado:</strong> <span style="color: #15803d; font-weight: bold;">● Activo</span></p>
        {f'<p style="margin: 4px 0;"><strong>Enlace de acceso:</strong> <a href="{url_acceso}">{url_acceso}</a></p>' if url_acceso else ''}
    </div>
    <p>Ya puedes acceder a tu panel para iniciar, reiniciar o utilizar la consola de tu servicio:</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo="Servicio Aprobado y Disponible",
        cuerpo_html=cuerpo_html,
        boton_texto="Ir a Mis Servicios",
        boton_url=url_servicio,
    )

    despachar_email([email], asunto, texto_plano, html)


def enviar_email_error_despliegue(
    destinatarios: list[str],
    pedido_id: int,
    catedra_nombre: str,
    solicitante_nombre: str,
    detalle_error: str,
) -> None:
    """Alerta sobre fallos técnicos durante el despliegue automático del contenedor."""
    if not destinatarios:
        return

    settings = get_settings()
    url_pedidos = f"{settings.app_frontend_url}/pedidos"
    asunto = f"[Error en Despliegue] Incidente en Pedido #{pedido_id} ({catedra_nombre})"

    texto_plano = f"""Alerta de Despliegue,

Se ha producido un error durante el despliegue automático del Pedido #{pedido_id}:

- Cátedra: {catedra_nombre}
- Solicitante: {solicitante_nombre}
- Error técnico: {detalle_error}

El pedido ha pasado a estado ERROR para permitir su reintento o revisión técnica:
{url_pedidos}

Centro de Cómputos — UTN FRT
"""

    cuerpo_html = f"""
    <p>Se ha detectado un incidente técnico durante la tarea de despliegue en la infraestructura Proxmox:</p>
    <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 4px; padding: 15px; margin: 15px 0;">
        <p style="margin: 4px 0;"><strong>Pedido:</strong> #{pedido_id}</p>
        <p style="margin: 4px 0;"><strong>Cátedra:</strong> {catedra_nombre}</p>
        <p style="margin: 4px 0;"><strong>Solicitante:</strong> {solicitante_nombre}</p>
        <p style="margin: 4px 0; color: #b91c1c;"><strong>Detalle:</strong> <code>{detalle_error}</code></p>
    </div>
    <p>El pedido quedó en estado de error para permitir el diagnóstico y reintento correspondiente:</p>
    """

    html = _generar_plantilla_html(
        titulo=asunto,
        subtitulo="Fallo Técnico en Despliegue",
        cuerpo_html=cuerpo_html,
        boton_texto="Ver Pedido en Portal",
        boton_url=url_pedidos,
    )

    despachar_email(destinatarios, asunto, texto_plano, html)

