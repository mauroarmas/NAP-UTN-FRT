"""eliminar usuarios.catedra_id

Cuarta y última revisión de la feature 004. Se separa de la primera a propósito:
entre ambas conviven los dos esquemas, de modo que la titularidad puede
verificarse (y revertirse) antes de perder el dato original.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("usuarios_catedra_id_fkey", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "catedra_id")


def downgrade() -> None:
    op.add_column("usuarios", sa.Column("catedra_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "usuarios_catedra_id_fkey", "usuarios", "catedras", ["catedra_id"], ["id"]
    )
    # Se reconstruye desde la titularidad: cada titular recupera una de sus
    # cátedras. Si tenía varias, el esquema viejo solo admite una, así que se
    # toma la de menor id — la reversión es lossy y no puede no serlo.
    op.execute(
        """
        UPDATE usuarios
        SET catedra_id = (
            SELECT MIN(c.id) FROM catedras c WHERE c.titular_id = usuarios.id
        )
        """
    )
