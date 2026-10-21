"""Inspección sin efectos. Los informes contienen códigos/IDs, nunca valores secretos."""
from datetime import datetime, timezone
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography import x509
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.utils.secretos import configured_keyring, SecretError


def _report(findings, **extra):
    return {'apto':not any(h.get('nivel','error')=='error' for h in findings),
        'hallazgos':findings,**extra}


def _origin(value):
    try:
        parsed=urlsplit(value)
        host=parsed.hostname
        if (parsed.scheme!='https' or not host or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or parsed.port==0
            or host=='localhost' or host.endswith('.localhost')):
            return False
        try:
            address=ipaddress.ip_address(host)
            if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
                return False
        except ValueError:
            if '.' not in host or not re.fullmatch(r'[a-zA-Z0-9.-]+',host):
                return False
        return True
    except (ValueError,TypeError):
        return False


def validar_configuracion(settings):
    """Sólo archivos públicos de CA y estructura de configuración; no red/DB."""
    findings=[]
    def issue(code,message): findings.append({'codigo':code,'mensaje':message,'nivel':'error'})
    if settings.app_env!='production': issue('entorno_no_operativo','Configurar APP_ENV=production para la puesta en servicio')
    if settings.app_debug: issue('debug_operativo','Desactivar trazas y SQL de depuración')
    if len(settings.secret_key)<32 or settings.secret_key.startswith('dev-secret'):
        issue('jwt_inseguro','Configurar clave JWT propia de al menos32caracteres')
    if len(settings.csrf_secret)<32 or settings.csrf_secret==settings.secret_key:
        issue('csrf_inseguro','Configurar clave CSRF independiente de JWT')
    try:
        configured_keyring(settings)
        if len(set(settings.secret_keyring.values()))!=len(settings.secret_keyring): raise SecretError()
    except (SecretError,ValueError,TypeError):
        issue('keyring_invalido','Instalar keyring válido, versionado e independiente de autenticación')
    if not _origin(settings.app_frontend_url):
        issue('frontend_origen_invalido','Usar origen HTTPS accesible desde el equipo visitante, sin ruta ni credenciales')
    origins=settings.auth_allowed_origins
    if not origins or any(not _origin(value) for value in origins) or settings.app_frontend_url not in origins:
        issue('origen_invalido','Declarar explícitamente los orígenes HTTPS autorizados')
    try:
        if not settings.trusted_proxy_networks or any(ipaddress.ip_network(value).prefixlen==0 for value in settings.trusted_proxy_networks):
            raise ValueError()
    except (TypeError,ValueError,ArgumentError):
        issue('proxy_no_delimitado','Declarar únicamente las redes de los proxies confiables')
    try:
        url=make_url(settings.database_url)
        if (url.drivername!='postgresql+asyncpg' or not url.host or not url.database or not url.username
            or not url.password or url.password in {'ps_password','password','postgres'}):
            raise ValueError()
    except (TypeError,ValueError,ArgumentError):
        issue('database_insegura','Configurar PostgreSQL con credenciales propias fuera del repositorio')
    if not settings.proxmox_token_value or not settings.proxmox_token_name:
        issue('pve_token_ausente','Falta token dedicado de infraestructura')
    if settings.proxmox_user in {'root@pam','root'}:
        issue('pve_usuario_privilegiado','Usar identidad institucional dedicada con permisos mínimos')
    if not settings.proxmox_host or '://' in settings.proxmox_host:
        issue('pve_host_invalido','Configurar hostname o IP del nodo, sin URL ni credenciales')
    if not settings.proxmox_verify_ssl:
        issue('pve_tls_no_verificado','La conexión PVE debe verificar TLS')
    try:
        path=Path(settings.proxmox_ca_file)
        if not settings.proxmox_ca_file or not path.is_file() or path.stat().st_size>1024*1024:
            raise ValueError()
        certificates=x509.load_pem_x509_certificates(path.read_bytes())
        now=datetime.now(timezone.utc)
        if not certificates or not any(c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
            and c.not_valid_before_utc<=now<c.not_valid_after_utc for c in certificates):
            raise ValueError()
    except (OSError,ValueError,TypeError,x509.ExtensionNotFound):
        issue('pve_ca_invalida','Montar una CA PEM vigente para verificar la conexión PVE')
    profile=settings.infrastructure_profile
    try:
        from uuid import UUID
        UUID(profile['cluster_id'])
        if profile.get('version')!=1 or not profile['nodos'] or not profile['almacenamientos']:
            raise ValueError()
        for node,entry in profile['nodos'].items():
            if (not isinstance(node,str) or not entry['storages']
                or any(storage not in profile['almacenamientos'] for storage in entry['storages'])
                or type(entry['margen_vcpus']) is not int or entry['margen_vcpus']<0
                or type(entry['margen_ram_mb']) is not int or entry['margen_ram_mb']<0): raise ValueError()
        for entry in profile['almacenamientos'].values():
            if (type(entry['shared']) is not bool or any(type(entry[k]) is not int or entry[k]<0
                for k in ['margen_logico_bytes','margen_fisico_bytes'])): raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):
        issue('perfil_infraestructura_incompleto','Configurar identidad del clúster, destinos y márgenes verificables')
    try:
        ZoneInfo(settings.institutional_timezone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):
        issue('zona_horaria_invalida','Configurar zona IANA institucional')
    if (not settings.smtp_host or not settings.smtp_from or not settings.smtp_user or not settings.smtp_password
        or not (settings.smtp_tls ^ settings.smtp_ssl)):
        issue('smtp_incompleto','Configurar entrega SMTP autenticada y un único modo TLS')
    # La disponibilidad de cada oferta se verifica además contra sus artefactos
    # al inspeccionar DB. Un registro vacío es válido si aún no hay ofertas.
    for key,entry in settings.service_artifacts.items():
        try:
            if (not entry['nodes'] or any(n not in settings.runner_nodes for n in entry['nodes'])
                or entry['network_profile_id'] not in settings.network_profiles): raise ValueError()
        except (KeyError,ValueError,TypeError):
            issue('preparacion_incompleta','Cada artefacto ofrecido requiere nodos, runner y perfil de red')
    return _report(findings,alcance='configuracion_sin_conexion_externa')


