"""Conservar digests de la preparación sin inferirlos para recursos históricos."""
from alembic import op
import sqlalchemy as sa

revision = '009_10_identidad_preparacion'
down_revision = '009_09_perfiles_definicion'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('identidades_infraestructura', sa.Column('definition_sha256', sa.String(64), nullable=True))
    op.add_column('identidades_infraestructura', sa.Column('bundle_sha256', sa.String(64), nullable=True))


def downgrade():
    raise RuntimeError('La identidad histórica se conserva; restaurar una copia verificada')
