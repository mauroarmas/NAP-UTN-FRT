"""Reparar instalaciones migradas antes de corregir el vínculo alta-servicio.

El alta comienza sin servicio y adquiere servicio_id al materializar el LXC.
La condición anterior sobrevivió en instalaciones que ya tenían 009_14 aplicada.
"""
from alembic import op

revision = '010_05_alta_materializada'
down_revision = '010_04_preparacion_simple'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_pedido_tipo_servicio', 'pedidos', type_='check')
    op.create_check_constraint('ck_pedido_tipo_servicio', 'pedidos',
        "tipo = 'ALTA' OR (tipo = 'RENOVACION' AND servicio_id IS NOT NULL)")


def downgrade():
    # Reparación de datos/esquema: la revisión anterior corregida usa la misma condición.
    # No restablecer la condición defectuosa que impediría materializar altas existentes.
    pass
