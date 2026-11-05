"""Bases Linux de Proxmox: catálogo directo, sin construir una aplicación."""
from copy import deepcopy
import re

from sqlalchemy import select

from app.config import get_settings
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.pedido import ModeloServicio
from app.schemas.tamanos import TAMANOS
from app.services.infraestructura_io import consultar
from app.utils.errors import error


def nombre_base(volume):
    if not isinstance(volume, str):
        return None
    match = re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*:vztmpl/(ubuntu|debian)-(24\.04|13)-standard_[A-Za-z0-9_.+-]+_amd64\.tar\.(?:zst|xz|gz)', volume)
    if not match or (match[1], match[2]) not in {('ubuntu', '24.04'), ('debian', '13')}:
        return None
    return ('Ubuntu' if match[1] == 'ubuntu' else 'Debian') + ' ' + match[2]


def es_base(template):
    return bool(template and not template.definicion_version_id
        and template.tipo == TipoRecurso.LXC and template.modelo_servicio == ModeloServicio.IAAS
        and (template.config_extra or {}).get('origen') == 'proxmox_iaas'
        and nombre_base(template.os_template))


def red(node=None):
    settings = get_settings()
    selected = settings.iaas_network_profile_id
    profile = settings.network_profiles.get(selected)
    if (not profile or not set(profile.get('nodes', [])) & set(settings.infrastructure_profile.get('nodos', {}))
        or (node and node not in profile.get('nodes', []))
        or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', profile.get('bridge', ''))):
        raise error(409, 'red_iaas_no_configurada', 'Falta configurar la red de los entornos Linux.')
    return selected, deepcopy(profile)


def disponible(template):
    try:
        _, profile = red()
        return bool(es_base(template) and template.activo and (template.config_extra or {}).get('disponible', False)
            and set(template.config_extra.get('nodes', [])) & set(profile['nodes']))
    except Exception:
        return False


async def sincronizar(db, *, pve=None):
    from app.services.capacidad_service import bloqueo_capacidad
    settings = get_settings()
    if not settings.infrastructure_profile.get('nodos'):
        raise error(409, 'conexion_iaas_no_configurada', 'Falta configurar la conexión con Proxmox.')
    found = {}
    # Sólo se consulta infraestructura autorizada; un fallo no borra el catálogo anterior.
    for node in settings.infrastructure_profile.get('nodos', {}):
        observed = await consultar('get_available_templates', node, settings.iaas_template_storage, pve=pve)
        if observed.estado != 'presente':
            raise error(502, 'catalogo_iaas_no_verificable', 'No se pudieron consultar las bases Linux de Proxmox.')
        for item in observed.valor:
            volume = item.get('volid')
            name = nombre_base(volume)
            if item.get('content') == 'vztmpl' and name:
                found.setdefault(volume, {'nombre': name, 'nodes': []})['nodes'].append(node)
    async with bloqueo_capacidad(db):
        rows = list((await db.scalars(select(RecursoTemplate).with_for_update())).all())
        managed = {row.os_template: row for row in rows if es_base(row)}
        for volume, item in found.items():
            row = managed.get(volume)
            if not row:
                name = item['nombre']
                if any(existing.nombre == name for existing in rows):
                    name += ' · ' + volume.split('/', 1)[1].removesuffix('.tar.zst').removesuffix('.tar.gz').removesuffix('.tar.xz')
                row = RecursoTemplate(nombre=name[:100], descripcion=f"Entorno {item['nombre']} para las prácticas de la cátedra.",
                    modelo_servicio=ModeloServicio.IAAS, tipo=TipoRecurso.LXC, os_template=volume,
                    activo=True, revision=1, **{'default_' + key: value for key, value in TAMANOS['small'].items()})
                db.add(row)
                rows.append(row)
            row.config_extra = {'origen': 'proxmox_iaas', 'disponible': True, 'nodes': item['nodes']}
        for volume, row in managed.items():
            if volume not in found:
                row.config_extra = {**row.config_extra, 'disponible': False}
        await db.flush()
    return len(found)


async def validar_snapshot(assignment, destination, *, pve=None):
    if (assignment.get('origen') != 'proxmox_iaas' or assignment.get('tipo') != 'lxc'
        or assignment.get('modelo_servicio') != 'iaas' or assignment.get('definicion_version_id')
        or not nombre_base(assignment.get('image', {}).get('volume_id'))):
        raise error(409, 'base_iaas_invalida', 'La asignación no corresponde a una base Linux autorizada.')
    node = destination['nodo']
    if node not in get_settings().infrastructure_profile.get('nodos', {}):
        raise error(409, 'destino_no_permitido', 'El nodo no está autorizado.')
    volume = assignment['image']['volume_id']
    observed = await consultar('get_available_templates', node, volume.split(':', 1)[0], pve=pve)
    if observed.estado != 'presente' or not any(row.get('volid') == volume and row.get('content') == 'vztmpl' for row in observed.valor):
        raise error(409, 'imagen_no_disponible', 'La plantilla Linux ya no está disponible en el nodo elegido.')
    selected, profile = red(node)
    tag = profile.get('vlan_tag')
    if tag is not None and (type(tag) is not int or not 1 <= tag <= 4094):
        raise error(409, 'red_iaas_no_configurada', 'La red Linux tiene una VLAN inválida.')
    return {'net0': 'name=eth0,bridge=' + profile['bridge'] + ',ip=dhcp' + (f',tag={tag}' if tag else ''),
        'network_profile_id': selected, 'origen': 'proxmox_iaas'}
