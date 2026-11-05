import pytest
from pydantic import ValidationError
from uuid import uuid4

from app.schemas.template import TemplateCreate, TemplateResponse
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from app.schemas.catedra import CatedraCreate


@pytest.mark.parametrize('field,value', [('default_vcpus', 0), ('default_ram_mb', -1), ('default_disk_gb', True), ('default_vcpus', '2')])
def test_resource_profile_rejects_nonpositive_or_coerced_numbers(field, value):
    with pytest.raises(ValidationError):
        TemplateCreate(nombre='Perfil', definicion_version_id=uuid4(), **{field: value})


def test_new_profiles_only_lxc_and_never_accept_invariant_overrides():
    for payload in [{'tipo': 'qemu'}, {'config_extra': {'vmid': 100}}, {'force': True}]:
        with pytest.raises(ValidationError):
            TemplateCreate(nombre='Perfil', definicion_version_id=uuid4(), **payload)
    assert TemplateCreate(nombre='Disco grande', definicion_version_id=uuid4(), default_disk_gb=500).default_disk_gb == 500
    assert TemplateResponse(id=1, nombre='Histórica', tipo='qemu', activo=False).tipo == 'qemu'


def test_email_and_required_names_are_validated_for_all_writes():
    with pytest.raises(ValidationError):
        UsuarioCreate(username='docente', nombre='Nombre', email='not-an-email')
    with pytest.raises(ValidationError):
        UsuarioUpdate(email='not-an-email')
    with pytest.raises(ValidationError):
        UsuarioUpdate(nombre=None)
    with pytest.raises(ValidationError):
        CatedraCreate(nombre='   ')
    assert UsuarioCreate(username='docente', nombre='Nombre', email='DOCENTE@EXAMPLE.ORG').email == 'docente@example.org'
