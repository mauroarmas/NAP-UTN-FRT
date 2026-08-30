"""eliminar la cuota por cátedra y relajar la unicidad del nombre

Tercera de las cuatro revisiones de la feature 004.

Lo que desaparece es el **techo declarado por adelantado**, no la contabilidad
de capacidad: esa se conserva y pasa a ejercerse contra la capacidad real del
clúster en el momento de la aprobación.

El nombre de cátedra deja de ser único a nivel global —dos personas pueden
dictar materias homónimas— y pasa a serlo por titular.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La unicidad global del nombre se reemplaza por unicidad (titular, nombre).
    op.drop_constraint("catedras_nombre_key", "catedras", type_="unique")
    op.create_unique_constraint(
        "uq_catedras_titular_nombre", "catedras", ["titular_id", "nombre"]
    )

    op.drop_column("catedras", "cuota_vcpus")
    op.drop_column("catedras", "cuota_ram_mb")
    op.drop_column("catedras", "cuota_storage_gb")


def downgrade() -> None:
    # Los valores por defecto son los que traía el modelo anterior; el dato
    # original de cada cátedra no es recuperable y no debe fingirse que sí.
    op.add_column(
        "catedras",
        sa.Column("cuota_vcpus", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "catedras",
        sa.Column("cuota_ram_mb", sa.Integer(), nullable=False, server_default="1024"),
    )
    op.add_column(
        "catedras",
        sa.Column("cuota_storage_gb", sa.Integer(), nullable=False, server_default="8"),
    )

    op.drop_constraint("uq_catedras_titular_nombre", "catedras", type_="unique")
    op.create_unique_constraint("catedras_nombre_key", "catedras", ["nombre"])
