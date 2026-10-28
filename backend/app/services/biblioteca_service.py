"""Búsqueda en Docker Hub y preservación de incorporaciones históricas."""
import base64
from copy import deepcopy
import hashlib
import json
from uuid import UUID

import httpx
from sqlalchemy import select, text

from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.models.evento_seguridad import EventoSeguridad
from app.services.acceso_service import requiere_admin_actual
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.errors import error

DOCKER_HUB_SEARCH_URL = 'https://hub.docker.com/v2/search/repositories/'


class DockerHubError(Exception):
    pass


class DockerHubRateLimitError(DockerHubError):
    pass


class DockerHubUnavailableError(DockerHubError):
    pass


async def docker_hub_search(query: str, *, page: int = 1, page_size: int = 20) -> dict:
    """Consulta la API de búsqueda de repositorios de Docker Hub con límites y timeout."""
    params = {'query': query, 'page': page, 'page_size': min(max(page_size, 1), 100)}
    headers = {'Accept': 'application/json', 'User-Agent': 'NAP-Portal/1.0'}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get(DOCKER_HUB_SEARCH_URL, params=params, headers=headers)
            if response.status_code == 429:
                raise DockerHubRateLimitError('Rate limit exceeded on Docker Hub')
            if response.status_code != 200:
                raise DockerHubUnavailableError(f'Docker Hub returned status {response.status_code}')
            return response.json()
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        raise DockerHubUnavailableError(str(exc)) from exc


def present(row):
    value = {key: deepcopy(getattr(row, key)) for key in ['proveedor', 'identidad_externa', 'revision_fuente', 'version_externa',
        'nombre', 'descripcion', 'categorias', 'aliases', 'comando_origen', 'url_origen', 'comando_sha256', 'revision', 'datos_origen']}
    value.update(
        id=str(row.id),
        created_at=row.created_at.isoformat(),
        faltantes=[key for key in ['descripcion', 'version_externa'] if not getattr(row, key)],
        compatibilidad=row.datos_origen.get('compatibilidad', 'sin_comprobar') if row.datos_origen else 'sin_comprobar'
    )
    return value


def paginate(items, *, query, limit, cursor, revision):
    fingerprint = hashlib.sha256(json.dumps([query, revision], sort_keys=True).encode()).hexdigest()
    offset = 0
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if set(value) != {'offset', 'fingerprint'} or value['fingerprint'] != fingerprint or type(value['offset']) is not int or value['offset'] < 0:
                raise ValueError()
            offset = value['offset']
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise error(409, 'cursor_desactualizado', 'La búsqueda cambió; volvé a consultar') from None
    after = offset + limit
    next_cursor = base64.urlsafe_b64encode(json.dumps({'offset': after, 'fingerprint': fingerprint}).encode()).decode() if after < len(items) else None
    return {'items': items[offset:after], 'next_cursor': next_cursor}


