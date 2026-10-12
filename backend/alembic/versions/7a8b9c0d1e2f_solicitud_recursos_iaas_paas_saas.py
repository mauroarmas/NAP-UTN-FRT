"""solicitud y aprovisionamiento iaas paas saas

Feature 007: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS.
- Agrega campos de modelo de servicio, vigencia y opciones avanzadas a pedidos.
- Agrega modelo_servicio a recurso_templates.
- Agrega url_acceso y credenciales_acceso a servicios.
- Permite que template_id sea nullable en pedidos.
- Agrega REQUIERE_AJUSTE y CANCELADO a estadopedido en PostgreSQL.

Revision ID: 7a8b9c0d1e2f
Revises: a4b5c6d7e8f9
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extender Enum estadopedido si la base es PostgreSQL
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TYPE estadopedido ADD VALUE IF NOT EXISTS 'REQUIERE_AJUSTE'")
        op.execute("ALTER TYPE estadopedido ADD VALUE IF NOT EXISTS 'CANCELADO'")

    # 2. Modificaciones en pedidos
    op.add_column(
        "pedidos",
        sa.Column("modelo_servicio", sa.String(length=20), nullable=False, server_default="iaas"),
    )
    op.add_column(
        "pedidos",
        sa.Column("descripcion_requerimientos", sa.Text(), nullable=True),
    )
    op.add_column(
        "pedidos",
        sa.Column("vigencia_tipo", sa.String(length=30), nullable=False, server_default="primer_cuatrimestre"),
    )
    op.add_column(
        "pedidos",
        sa.Column("vigencia_desde", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "pedidos",
        sa.Column("vigencia_hasta", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "pedidos",
        sa.Column("observaciones_ajuste", sa.Text(), nullable=True),
    )
    op.add_column(
        "pedidos",
        sa.Column("opciones_avanzadas", sa.JSON(), nullable=True),
    )
    # template_id pasa a ser nullable (para pedidos SaaS/PaaS antes de asignación administrativa)
    op.alter_column("pedidos", "template_id", existing_type=sa.Integer(), nullable=True)

    # 3. Modificaciones en recurso_templates
    op.add_column(
        "recurso_templates",
        sa.Column("modelo_servicio", sa.String(length=20), nullable=False, server_default="iaas"),
    )

    # 4. Modificaciones en servicios
    op.add_column(
        "servicios",
        sa.Column("url_acceso", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "servicios",
        sa.Column("credenciales_acceso", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("servicios", "credenciales_acceso")
    op.drop_column("servicios", "url_acceso")

    op.drop_column("recurso_templates", "modelo_servicio")

    op.alter_column("pedidos", "template_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("pedidos", "opciones_avanzadas")
    op.drop_column("pedidos", "observaciones_ajuste")
    op.drop_column("pedidos", "vigencia_hasta")
    op.drop_column("pedidos", "vigencia_desde")
    op.drop_column("pedidos", "vigencia_tipo")
    op.drop_column("pedidos", "descripcion_requerimientos")
    op.drop_column("pedidos", "modelo_servicio")