async def inspeccionar_datos(db):
    """Acepta esquema legacy o actual. Nunca completa campos ni reclama recursos."""
    connection=await db.connection()
    tables=await connection.run_sync(lambda c:set(inspect(c).get_table_names()))
    findings=[]
    def issue(code,ids,message):
        values=list(ids)
        if values: findings.append({'codigo':code,'ids':values[:100],'total':len(values),'mensaje':message,'nivel':'error'})
    if not {'usuarios','servicios','pedidos'}<=tables:
        return _report([{'codigo':'esquema_incompleto','mensaje':'Aplicar migraciones aditivas sobre una copia antes de regularizar','nivel':'error'}])
    async def rows(table,allowed):
        columns=await connection.run_sync(lambda c:{col['name'] for col in inspect(c).get_columns(table)})
        selected=[name for name in allowed if name in columns]
        result=[dict(r) for r in (await db.execute(text('SELECT '+','.join(selected)+' FROM '+table))).mappings()]
        for row in result:
            if isinstance(row.get('asignacion_snapshot'),str):
                try: row['asignacion_snapshot']=json.loads(row['asignacion_snapshot'])
                except (ValueError,TypeError): row['asignacion_snapshot']=None
        return result
    services=await rows('servicios',['id','proxmox_vmid','proxmox_node','tipo','deleted_at','vence_at',
        'identidad_infraestructura_id','asignacion_snapshot','vcpus_asignados','ram_asignada_mb','disk_asignado_gb'])
    active=[r for r in services if r.get('deleted_at') is None]
    groups={}
    invalid=[]
    for row in active:
        vmid=row.get('proxmox_vmid')
        if vmid is None: continue
        try:
            if not isinstance(vmid,str) or not vmid.isascii() or not vmid.isdecimal() or int(vmid)<=0:
                raise ValueError()
            # VMID es global en un clúster, no por nodo. Normalizar sólo para
            # detectar conflicto; conservar la cadena original en la base.
            groups.setdefault(int(vmid),[]).append(row['id'])
        except (ValueError,TypeError): invalid.append(row['id'])
    issue('vmid_invalido',invalid,'Resolver identificadores heredados mediante decisión institucional')
    issue('vmid_duplicado',[identity for values in groups.values() if len(values)>1 for identity in values],
        'Hay varios registros vigentes para un mismo recurso; no adoptar ni borrar automáticamente')
    issue('recursos_invalidos',[r['id'] for r in services if any(type(r.get(k)) is not int or r[k]<=0
        for k in ['vcpus_asignados','ram_asignada_mb','disk_asignado_gb'])],
        'Las cantidades deben ser positivas y contrastarse sin borrar historia')
    if 'recurso_templates' in tables:
        profiles=await rows('recurso_templates',['id','default_vcpus','default_ram_mb','default_disk_gb'])
        issue('perfil_recursos_invalidos',[r['id'] for r in profiles if any(type(r.get(k)) is not int or r[k]<=0
            for k in ['default_vcpus','default_ram_mb','default_disk_gb'])],'Regularizar cantidades del perfil antes de aplicar restricciones positivas')
    periods=[]
    if 'vigencias_autorizadas' in tables:
        periods=await rows('vigencias_autorizadas',['id','servicio_id','inicio_at','fin_exclusivo_at','revocada_at'])
    covered={p['servicio_id'] for p in periods if p['servicio_id'] and p.get('revocada_at') is None}
    issue('vigencia_sin_regularizar',[r['id'] for r in active if r['id'] not in covered],
        'Se requieren fechas comprobadas; deployed_at no acredita la duración autorizada')
    identities=[]
    if 'identidades_infraestructura' in tables:
        identities=await rows('identidades_infraestructura',['id','servicio_id','ownership_verificada_at','ausencia_confirmada_at','estado'])
    owners={str(r['id']):r for r in identities}
    issue('propiedad_sin_verificar',[r['id'] for r in active if not r.get('identidad_infraestructura_id')
        or str(r['identidad_infraestructura_id']) not in owners
        or not owners[str(r['identidad_infraestructura_id'])].get('ownership_verificada_at')
        or owners[str(r['identidad_infraestructura_id'])].get('servicio_id')!=r['id']],
        'El nombre, VMID o nodo por sí solos no prueban pertenencia')
    issue('asignacion_sin_regularizar',[r['id'] for r in active if not r.get('asignacion_snapshot')],
        'Conservar cantidades autorizadas conocidas; no copiar una plantilla actualmente editable')
    users=await rows('usuarios',['id','totp_habilitado','totp_secret_encrypted','habilitacion_inconsistente'])
    issue('mfa_inconsistente',[r['id'] for r in users if r.get('habilitacion_inconsistente')
        or (r['totp_habilitado'] and not r.get('totp_secret_encrypted'))],
        'Conservar el factor activo y tramitar recuperación de la identidad; nunca desactivarlo por migración')
    requests=await rows('pedidos',['id','estado','deleted_at','asignacion_snapshot','revision','revision_decision','tipo','servicio_id'])
    issue('pedido_revisiones_invalidas',[r['id'] for r in requests if ('revision' in r and (type(r['revision']) is not int or r['revision']<1))
        or ('revision_decision' in r and (type(r['revision_decision']) is not int or r['revision_decision']<0))],
        'Revisar revisiones históricas antes del cierre de esquema')
    issue('pedido_tipo_servicio_incoherente',[r['id'] for r in requests if ('tipo' in r and
        not (str(r['tipo']).lower()=='alta'
            or (str(r['tipo']).lower()=='renovacion' and r.get('servicio_id') is not None)))],
        'Recuperar la relación del servicio renovado sin cambiar pertenencias ni borrar historia')
    issue('despliegue_legacy_incierto',[r['id'] for r in requests if str(r['estado']).lower() in {'en_despliegue','error'}
        and r.get('deleted_at') is None and (not isinstance(r.get('asignacion_snapshot'),dict)
            or r['asignacion_snapshot'].get('origen')=='legado_cantidades_autorizadas')],
        'Reconciliar tarea/recurso antes de liberar capacidad o volver a crear')
    return _report(findings,alcance='base_sin_cambios_ni_consultas_pve',
        cantidades={'usuarios':len(users),'servicios':len(services),'servicios_vigentes':len(active),'pedidos':len(requests)})


