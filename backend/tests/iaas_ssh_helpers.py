"""Dobles y atajos para las pruebas del acceso SSH a Linux IaaS (feature 017)."""
from datetime import timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import Pedido
from app.models.recurso_template import RecursoTemplate
from app.schemas.guest_runner import RunnerError
from app.services import bases_iaas_service as bases, perfiles_service
from app.utils.clock import clock
from app.utils.ssh_keys import validar_clave
from tests.capacity_helpers import aprobar_http


def nueva_clave(comentario='docente@equipo'):
    publica = ed25519.Ed25519PrivateKey.generate().public_key()
    return publica.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode() + ' ' + comentario


class RunnerSsh:
    """Doble del runner del nodo para el protocolo nap-iaas-access/1."""

    def __init__(self, *, error=None, excepcion=None):
        self.calls, self.error, self.excepcion = [], error, excepcion

    async def execute_iaas_access(self, request):
        self.calls.append(request)
        if self.excepcion:
            raise self.excepcion
        base = {'protocol': 'nap-iaas-access/1', 'operation_id': request['operation_id'], 'action': request['action'],
            'resource_uuid': request['resource_uuid'], 'phase': 'verified', 'identity_verified': True,
            'observed_at': clock.now().isoformat()}
        if self.error:
            return base | {'status': 'failed', 'phase': 'execution', 'error': {'code': self.error, 'retryable': False}}
        huella = validar_clave(request['clave_publica'])[2] if request['action'] == 'configure' else request['huella']
        return base | {'status': 'succeeded', 'result': {'ready': True, 'revision': request['revision'], 'huella': huella,
            'usuario': 'nap', 'puerto': 22}}


async def pedir_ubuntu(client, db, headers, catedra, *, proxmox, clave, clave_http='pedido-ssh', extra=None):
    """Sincroniza las bases, pide un Ubuntu y devuelve (respuesta, plantilla)."""
    await bases.sincronizar(db, pve=proxmox)
    await db.commit()
    row = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == 'Ubuntu 24.04'))
    await perfiles_service.anexar_disponibilidad(db, [row])
    hoy = clock.now().date()
    parametros = ({'clave_ssh_publica': clave} if clave is not None else {}) | (extra or {})
    cuerpo = {'template_id': row.id, 'modelo_servicio': 'iaas', 'catedra_id': catedra.id,
        'descripcion_requerimientos': 'Entorno para las prácticas de sistemas operativos.',
        'vigencia': {'tipo': 'personalizado', 'desde': hoy.isoformat(), 'hasta': (hoy + timedelta(days=7)).isoformat()}}
    if parametros:
        cuerpo['parametros_extra'] = parametros
    return await client.post('/pedidos/', headers=headers | {'Idempotency-Key': clave_http}, json=cuerpo), row


async def desplegar(client, db, engine, proxmox, runner, *, headers_admin, pedido_id, plantilla, vueltas=8):
    pedido = await db.get(Pedido, pedido_id)
    aprobado = await aprobar_http(client, pedido, plantilla, headers_admin, desplegar_inmediatamente=True)
    assert aprobado.status_code == 202, aprobado.text
    await db.commit()
    await procesar(engine, proxmox, runner, vueltas)
    await db.refresh(pedido)
    return pedido


async def procesar(engine, proxmox, runner, vueltas=8):
    from app.worker import procesar_una
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(vueltas):
        await procesar_una(sessions, pve=proxmox, runner=runner)
