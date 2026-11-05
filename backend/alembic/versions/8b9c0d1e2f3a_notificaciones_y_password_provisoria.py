"""notificaciones y password provisoria

Feature 008: Notificaciones por Email y Gestión de Contraseñas Provisorias
- Agrega campo debe_cambiar_password a usuarios.
- Agrega campo recibir_notificaciones_email a usuarios.

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "8b9c0d1e2f3a"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "debe_cambiar_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "recibir_notificaciones_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "recibir_notificaciones_email")
    op.drop_column("usuarios", "debe_cambiar_password")

