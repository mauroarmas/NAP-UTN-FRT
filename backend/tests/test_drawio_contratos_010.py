import pytest
from fastapi import HTTPException
from app.schemas.definicion import validar_manifest
from tests.service_helpers import manifest


def test_schema_1_0_se_conserva():
    validar_manifest(manifest('linux'))


def test_drawio_incompleto_no_valida_y_producto_cerrado():
    from app.schemas.definicion import DefinicionCreate
    from pydantic import ValidationError
    with pytest.raises(ValidationError): DefinicionCreate(codigo='aplicacion',version='1.0.0',producto='cualquiera',modelo_servicio='saas')
    with pytest.raises(HTTPException): validar_manifest({'schema_version':'1.1','product':'drawio'})


def test_drawio_completo_exige_ensayo_sin_proveedor():
    from tests.drawio_helpers import drawio_manifest
    value=drawio_manifest()
    validar_manifest(value)
    value['validation']['checks'].remove('deployment_without_provider')
    with pytest.raises(HTTPException):validar_manifest(value)
