"""Selección original de biblioteca, sin reconstruir datos históricos."""
from alembic import op
import sqlalchemy as sa
revision='010_03_seleccion_oferta'
down_revision='010_02_ensayos_artefactos'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('pedidos',sa.Column('seleccion_oferta_snapshot',sa.JSON(),nullable=True))


def downgrade():
    raise RuntimeError('No borrar selecciones históricas; recuperar copia comprobada')
