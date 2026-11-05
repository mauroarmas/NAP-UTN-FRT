"""Leases de trabajos con dueño/generación y vencimiento explícitos."""
from alembic import op
import sqlalchemy as sa

revision = '009_06_worker_jobs'
down_revision = '009_05_operaciones'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('job_locks', sa.Column('owner_token', sa.Uuid(), nullable=True))
    op.add_column('job_locks', sa.Column('generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('job_locks', sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True))
    # Los locks legados se respetan durante su TTL anterior, sin asumir abandono.
    op.execute("UPDATE job_locks SET lease_until = (tomado_at AT TIME ZONE 'UTC') + INTERVAL '30 minutes'")


def downgrade():
    raise RuntimeError('Restaurar copia verificada; no eliminar ownership de trabajos en curso')
