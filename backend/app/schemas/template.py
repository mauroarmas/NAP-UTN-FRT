from pydantic import BaseModel, Field, StrictInt, ConfigDict, field_validator, model_validator
from typing import Literal
import re
from uuid import UUID
from app.schemas.common import Contrato
from app.schemas.tamanos import Tamano, validar_tamano


class TemplateBase(BaseModel):
    nombre: str
    descripcion: str | None = None
    modelo_servicio: str = "iaas"
    tipo: str = "lxc"
    default_vcpus: int = 1
    default_ram_mb: int = 256
    default_disk_gb: int = 2
    justificacion_disco: str | None = None
    os_template: str | None = None
    config_extra: dict | None = None


class TemplateCreate(TemplateBase, Contrato):
    tamano: Tamano | None = None
    definicion_version_id: UUID
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    modelo_servicio: Literal['iaas', 'paas', 'saas'] = 'iaas'
    tipo: Literal['lxc'] = 'lxc'
    default_vcpus: StrictInt = Field(default=1, ge=1, le=2**31-1)
    default_ram_mb: StrictInt = Field(default=256, ge=1, le=2**31-1)
    default_disk_gb: StrictInt = Field(default=2, ge=1, le=2**31-1)

    @model_validator(mode='after')
    def tamano_coherente(self):
        validar_tamano(self.tamano, {key: getattr(self, 'default_' + key) for key in ['vcpus', 'ram_mb', 'disk_gb']})
        return self

    @field_validator('nombre', mode='before')
    @classmethod
    def nonempty(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('config_extra')
    @classmethod
    def closed_options(cls, value):
        if value not in (None, {}):
            raise ValueError('La configuración de infraestructura procede de definiciones y perfiles validados')
        return value

    @field_validator('os_template')
    @classmethod
    def prepared_image_path(cls, value):
        if value is not None and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*:vztmpl/[A-Za-z0-9][A-Za-z0-9_.-]*\.tar\.(zst|xz|gz)', value):
            raise ValueError('Indicá una imagen preparada del almacenamiento autorizado')
        return value


class TemplateUpdate(BaseModel):
    """Corrección de una plantilla ya creada. Todos los campos son opcionales.

    `tipo` **no es editable** (regla T4): cambiar un contenedor por una máquina
    virtual altera la naturaleza de lo que se entrega y de lo que ya se aprobó
    sobre esa plantilla. Para eso corresponde una plantilla nueva. Figura abajo
    de todas formas para que el endpoint pueda rechazarlo diciendo por qué.
    """

    model_config = ConfigDict(extra='forbid')
    tamano: Tamano | None = None
    definicion_version_id: UUID | None = None
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    modelo_servicio: Literal['iaas', 'paas', 'saas'] | None = None
    # `tipo` figura acá **solo para poder rechazarlo con un mensaje que explique
    # por qué**. Dejarlo fuera del schema haría que Pydantic lo descartara en
    # silencio y el administrador creería haberlo cambiado.
    tipo: None = None
    default_vcpus: StrictInt | None = Field(default=None, ge=1, le=2**31-1)
    default_ram_mb: StrictInt | None = Field(default=None, ge=1, le=2**31-1)
    default_disk_gb: StrictInt | None = Field(default=None, ge=1, le=2**31-1)
    justificacion_disco: str | None = None
    os_template: str | None = None
    config_extra: dict | None = None
    activo: bool | None = None

    @field_validator('config_extra')
    @classmethod
    def closed_options(cls, value):
        return TemplateCreate.closed_options(value)

    @field_validator('os_template')
    @classmethod
    def prepared_image_path(cls, value):
        return TemplateCreate.prepared_image_path(value)

    @field_validator('nombre', 'modelo_servicio', 'default_vcpus', 'default_ram_mb', 'default_disk_gb', 'activo', 'definicion_version_id')
    @classmethod
    def explicit_required(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError('El campo no puede quedar vacío')
        return value.strip() if isinstance(value, str) else value


class AlcanceDelCambio(BaseModel):
    """Qué queda fuera del alcance de una corrección de plantilla (FR-003).

    Es informativo, nunca bloqueante: editar una plantilla no toca lo ya
    entregado ni lo ya aprobado, y el administrador merece saberlo en el momento
    en que edita, no descubrirlo después.
    """

    servicios_desplegados: int
    pedidos_aprobados_pendientes: int


class TemplateResponse(TemplateBase):
    configuracion_despliegue_id: UUID | None = None
    codigo_definicion: str | None = None
    revision: int = 1
    minimum_resources: dict[str, int] | None = None
    tamanos_permitidos: list[Tamano] = Field(default_factory=list)
    tamano_recomendado: Tamano | None = None
    origen_biblioteca: bool = False
    version_ofrecida: str | None = None
    definicion_version_id: UUID | None = None
    oferta_disponible: bool = False
    id: int
    activo: bool
    # Solo se completa en la respuesta de una corrección; en los listados va en
    # None para no pagar el conteo en cada elemento.
    alcance_del_cambio: AlcanceDelCambio | None = None

    model_config = {"from_attributes": True}
