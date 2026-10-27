"""Borradores de fuente externa; no crea ofertas ni instalaciones."""
from alembic import op
import sqlalchemy as sa
revision = '010_01_biblioteca'
down_revision = '009_14_restauracion'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('incorporaciones_aplicacion',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('proveedor',sa.String(40),nullable=False),
        sa.Column('identidad_externa',sa.String(180),nullable=False),
        sa.Column('origen_clave',sa.String(180),nullable=False),
        sa.Column('revision_fuente',sa.String(40),nullable=False),
        sa.Column('comando_sha256',sa.String(64),nullable=False),
        sa.Column('comando_origen',sa.Text(),nullable=False),
        sa.Column('url_origen',sa.Text(),nullable=False),
        sa.Column('version_externa',sa.String(100)),
        sa.Column('nombre',sa.String(150),nullable=False),
        sa.Column('descripcion',sa.Text()),
        sa.Column('categorias',sa.JSON(),nullable=False),
        sa.Column('aliases',sa.JSON(),nullable=False),
        sa.Column('datos_origen',sa.JSON(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False,server_default='1'),
        sa.Column('creado_por',sa.Integer(),sa.ForeignKey('usuarios.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('proveedor','identidad_externa','origen_clave',name='uq_incorporacion_origen'),
        sa.CheckConstraint('revision >= 1',name='ck_incorporacion_revision'))


def downgrade():
    raise RuntimeError('No borrar borradores/historia; deshabilitar biblioteca o restaurar copia comprobada')