async def buscar(db, *, actor, filters):
    """Descubrimiento de imágenes en Docker Hub para el motor OCI común."""
    await requiere_admin_actual(db, actor)
    q = (filters.q or '').strip()
    if not q:
        raise error(422, 'busqueda_requerida', 'Indicá un término de búsqueda para consultar la biblioteca.')

    page = 1
    fingerprint = hashlib.sha256(q.casefold().encode()).hexdigest()
    if filters.cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(filters.cursor.encode()))
            if set(value) != {'page', 'fingerprint'} or value['fingerprint'] != fingerprint or type(value['page']) is not int or value['page'] < 1:
                raise ValueError()
            page = value['page']
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise error(409, 'cursor_desactualizado', 'La búsqueda cambió; volvé a consultar') from None

    page_size = min(max(filters.limit, 1), 100)
    try:
        data = await docker_hub_search(q, page=page, page_size=page_size)
    except DockerHubRateLimitError:
        raise error(429, 'limite_consultas_proveedor', 'Se superó el límite de consultas a Docker Hub. Esperá unos momentos o ingresá la referencia directamente.')
    except DockerHubUnavailableError:
        raise error(502, 'proveedor_no_disponible', 'No se pudo consultar Docker Hub. Podés reintentar o ingresar la referencia de la imagen manualmente.')

    count = data.get('count', 0)
    results = data.get('results', [])
    items = []
    for r in results:
        repo_name = r.get('repo_name', '')
        is_official = bool(r.get('is_official'))
        is_automated = bool(r.get('is_automated'))
        distintivos = []
        if is_official:
            distintivos.append('oficial')
        if is_automated:
            distintivos.append('automatizado')
        items.append({
            'nombre': repo_name,
            'repositorio': repo_name,
            'referencia': repo_name if ':' in repo_name else f'{repo_name}:latest',
            'descripcion': r.get('short_description') or None,
            'procedencia': 'oficial' if is_official else 'comunidad',
            'distintivos': distintivos,
            'estrellas': r.get('star_count', 0),
            'descargas': r.get('pull_count', 0),
            'categorias': [],
        })

    next_cursor = None
    if data.get('next') and len(items) == page_size and (page * page_size) < count:
        next_cursor = base64.urlsafe_b64encode(json.dumps({'page': page + 1, 'fingerprint': fingerprint}).encode()).decode()

    return {
        'items': items,
        'next_cursor': next_cursor,
        'total': count,
        'fuente': {'proveedor': 'docker_hub', 'endpoint': DOCKER_HUB_SEARCH_URL},
    }


async def categorias(db, *, actor):
    """Categorías de Docker Hub; lista vacía ya que la API no las expone estructuradas."""
    await requiere_admin_actual(db, actor)
    return {'items': [], 'fuente': {'proveedor': 'docker_hub'}}


async def incorporar(db, *, actor, data, clave):
    """Rechazo explícito de nuevas incorporaciones Community Scripts."""
    await requiere_admin_actual(db, actor)
    raise error(422, 'community_scripts_retirado', 'Community Scripts se retiró del alcance. Utilizá Docker Hub o ingresá una imagen propia.')


async def obtener(db, identity, *, actor, bloquear=False):
    """Consulta de incorporación histórica para auditoría o Draw.io."""
    await requiere_admin_actual(db, actor)
    query = select(IncorporacionAplicacion).where(IncorporacionAplicacion.id == identity).execution_options(populate_existing=True)
    if bloquear:
        query = query.with_for_update()
    row = await db.scalar(query)
    if not row:
        raise error(404, 'incorporacion_no_encontrada', 'Incorporación no encontrada')
    return row


async def listar(db, *, actor, filters):
    """Lista de incorporaciones históricas conservadas en base de datos."""
    await requiere_admin_actual(db, actor)
    rows = list((await db.scalars(select(IncorporacionAplicacion).order_by(IncorporacionAplicacion.created_at, IncorporacionAplicacion.id))).all())
    revision = hashlib.sha256(str([(str(r.id), r.revision) for r in rows]).encode()).hexdigest()
    return paginate([present(r) for r in rows], query='incorporaciones', limit=filters.limit, cursor=filters.cursor, revision=revision)


async def editar(db, identity, *, actor, data, clave):
    actor = await requiere_admin_actual(db, actor)
    async def decide(session):
        row = await obtener(session, identity, actor=actor, bloquear=True)
        if row.revision != data.revision_esperada:
            raise error(409, 'revision_desactualizada', 'La ficha cambió; revisá los datos', revision=row.revision)
        for key, value in data.model_dump(exclude_unset=True).items():
            if key == 'revision_esperada':
                continue
            if key == 'nombre' and (value is None or not value.strip()):
                raise error(422, 'datos_invalidos', 'Indicá un nombre válido')
            if key in {'aliases', 'categorias'} and value is None:
                value = []
            setattr(row, key, value)
        row.revision += 1
        await session.flush()
        session.add(EventoSeguridad(actor_usuario_id=actor.id, accion='editar_incorporacion', resultado='completado', referencia=str(row.id)))
        return ResultadoDecision(200, present(row))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='PATCH', ruta=f'/biblioteca/incorporaciones/{identity}', payload=data.model_dump(exclude_unset=True), decidir=decide)
