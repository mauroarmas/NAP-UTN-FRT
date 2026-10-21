"""Vincular perfiles a definiciones sin inventar producto en filas históricas."""
from alembic import op
import sqlalchemy as sa

revision = '009_09_perfiles_definicion'
down_revision = '009_08_periodos'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recurso_templates', sa.Column('definicion_version_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_template_definicion', 'recurso_templates', 'definiciones_servicio', ['definicion_version_id'], ['id'])
    op.create_index('ix_recurso_templates_definicion_version_id', 'recurso_templates', ['definicion_version_id'])


def downgrade():
    raise RuntimeError('Las referencias históricas se conservan; restaurar una copia verificada')
