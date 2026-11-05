from fastapi import HTTPException
import pytest

from app.config import Settings
from app.services.application_profiles_service import require_profile, profile_capabilities


def test_backend_empty_registry_is_explicit_not_an_implicit_docker_profile():
    settings = Settings(_env_file=None)
    assert settings.application_profiles == {}
    assert profile_capabilities(settings=settings) == []
    with pytest.raises(HTTPException) as caught:
        require_profile({'id': 'docker-ubuntu24', 'revision': 1, 'sha256': 'a'*64}, settings=settings)
    assert caught.value.status_code == 409
    assert caught.value.detail['codigo'] == 'perfil_aplicacion_no_disponible'
