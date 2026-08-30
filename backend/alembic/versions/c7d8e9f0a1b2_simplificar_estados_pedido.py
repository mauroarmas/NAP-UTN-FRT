"""simplificar estados de pedido: sacar en_revision

Revision ID: c7d8e9f0a1b2
Revises: b1a2c3d4e5f6
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ESTADOS_NUEVOS = (
    "SOLICITADO", "APROBADO", "EN_DESPLIEGUE", "ACTIVO",
    "RECHAZADO", "ERROR", "SUSPENDIDO",
)
_ESTADOS_VIEJOS = ("SOLICITADO", "EN_REVISION") + _ESTADOS_NUEVOS[1:]


def upgrade() -> None:
    """
    Simplifica EstadoPedido sacando EN_REVISION: la revisión y la aprobación
    eran dos clics separados sin ninguna diferencia funcional entre sí, y esa
    parada extra era la que hacía que aprobar un pedido se sintiera como un
    trámite largo. Los pedidos que estuvieran en EN_REVISION vuelven a
    SOLICITADO (todavía no fueron decididos).

    Postgres no soporta DROP VALUE en un enum, así que se recrea el tipo.
    """
    op.execute("ALTER TYPE estadopedido RENAME TO estadopedido_old")
    op.execute(
        "CREATE TYPE estadopedido AS ENUM ("
        + ", ".join(f"'{e}'" for e in _ESTADOS_NUEVOS)
        + ")"
    )
    op.execute(
        """
        ALTER TABLE pedidos ALTER COLUMN estado TYPE estadopedido USING (
            CASE estado::text
                WHEN 'EN_REVISION' THEN 'SOLICITADO'
                ELSE estado::text
            END
        )::estadopedido
        """
    )
    op.execute("DROP TYPE estadopedido_old")


def downgrade() -> None:
    """Restaura EN_REVISION al enum (sin backfill: no hay forma de saber cuáles volver)."""
    op.execute("ALTER TYPE estadopedido RENAME TO estadopedido_new")
    op.execute(
        "CREATE TYPE estadopedido AS ENUM ("
        + ", ".join(f"'{e}'" for e in _ESTADOS_VIEJOS)
        + ")"
    )
    op.execute(
        "ALTER TABLE pedidos ALTER COLUMN estado TYPE estadopedido "
        "USING estado::text::estadopedido"
    )
    op.execute("DROP TYPE estadopedido_new")
