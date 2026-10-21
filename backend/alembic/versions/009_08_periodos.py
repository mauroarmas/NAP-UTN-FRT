"""Una sustitución vigente por período; preservar filas históricas."""
from alembic import op
import sqlalchemy as sa

revision = '009_08_periodos'
down_revision = '009_07_calendario'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pedidos', sa.Column('vigencia_solicitada', sa.JSON(), nullable=True))
    op.create_index('uq_vigencia_sustituye_activa', 'vigencias_autorizadas', ['sustituye_id'], unique=True,
        postgresql_where=sa.text('sustituye_id IS NOT NULL AND revocada_at IS NULL'))


def downgrade():
    raise RuntimeError('Conservar restricciones e historia; restaurar copia verificada')
