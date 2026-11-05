from uuid import UUID
from sqlalchemy import Uuid, UniqueConstraint
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    Text,
    JSON,
    Enum as SAEnum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text
import enum

from app.database import Base


class EstadoPedido(str, enum.Enum):
    SOLICITADO = "solicitado"
    REQUIERE_AJUSTE = "requiere_ajuste"
    CANCELADO = "cancelado"
    APROBADO = "aprobado"
    # Transitorio: solo lo asigna el orquestador durante el despliegue real
    # contra Proxmox (ver pedido_service.TRANSICIONES_SISTEMA). Nunca se llega
    # a este estado con un cambio de estado manual.
    EN_DESPLIEGUE = "en_despliegue"
    ACTIVO = "activo"
    RECHAZADO = "rechazado"
    ERROR = "error"
    SUSPENDIDO = "suspendido"


class ModeloServicio(str, enum.Enum):
    IAAS = "iaas"
    PAAS = "paas"
    SAAS = "saas"


class VigenciaTipo(str, enum.Enum):
    PRIMER_CUATRIMESTRE = "primer_cuatrimestre"
    SEGUNDO_CUATRIMESTRE = "segundo_cuatrimestre"
    ANUAL = "anual"
    PERSONALIZADO = "personalizado"


class TipoPedido(str, enum.Enum):
    """Un pedido da de alta un servicio nuevo o renueva uno existente.

    Ambos atraviesan la misma máquina de estados; lo que cambia es el ejecutor
    de la transición a ACTIVO (desplegar un contenedor vs. correr la fecha de
    vencimiento del servicio que ya existe).
    """

    ALTA = "alta"
    RENOVACION = "renovacion"


class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint('revision >= 1 AND revision_decision >= 0',name='ck_pedido_revisiones'),
        CheckConstraint('definicion_version_id IS NULL OR configuracion_despliegue_id IS NULL', name='ck_pedidos_origen_exclusivo'),
        CheckConstraint('despliegue_revision_programada IS NULL OR despliegue_revision_programada > 0', name='ck_pedido_agenda_revision'),
        Index('ix_pedido_despliegue_programado', 'despliegue_programado_at', postgresql_where=text('despliegue_programado_at IS NOT NULL')),
        CheckConstraint("tipo = 'ALTA' OR (tipo = 'RENOVACION' AND servicio_id IS NOT NULL)",name='ck_pedido_tipo_servicio'),
        # Índice parcial: los listados solo consultan filas vigentes.
        Index(
            "ix_pedidos_vigentes",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catedra_id: Mapped[int] = mapped_column(ForeignKey("catedras.id"), nullable=False)
    solicitante_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id"), nullable=False
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurso_templates.id"), nullable=True
    )
    modelo_servicio: Mapped[ModeloServicio] = mapped_column(
        SAEnum(
            ModeloServicio,
            name="modeloservicio",
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
        ),
        default=ModeloServicio.IAAS,
        nullable=False,
    )
    descripcion_requerimientos: Mapped[str | None] = mapped_column(Text, nullable=True)
    vigencia_solicitada: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @property
    def vigencia(self):
        return self.vigencia_solicitada
    vigencia_tipo: Mapped[VigenciaTipo] = mapped_column(
        SAEnum(
            VigenciaTipo,
            name="vigenciatipo",
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
        ),
        default=VigenciaTipo.PRIMER_CUATRIMESTRE,
        nullable=False,
    )
    vigencia_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vigencia_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observaciones_ajuste: Mapped[str | None] = mapped_column(Text, nullable=True)
    opciones_avanzadas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estado: Mapped[EstadoPedido] = mapped_column(
        SAEnum(EstadoPedido, name="estadopedido", native_enum=False),
        default=EstadoPedido.SOLICITADO,
    )
    tipo: Mapped[TipoPedido] = mapped_column(
        SAEnum(TipoPedido, name="tipopedido", native_enum=False),
        default=TipoPedido.ALTA,
        nullable=False,
    )
    # Solo en tipo=RENOVACION: el servicio cuya fecha de fin se quiere correr.
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicios.id"), nullable=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    parametros_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # VMID reservado en el clúster antes de intentar crear el contenedor.
    # Se persiste para que un reintento pueda reutilizarlo tras un fallo.
    vmid_reservado: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Cantidades autorizadas: asignacion_snapshot; saldo y caducidad:
    # compromiso_capacidad. No mantener un segundo contador en el pedido.
    # Obligatoria cuando se aprueba por encima de la capacidad libre.
    justificacion_capacidad: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    revision_decision: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    anio_lectivo: Mapped[int | None] = mapped_column(Integer)
    definicion_version_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('definiciones_servicio.id'))
    configuracion_despliegue_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('configuraciones_despliegue.id', name='fk_pedidos_configuracion'), index=True)
    despliegue_solicitado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    despliegue_programado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    despliegue_revision_programada: Mapped[int | None] = mapped_column(Integer)
    despliegue_solicitado_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id', name='fk_pedido_solicitante_despliegue'))
    seleccion_oferta_snapshot: Mapped[dict | None] = mapped_column(JSON)
    asignacion_snapshot: Mapped[dict | None] = mapped_column(JSON)
    destino_snapshot: Mapped[dict | None] = mapped_column(JSON)
    decision_snapshot: Mapped[dict | None] = mapped_column(JSON)
    sustituye_vigencia_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('vigencias_autorizadas.id'))

    # Relaciones
    catedra: Mapped["Catedra"] = relationship(back_populates="pedidos")
    solicitante: Mapped["Usuario"] = relationship(back_populates="pedidos", foreign_keys=[solicitante_id])
    template: Mapped["RecursoTemplate"] = relationship(back_populates="pedidos")
    historial: Mapped[list["PedidoHistorial"]] = relationship(
        back_populates="pedido", order_by="PedidoHistorial.created_at"
    )
    servicio: Mapped["Servicio | None"] = relationship(
        back_populates="pedido", foreign_keys="Servicio.pedido_id"
    )
    # Solo en renovaciones: el servicio destino.
    servicio_renovado: Mapped["Servicio | None"] = relationship(
        foreign_keys=[servicio_id]
    )

    def __repr__(self) -> str:
        return f"<Pedido #{self.id} ({self.estado.value})>"


class PedidoHistorial(Base):
    __tablename__ = "pedidos_historial"
    __table_args__ = (UniqueConstraint('pedido_id', 'evento_clave', name='uq_historial_pedido_evento'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False)
    estado_anterior: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL significa que la transición la ejecutó el propio sistema (expiración
    # de una reserva, vencimiento, pausado automático). No se atribuye a una
    # persona que no la decidió, ni se omite del historial por no tener autor.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    operacion_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('operaciones_infraestructura.id'))
    evento_clave: Mapped[str | None] = mapped_column(String(200))
    actor_tipo: Mapped[str | None] = mapped_column(String(10))
    decision_metadata: Mapped[dict | None] = mapped_column(JSON)

    # Relaciones
    pedido: Mapped["Pedido"] = relationship(back_populates="historial")

    def __repr__(self) -> str:
        return f"<PedidoHistorial {self.estado_anterior} → {self.estado_nuevo}>"
