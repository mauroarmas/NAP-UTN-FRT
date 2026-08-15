"""soft delete en pedidos/servicios + vmid reservado en pedidos

Revision ID: b1a2c3d4e5f6
Revises: ce2e9b4b4077
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'ce2e9b4b4077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Baja lógica: NULL = registro vigente. No requiere backfill, las filas
    # existentes quedan vigentes por defecto.
    op.add_column('pedidos', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('pedidos', sa.Column('vmid_reservado', sa.String(length=10), nullable=True))
    op.add_column('servicios', sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Índices parciales: los listados solo consultan filas vigentes, así que el
    # índice cubre únicamente esas y se mantiene chico.
    op.create_index(
        'ix_pedidos_vigentes',
        'pedidos',
        ['deleted_at'],
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
    op.create_index(
        'ix_servicios_vigentes',
        'servicios',
        ['deleted_at'],
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_servicios_vigentes', table_name='servicios')
    op.drop_index('ix_pedidos_vigentes', table_name='pedidos')
    op.drop_column('servicios', 'deleted_at')
    op.drop_column('pedidos', 'vmid_reservado')
    op.drop_column('pedidos', 'deleted_at')
