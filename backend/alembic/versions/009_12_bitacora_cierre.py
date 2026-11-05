"""Bitácora aditiva para regularización explícita, sin modificar legado."""
from alembic import op
import sqlalchemy as sa

revision='009_12_bitacora_cierre'
down_revision='009_11_observacion'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('bitacora_cierre',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('entidad_tipo',sa.String(20),nullable=False),
        sa.Column('entidad_id',sa.String(80),nullable=False),
        sa.Column('fuente_sha256',sa.String(64),nullable=False),
        sa.Column('resultado_sha256',sa.String(64),nullable=False),
        sa.Column('accion',sa.String(40),nullable=False),
        sa.Column('antes_seguro',sa.JSON(),nullable=False),
        sa.Column('despues_seguro',sa.JSON(),nullable=False),
        sa.Column('pendientes',sa.JSON(),nullable=False),
        sa.Column('legado_cifrado',sa.Text()),
        sa.Column('actor_institucional',sa.String(200)),
        sa.Column('actor_usuario_id',sa.Integer(),sa.ForeignKey('usuarios.id')),
        sa.Column('referencia',sa.String(200),nullable=False),
        sa.Column('creado_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("entidad_tipo IN ('usuario','pedido','servicio')",name='ck_cierre_entidad'),
        sa.UniqueConstraint('entidad_tipo','entidad_id','accion','fuente_sha256',name='uq_cierre_entidad_fuente'))


def downgrade():
    raise RuntimeError('Restaurar copia verificada; no eliminar bitácora ni cuarentena de legado')