async def inspeccionar_claves(db):
    """Comprueba claves restaurables sin devolver tokens ni valores descifrados."""
    from uuid import UUID
    findings=[]
    try:
        keyring=configured_keyring()
    except SecretError:
        return _report([{'codigo':'keyring_invalido','mensaje':'Instalar claves externas antes de inspeccionar secretos','nivel':'error'}])
    connection=await db.connection()
    tables=await connection.run_sync(lambda c:set(inspect(c).get_table_names()))
    groups=[('usuarios','totp_secret_encrypted',lambda r:f"totp:{r['id']}",[]),
        ('servicios','credenciales_encrypted',lambda r:f"servicio:{r['id']}:secretos",[]),
        ('identidades_infraestructura','nonce_cifrado',lambda r:f"infra:{UUID(str(r['resource_uuid']))}:nonce",['resource_uuid']),
        ('desafios_autenticacion','secreto_pendiente_cifrado',lambda r:f"totp-pending:{UUID(str(r['id']))}",[]),
        ('notificaciones','destinatario_email_cifrado',lambda r:f"email:{UUID(str(r['id']))}",[]),
        ('notificaciones','secreto_temporal_encrypted',lambda r:f"welcome:{UUID(str(r['id']))}",[]),
        ('bitacora_cierre','legado_cifrado',lambda r:f"cierre:{UUID(str(r['id']))}:legado",[])]
    checked=0
    for table,column,context,extra in groups:
        if table not in tables: continue
        columns=await connection.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns(table)})
        if column not in columns: continue
        rows=(await db.execute(text('SELECT id,'+column+(' ,'+','.join(extra) if extra else '')+
            ' FROM '+table+' WHERE '+column+' IS NOT NULL'))).mappings()
        for row in rows:
            checked+=1
            try:
                value=keyring.decrypt(row[column],context=context(row))
                # Se descarta el valor sin incorporarlo al informe/logs.
                del value
            except (SecretError,ValueError,TypeError):
                findings.append({'codigo':'secreto_no_descifrable','tabla':table,'id':str(row['id']),
                    'mensaje':'Recuperar la versión de keyring y contexto necesarios antes de migrar/restaurar','nivel':'error'})
    for table,column in [('usuarios','totp_secret'),('servicios','credenciales_acceso')]:
        if table not in tables: continue
        columns=await connection.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns(table)})
        if column not in columns: continue
        ids=(await db.execute(text('SELECT id FROM '+table+' WHERE '+column+" IS NOT NULL AND CAST("+column+" AS TEXT) != 'null'"))).scalars().all()
        if ids: findings.append({'codigo':'secreto_legacy_en_claro','tabla':table,'ids':ids[:100],
            'mensaje':'Migrar material legado de forma tipada y comprobada antes de retirar columnas','nivel':'error'})
    return _report(findings,alcance='descifrado_local_sin_revelado',secretos_comprobados=checked)


