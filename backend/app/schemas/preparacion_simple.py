from pydantic import Field
from app.schemas.common import Contrato
from app.schemas.tamanos import Tamano

SIMPLE_CHECKS = {'image_digest', 'sanitized_image', 'repeatable_deployment', 'functional_access',
                 'student_network_access', 'unique_secrets', 'authorized_perimeter', 'simple_verification'}
AUTOMATIC_CHECKS = (SIMPLE_CHECKS - {'student_network_access', 'simple_verification'}) | {'automatic_verification'}


class PublicarAplicacion(Contrato):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str = Field(default='', max_length=2000)
    tamano: Tamano


class PrepararAplicacion(Contrato):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str = Field(default='', max_length=2000)
    tamano: Tamano = 'small'
