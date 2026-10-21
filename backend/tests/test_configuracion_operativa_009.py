"""Preflight debe informar faltantes sin contactar ni mutar infraestructura."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
from sqlalchemy import select, func

from app.config import Settings
from app.models.servicio import Servicio
from app.models.usuario import Usuario
from tests import factories


@pytest.fixture
def operational_settings(tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CA de prueba aislada')])
    certificate=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())\
        .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))\
        .not_valid_after(datetime.now(timezone.utc)+timedelta(days=30))\
        .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256())
    ca=tmp_path/'ca.pem';ca.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return Settings(_env_file=None,_env_prefix='ISOLATED_SETTINGS_',app_env='production',app_debug=False,
        database_url='postgresql+asyncpg://nap:database-fixture-secret@database/nap',
        secret_key='jwt-independent-'+('j'*40),csrf_secret='csrf-independent-'+('c'*40),
        secret_keyring={'one':Fernet.generate_key().decode()},secret_active_key='one',
        app_frontend_url='https://nap.example.org',auth_allowed_origins=['https://nap.example.org'],
        trusted_proxy_networks=['172.25.0.0/24'],proxmox_host='pve.example.org',proxmox_user='nap@pve',
        proxmox_token_name='portal',proxmox_token_value='proxmox-fixture-secret-'+('p'*32),
        proxmox_verify_ssl=True,proxmox_ca_file=str(ca),smtp_host='smtp.example.org',smtp_user='portal',
        smtp_password='smtp-fixture-secret',smtp_from='nap@example.org',smtp_tls=True,
        infrastructure_profile={'version':1,'cluster_id':str(uuid4()),'nodos':{'pve1':{
            'margen_vcpus':1,'margen_ram_mb':512,'storages':['local-lvm']}},
            'almacenamientos':{'local-lvm':{'shared':False,'margen_logico_bytes':0,'margen_fisico_bytes':0}}})


def test_complete_configuration_is_read_only_and_does_not_contact_services(operational_settings):
    from app.services.preflight_service import validar_configuracion
    report=validar_configuracion(operational_settings)
    assert report['apto'] is True,report
    assert not report['hallazgos']


@pytest.mark.parametrize('field,value,code',[
    ('secret_key','dev-secret-key-change-in-production-please','jwt_inseguro'),
    ('csrf_secret','','csrf_inseguro'),
    ('secret_keyring',{},'keyring_invalido'),
    ('auth_allowed_origins',['*'],'origen_invalido'),
    ('proxmox_verify_ssl',False,'pve_tls_no_verificado'),
    ('proxmox_ca_file','/no/existe/ca.pem','pve_ca_invalida'),
    ('proxmox_token_value','','pve_token_ausente'),
    ('infrastructure_profile',{},'perfil_infraestructura_incompleto'),
    ('smtp_host','','smtp_incompleto'),
    ('app_debug',True,'debug_operativo'),
])
def test_missing_operational_parts_are_explicit_without_secrets(operational_settings,field,value,code):
    from app.services.preflight_service import validar_configuracion
    report=validar_configuracion(operational_settings.model_copy(update={field:value}))
    assert report['apto'] is False
    assert code in {h['codigo'] for h in report['hallazgos']}
    rendered=str(report)
    for secret in [operational_settings.secret_key,operational_settings.csrf_secret,
            operational_settings.proxmox_token_value,operational_settings.smtp_password,'database-fixture-secret']:
        assert secret not in rendered


@pytest.mark.parametrize('url',['http://localhost:5173','https://127.0.0.1','https://[::1]',
    'https://0.0.0.0','https://localhost','https://admin:private@nap.example.org','https://nap.example.org/subpath'])
def test_visitor_url_must_be_a_real_https_origin(operational_settings,url):
    from app.services.preflight_service import validar_configuracion
    report=validar_configuracion(operational_settings.model_copy(update={'app_frontend_url':url}))
    assert not report['apto']
    assert 'frontend_origen_invalido' in {h['codigo'] for h in report['hallazgos']}
    assert 'private' not in str(report)


async def test_preflight_reports_duplicate_vmid_unknown_dates_and_ownership_without_backfill(db,admin,catedra,template):
    from app.services.preflight_service import inspeccionar_datos
    first=await factories.crear_servicio(db,catedra.id,template.id,proxmox_vmid='100')
    second=await factories.crear_servicio(db,catedra.id,template.id,proxmox_vmid='0100')
    report=await inspeccionar_datos(db)
    codes={h['codigo'] for h in report['hallazgos']}
    assert {'vmid_duplicado','vigencia_sin_regularizar','propiedad_sin_verificar'}<=codes
    assert not report['apto']
    await db.refresh(first);await db.refresh(second)
    assert first.vence_at is None and second.identidad_infraestructura_id is None
    assert await db.scalar(select(func.count()).select_from(Servicio))==2


async def test_api_restart_does_not_seed_accounts_or_change_passwords(db,admin):
    from app.main import app
    previous=admin.password_hash
    async with app.router.lifespan_context(app): pass
    async with app.router.lifespan_context(app): pass
    await db.refresh(admin)
    assert admin.password_hash==previous
    assert await db.scalar(select(func.count()).select_from(Usuario))==1


async def test_unreadable_encryption_is_reported_without_token_or_mutation(db,admin):
    from app.services.preflight_service import inspeccionar_claves
    token='private-opaque-fixture-that-must-not-be-logged'
    admin.totp_secret_encrypted=token
    await db.commit()
    report=await inspeccionar_claves(db)
    assert not report['apto'] and report['hallazgos'][0]['codigo']=='secreto_no_descifrable'
    assert token not in str(report)
    await db.refresh(admin);assert admin.totp_secret_encrypted==token


async def test_live_inventory_failure_never_proves_absence_or_changes_services(db,catedra,template,proxmox):
    from app.services.preflight_service import inspeccionar_infraestructura
    service=await factories.crear_servicio(db,catedra.id,template.id)
    proxmox.fallar_recursos=RuntimeError('private-transport-value')
    report=await inspeccionar_infraestructura(db,pve=proxmox)
    assert not report['apto'] and report['hallazgos'][0]['codigo']=='inventario_no_verificable'
    assert 'private-transport-value' not in str(report)
    await db.refresh(service);assert service.deleted_at is None


def test_pve_transport_receives_mounted_ca_when_verification_is_enabled(operational_settings,monkeypatch):
    from app.services import proxmox_client
    captured={}
    def transport(host,**kwargs): captured.update(kwargs);return object()
    monkeypatch.setattr(proxmox_client,'ProxmoxAPI',transport)
    proxmox_client.ProxmoxClient(operational_settings)
    assert captured['verify_ssl']==operational_settings.proxmox_ca_file


@pytest.fixture
async def validated_offer(db,admin,tmp_path,monkeypatch):
    """Artefactos/digests reales, observación explícitamente SIMULADA para test."""
    import hashlib
    from app.models.definicion_servicio import DefinicionServicio
    from app.models.evidencia import Evidencia
    from app.config import get_settings
    from app.schemas.definicion import digest
    from app.schemas.evidencia import canonical
    from tests.service_helpers import manifest,definition_proof
    value=manifest();identity,reference=uuid4(),uuid4()
    for key,field in [('image','image_path'),('bundle','bundle_path')]:
        path=tmp_path/key;path.write_bytes(('simulado-'+key).encode());path.chmod(0o444)
        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
        if key=='image': value['image']['sha256']=checksum
        else: value['preparation']['bundle_sha256']=checksum
    proof=definition_proof(identity,value);proof['entorno']='simulado'
    encoded=canonical(proof);checksum=hashlib.sha256(encoded.encode()).hexdigest()
    db.add(Evidencia(id=reference,tipo='validacion_definicion',schema_version=1,
        documento_canonico=encoded,sha256=checksum,registrada_por=admin.id))
    await db.flush();value['validation'].update(evidence_id=str(reference),evidence_sha256=checksum)
    definition=DefinicionServicio(id=identity,codigo=value['definition_key'],version='1.0.0',producto='linux',
        modelo_servicio='iaas',manifest=value,manifest_sha256=digest(value),estado='publicada',
        validada_por=admin.id,validada_at=datetime.now(timezone.utc),evidencia_validacion=reference)
    db.add(definition);await db.commit()
    private=tmp_path/'key';private.write_text('fake-key-not-used');private.chmod(0o600)
    hosts=tmp_path/'known_hosts';hosts.write_text('pve-test.invalid ssh-ed25519 TEST-ONLY');hosts.chmod(0o644)
    settings=get_settings()
    monkeypatch.setattr(settings,'app_env','test')
    monkeypatch.setattr(settings,'infrastructure_profile',{'cluster_id':value['validation']['cluster_uuid']})
    monkeypatch.setattr(settings,'service_artifacts',{value['definition_key']+':1.0.0':{
        'nodes':['pve1'],'network_profile_id':'test-network','image_path':str(tmp_path/'image'),'bundle_path':str(tmp_path/'bundle')}})
    monkeypatch.setattr(settings,'network_profiles',{'test-network':{'bridge':'vmbr0','nodes':['pve1'],
        'allowed_cidrs':['10.50.0.0/24'],'client_cidrs':['10.50.0.0/24']}})
    monkeypatch.setattr(settings,'runner_nodes',{'pve1':{'host':'pve-test.invalid','user':'naprunner','port':22,
        'private_key_path':str(private),'known_hosts_path':str(hosts)}})
    return definition


async def test_offer_preflight_checks_artifacts_and_keeps_corruption_visible(db,validated_offer,tmp_path):
    from app.services.preflight_service import inspeccionar_ofertas
    assert (await inspeccionar_ofertas(db))['apto']
    image=tmp_path/'image';image.chmod(0o600);image.write_text('contenido-alterado-privado');image.chmod(0o444)
    report=await inspeccionar_ofertas(db)
    assert not report['apto'] and report['hallazgos'][0]['codigo']=='preparacion_no_verificable'
    assert 'contenido-alterado-privado' not in str(report)