async def inspeccionar_ofertas(db):
    """Valida manifiestos/evidencia y archivos locales sin SELECT FOR UPDATE ni PVE."""
    import hashlib
    from uuid import UUID
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.config import get_settings
    from app.models.definicion_servicio import DefinicionServicio
    from app.models.evidencia import Evidencia
    from app.schemas.definicion import validar_manifest, digest
    from app.schemas.evidencia import parse_document, canonical
    from app.services import infraestructura_io
    from app.services.catalogo_service import hash_archivo_controlado
    from app.services.evidencia_service import BASE_CHECKS
    from app.utils.clock import clock, db_utc
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    settings=get_settings();findings=[]
    connection=await db.connection()
    tables=await connection.run_sync(lambda c:set(inspect(c).get_table_names()))
    if 'definiciones_servicio' not in tables:
        return _report([],alcance='catalogo_legacy_sin_ofertas',versiones_comprobadas=0)
    definitions=list((await db.scalars(select(DefinicionServicio).where(DefinicionServicio.estado.in_(['publicada','retirada'])))).all())
    for definition in definitions:
        def issue(code,message): findings.append({'codigo':code,'definicion_id':str(definition.id),'mensaje':message,'nivel':'error'})
        value=definition.manifest
        try:
            validar_manifest(value)
            if (definition.manifest_sha256!=digest(value) or
                (definition.codigo,definition.version,definition.producto,definition.modelo_servicio)!=
                (value['definition_key'],value['definition_version'],value['product'],value['service_model'])):
                raise ValueError()
            reference=value['validation'];entry=await db.get(Evidencia,UUID(reference['evidence_id']))
            if not entry or entry.id!=definition.evidencia_validacion: raise ValueError()
            document=parse_document(entry.documento_canonico.encode());proof=document['resultado']
            checksum=hashlib.sha256(canonical(document).encode()).hexdigest()
            required=BASE_CHECKS|({'unique_secrets'} if definition.producto in {'postgresql','bookstack'} else set())
            if definition.producto=='bookstack': required|={'reader_permissions_and_revocation'}
            observed=datetime.fromisoformat(document['observado_at'].replace('Z','+00:00'))
            if (entry.tipo!='validacion_definicion' or checksum!=entry.sha256 or checksum!=reference['evidence_sha256']
                or proof['definicion_id']!=str(definition.id) or proof['definition_key']!=definition.codigo
                or proof['definition_version']!=definition.version or proof['image_sha256']!=value['image']['sha256']
                or proof['recipe_sha256']!=value['preparation']['bundle_sha256']
                or proof['cluster_uuid']!=reference['cluster_uuid']
                or sorted(proof['pve_versions'])!=sorted(reference['pve_versions'])
                or len(proof['instancias'])!=reference['instances_tested']
                or set(proof['checks'])!=set(reference['checks'])
                or not required<=set(proof['checks']) or db_utc(observed)>clock.now()
                or observed!=datetime.fromisoformat(reference['validated_at'].replace('Z','+00:00'))
                or (document['entorno']!='real' and settings.app_env!='test')): raise ValueError()
        except (HTTPException,ValueError,TypeError,KeyError):
            issue('definicion_no_verificable','Revisar identidad, digest y evidencia de la versión; no se habilita por inferencia')
            continue
        try:
            registry=settings.service_artifacts[definition.codigo+':'+definition.version]
            if registry.get('security_blocked'): raise ValueError()
            for field,expected in [('image_path',value['image']['sha256']),('bundle_path',value['preparation']['bundle_sha256'])]:
                actual=await infraestructura_io.ejecutar(hash_archivo_controlado,registry[field],timeout=180)
                if actual!=expected: raise ValueError()
            if settings.infrastructure_profile['cluster_id']!=reference['cluster_uuid']: raise ValueError()
            if not registry['nodes'] or registry['network_profile_id'] not in value['network_profile_ids']: raise ValueError()
            runner=GuestRunnerClient()
            for node in registry['nodes']: runner.validar_destino(node)
            for key in value['network_profile_ids']:
                profile=settings.network_profiles[key]
                if (not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}',profile['bridge'])
                    or not set(registry['nodes'])<=set(profile['nodes'])
                    or not profile['allowed_cidrs'] or not profile['client_cidrs']): raise ValueError()
                for cidr in profile['allowed_cidrs']+profile['client_cidrs']:
                    if ipaddress.ip_network(cidr).prefixlen==0: raise ValueError()
        except (KeyError,ValueError,TypeError,RunnerError,infraestructura_io.InfraNoVerificable):
            issue('preparacion_no_verificable','Revisar archivos/digests, destino del runner, red y clúster de la versión')
    return _report(findings,alcance='catalogo_y_archivos_sin_efectos',versiones_comprobadas=len(definitions))


