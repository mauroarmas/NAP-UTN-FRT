"""Clave pública SSH por servicio Linux IaaS (feature 017); aditiva.

DDL congelado: no importa modelos runtime. Downgrade sólo si la tabla está vacía.
"""
from alembic import op
import sqlalchemy as sa

revision = '017_01_clave_acceso_servicio'
down_revision = '011_01_despliegue_aplicaciones'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('claves_acceso_servicio',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id'), nullable=False, unique=True),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('clave_publica', sa.Text(), nullable=False),
        sa.Column('huella_sha256', sa.String(60), nullable=False),
        sa.Column('usuario', sa.String(32), nullable=False, server_default='nap'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('aplicada_revision', sa.Integer()),
        sa.Column('registrada_por_id', sa.Integer(), sa.ForeignKey('usuarios.id')),
        sa.Column('registrada_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('aplicada_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("tipo IN ('ssh-ed25519','ssh-rsa','ecdsa-sha2-nistp256','ecdsa-sha2-nistp384','ecdsa-sha2-nistp521')", name='ck_clave_acceso_tipo'),
        sa.CheckConstraint('revision >= 1 AND (aplicada_revision IS NULL OR aplicada_revision BETWEEN 1 AND revision)', name='ck_clave_acceso_revisiones'))


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT 1 FROM claves_acceso_servicio LIMIT 1')).first():
        raise RuntimeError('Hay claves de acceso registradas; no se puede revertir sin perder datos')
    op.drop_table('claves_acceso_servicio')
