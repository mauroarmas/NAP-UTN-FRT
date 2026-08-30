from pydantic import BaseModel


class TemplateBase(BaseModel):
    nombre: str
    descripcion: str | None = None
    tipo: str = "lxc"
    default_vcpus: int = 1
    default_ram_mb: int = 256
    default_disk_gb: int = 2
    # Obligatoria para superar el tope de 8 GB por contenedor.
    justificacion_disco: str | None = None
    os_template: str | None = None
    config_extra: dict | None = None


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    """Corrección de una plantilla ya creada. Todos los campos son opcionales.

    `tipo` **no es editable** (regla T4): cambiar un contenedor por una máquina
    virtual altera la naturaleza de lo que se entrega y de lo que ya se aprobó
    sobre esa plantilla. Para eso corresponde una plantilla nueva. Figura abajo
    de todas formas para que el endpoint pueda rechazarlo diciendo por qué.
    """

    nombre: str | None = None
    descripcion: str | None = None
    # `tipo` figura acá **solo para poder rechazarlo con un mensaje que explique
    # por qué**. Dejarlo fuera del schema haría que Pydantic lo descartara en
    # silencio y el administrador creería haberlo cambiado.
    tipo: str | None = None
    default_vcpus: int | None = None
    default_ram_mb: int | None = None
    default_disk_gb: int | None = None
    justificacion_disco: str | None = None
    os_template: str | None = None
    config_extra: dict | None = None
    activo: bool | None = None


class AlcanceDelCambio(BaseModel):
    """Qué queda fuera del alcance de una corrección de plantilla (FR-003).

    Es informativo, nunca bloqueante: editar una plantilla no toca lo ya
    entregado ni lo ya aprobado, y el administrador merece saberlo en el momento
    en que edita, no descubrirlo después.
    """

    servicios_desplegados: int
    pedidos_aprobados_pendientes: int


class TemplateResponse(TemplateBase):
    id: int
    activo: bool
    # Solo se completa en la respuesta de una corrección; en los listados va en
    # None para no pagar el conteo en cada elemento.
    alcance_del_cambio: AlcanceDelCambio | None = None

    model_config = {"from_attributes": True}