async def inspeccionar_infraestructura(db,*,pve=None):
    """Sondeo explícito y acotado de inventario/propiedad; jamás adopta ni corrige."""
    from sqlalchemy import select
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.services import infraestructura_io, inventario_service, identidad_infra_service
    findings=[]
    try:
        inventory=await infraestructura_io.con_cliente(inventario_service.observar,pve=pve,timeout=30)
    except Exception:
        return _report([{'codigo':'inventario_no_verificable','mensaje':'No se confirmó inventario; el fallo no acredita ausencia','nivel':'error'}])
    identities=list((await db.scalars(select(IdentidadInfraestructura).where(
        IdentidadInfraestructura.ausencia_confirmada_at.is_(None)))).all())
    for identity in identities:
        try:
            observation=await identidad_infra_service.observar(identity,pve=pve)
            if observation.estado!='propia':
                findings.append({'codigo':'propiedad_externa_no_confirmada','identidad_id':str(identity.id),
                    'resultado':observation.estado,'mensaje':'Conservar capacidad hasta regularización/reconciliación','nivel':'error'})
        except Exception:
            findings.append({'codigo':'propiedad_externa_no_verificable','identidad_id':str(identity.id),
                'mensaje':'El sondeo falló; no se libera ni cambia identidad','nivel':'error'})
    return _report(findings,alcance='inventario_externo_sin_mutaciones',
        identidades_comprobadas=len(identities),destinos_observados=len(inventory.get('destinos',[])))
