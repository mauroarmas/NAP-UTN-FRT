"""Entrega indivisible tras consumir evidencia real de la instancia vigente."""
from sqlalchemy import select

from app.models.definicion_servicio import DefinicionServicio
from app.models.evento_seguridad import EventoSeguridad
from app.models.pedido import Pedido, EstadoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.schemas.servicio import VerificarAccesoRequest
from app.services import evidencia_service, historial_service, notificacion_service
from app.services.acceso_service import requiere_admin_actual, requiere_acceso_servicio
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.services.service_access_service import preparacion_confirmada
from app.services.vigencia_service import exigir_cobertura
from app.utils.clock import clock, db_utc
from app.utils.errors import error


async def verificar(db, *, actor, servicio_id, body, clave):
    actor = await requiere_admin_actual(db, actor)
    body = body if isinstance(body, VerificarAccesoRequest) else VerificarAccesoRequest.model_validate(body)
    async def decide(session):
        service = await session.scalar(select(Servicio).where(Servicio.id == servicio_id).with_for_update()
            .execution_options(populate_existing=True))
        await requiere_acceso_servicio(session, actor, servicio_id)
        if service.estado != EstadoServicio.RUNNING:
            raise error(409, 'servicio_no_disponible', 'La instancia debe estar encendida para verificar acceso')
        await exigir_cobertura(session, service.id, clock.now())
        preparation = await preparacion_confirmada(session, service)
        if not preparation:
            raise error(409, 'preparacion_no_confirmada', 'La preparación vigente no está confirmada')
        evidence, document = await evidencia_service.obtener(session, body.evidencia_ref, tipo='acceso_instancia', revalidar=True)
        if document['entorno'] != 'real':
            raise error(422, 'evidencia_simulada', 'La entrega exige una observación real desde la red prevista')
        result = document['resultado']
        if (result['servicio_id'] != service.id or result['preparacion_id'] != str(preparation.id)
            or result['endpoint'] != body.endpoint or (service.acceso_metadata or {}).get('endpoint') != body.endpoint
            or document['observado_at'] != body.observado_at):
            raise error(409, 'evidencia_desactualizada', 'La referencia, endpoint o instante no coinciden con esta preparación')
        from datetime import datetime
        observed = datetime.fromisoformat(document['observado_at'].replace('Z', '+00:00'))
        await exigir_cobertura(session, service.id, observed)
        definition = await session.get(DefinicionServicio, service.definicion_version_id)
        if definition is None:
            raise error(409, 'definicion_no_disponible', 'Falta la definición de esta instancia')
        if definition.producto == 'linux':
            # T101 incorpora comprobación institucional y habilita la ruta
            # nativa; la evidencia individual no puede saltarse esa compuerta.
            raise error(409, 'consola_no_habilitada', 'Primero debe comprobarse aislamiento y revocación de consola en la instalación')
        if service.disponibilidad_aplicacion == 'utilizable' and service.evidencia_acceso_id:
            if service.evidencia_acceso_id != evidence.id:
                raise error(409, 'acceso_ya_verificado', 'Esta preparación ya tiene una evidencia de entrega registrada')
            return ResultadoDecision(200, {'servicio_id': service.id, 'disponibilidad': 'utilizable',
                'evidencia_ref': str(evidence.id), 'verificado_at': db_utc(service.acceso_red_verificado_at).isoformat()})
        event = f'acceso:{service.id}:{preparation.id}'
        service.disponibilidad_aplicacion = 'utilizable'
        service.evidencia_acceso_id, service.acceso_red_verificado_at = evidence.id, observed
        service.verificado_at = clock.now()
        pedido = await session.get(Pedido, service.pedido_id) if service.pedido_id else None
        if pedido and pedido.estado == EstadoPedido.EN_DESPLIEGUE:
            from app.services.pedido_service import transicionar
            await transicionar(session, pedido.id, EstadoPedido.ACTIVO, usuario=actor,
                motivo='Acceso de la instancia verificado desde la red prevista', operacion_id=preparation.id,
                evento_clave=event, metadata={'evidencia_ref': str(evidence.id)})
        elif pedido and pedido.estado != EstadoPedido.ACTIVO:
            raise error(409, 'pedido_incompatible', 'El pedido no admite una entrega de acceso en este estado')
        session.add(historial_service.registrar_servicio(service.id, service.estado.value, service.estado.value,
            comentario='Acceso verificado desde la red prevista', usuario=actor, operacion_id=preparation.id,
            evento_clave=event, metadata={'evidencia_ref': str(evidence.id)}))
        session.add(EventoSeguridad(actor_usuario_id=actor.id, accion='verificar_acceso_servicio', resultado='completado',
            referencia=f'servicio:{service.id}', motivo=f'evidencia:{evidence.id}'))
        await notificacion_service.encolar_acceso_verificado(session, service, preparation_id=preparation.id)
        await session.flush()
        return ResultadoDecision(200, {'servicio_id': service.id, 'disponibilidad': 'utilizable',
            'evidencia_ref': str(evidence.id), 'verificado_at': observed.isoformat()})
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/servicios/{servicio_id}/verificar-acceso',
        payload=body.model_dump(mode='json'), decidir=decide)
