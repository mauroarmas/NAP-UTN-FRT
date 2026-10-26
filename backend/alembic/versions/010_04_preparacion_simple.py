"""Preparaciones sin vencimiento automático; conserva historia y plazos anteriores."""
from alembic import op
import sqlalchemy as sa

revision = '010_04_preparacion_simple'
down_revision = '010_03_seleccion_oferta'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('ensayos_preparacion', 'expires_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column('ensayos_preparacion', 'aviso_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute("UPDATE ensayos_preparacion SET expires_at=NULL,aviso_at=NULL WHERE publicacion_id IS NULL AND cancelada_at IS NULL AND estado NOT IN ('descartada','vencida')")
    op.execute("UPDATE operaciones_ensayo SET deadline_at=NULL WHERE ensayo_id IN (SELECT id FROM ensayos_preparacion WHERE expires_at IS NULL)")
    op.execute("UPDATE compromisos_capacidad SET expira_at=NULL WHERE recurso_ensayo_id IN (SELECT r.id FROM recursos_ensayo r JOIN ensayos_preparacion e ON e.id=r.ensayo_id WHERE e.expires_at IS NULL)")


def downgrade():
    raise RuntimeError('No inventar vencimientos para preparaciones permanentes')
