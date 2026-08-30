"""reserva de capacidad, vencimiento de servicios e historial de servicios

Segunda de las cuatro revisiones de la feature 004.

Agrega lo que hace falta para que la aprobación **comprometa** capacidad en vez
de solo informarla, para que los servicios tengan fecha de fin, y para que el
sistema pueda dejar rastro de las acciones que ejecuta sin persona detrás
(``pedidos_historial.usuario_id`` pasa a admitir NULL).

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Pedidos: tipo y reserva de capacidad ---
    # Las etiquetas van en MAYÚSCULA porque SQLAlchemy persiste el *nombre* del
    # miembro del enum de Python, no su valor: la columna se declara como
    # SAEnum(TipoPedido) y al consultar emite "ALTA", no "alta". Crear el tipo
    # con las etiquetas en minúscula rompe toda consulta que filtre por `tipo`
    # contra PostgreSQL (SQLite no lo detecta: allí el enum es un VARCHAR).
    # Es además la convención de los otros cuatro enums del esquema.
    tipo_pedido = sa.Enum("ALTA", "RENOVACION", name="tipopedido")
    tipo_pedido.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "pedidos",
        sa.Column("tipo", tipo_pedido, nullable=False, server_default="ALTA"),
    )
    op.add_column("pedidos", sa.Column("servicio_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pedidos_servicio_renovado", "pedidos", "servicios", ["servicio_id"], ["id"]
    )
    for col in ("reserva_vcpus", "reserva_ram_mb", "reserva_disk_gb"):
        op.add_column(
            "pedidos",
            sa.Column(col, sa.Integer(), nullable=False, server_default="0"),
        )
    op.add_column("pedidos", sa.Column("reserva_expira_at", sa.DateTime(), nullable=True))
    op.add_column(
        "pedidos", sa.Column("justificacion_capacidad", sa.Text(), nullable=True)
    )

    # --- El sistema como autor de una transición ---
    op.alter_column(
        "pedidos_historial", "usuario_id", existing_type=sa.Integer(), nullable=True
    )

    # --- Templates: justificación para superar el tope de disco ---
    op.add_column(
        "recurso_templates", sa.Column("justificacion_disco", sa.Text(), nullable=True)
    )

    # --- Servicios: vencimiento y pausado ---
    op.add_column("servicios", sa.Column("vence_at", sa.DateTime(), nullable=True))
    op.add_column(
        "servicios", sa.Column("aviso_vencimiento_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "servicios",
        sa.Column(
            "exento_pausado", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "servicios", sa.Column("pausa_programada_at", sa.DateTime(), nullable=True)
    )
    op.add_column("servicios", sa.Column("aviso_pausa_at", sa.DateTime(), nullable=True))
    op.add_column("servicios", sa.Column("pausado_auto_at", sa.DateTime(), nullable=True))

    # --- Historial de servicios ---
    op.create_table(
        "servicios_historial",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("estado_anterior", sa.String(length=20), nullable=False),
        sa.Column("estado_nuevo", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicios.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Exclusión mutua de los trabajos periódicos ---
    op.create_table(
        "job_locks",
        sa.Column("nombre", sa.String(length=50), nullable=False),
        sa.Column(
            "tomado_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tomado_por", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("nombre"),
    )


def downgrade() -> None:
    op.drop_table("job_locks")
    op.drop_table("servicios_historial")

    for col in (
        "pausado_auto_at",
        "aviso_pausa_at",
        "pausa_programada_at",
        "exento_pausado",
        "aviso_vencimiento_at",
        "vence_at",
    ):
        op.drop_column("servicios", col)

    op.drop_column("recurso_templates", "justificacion_disco")

    # Volver a NOT NULL exige que no queden transiciones ejecutadas por el
    # sistema; se descartan porque en el esquema viejo no tienen representación.
    op.execute("DELETE FROM pedidos_historial WHERE usuario_id IS NULL")
    op.alter_column(
        "pedidos_historial", "usuario_id", existing_type=sa.Integer(), nullable=False
    )

    op.drop_column("pedidos", "justificacion_capacidad")
    op.drop_column("pedidos", "reserva_expira_at")
    for col in ("reserva_disk_gb", "reserva_ram_mb", "reserva_vcpus"):
        op.drop_column("pedidos", col)
    op.drop_constraint("fk_pedidos_servicio_renovado", "pedidos", type_="foreignkey")
    op.drop_column("pedidos", "servicio_id")
    op.drop_column("pedidos", "tipo")
    sa.Enum(name="tipopedido").drop(op.get_bind(), checkfirst=True)
