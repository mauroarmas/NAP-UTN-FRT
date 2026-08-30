"""titular único por cátedra y bitácora de accesos perdidos

Primera de las cuatro revisiones de la feature 004. Invierte la relación entre
persona y cátedra: antes el usuario apuntaba a su (única) cátedra, ahora la
cátedra apunta a su titular, lo que permite que una persona tenga varias.

El titular se elige de forma determinista —el ``id`` más bajo entre quienes hoy
tienen esa cátedra asignada— porque cualquier regla "inteligente" (quien creó
más pedidos, quien entró último) da resultados que nadie puede auditar y que
cambian según cuándo se corra la migración.

``usuarios.catedra_id`` **no** se elimina acá: se hace en la revisión 4, para
que ambos esquemas convivan un momento y esta revisión sea reversible.

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("catedras", sa.Column("titular_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_catedras_titular", "catedras", "usuarios", ["titular_id"], ["id"]
    )

    op.create_table(
        "migracion_004_accesos_perdidos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("catedra_id", sa.Integer(), nullable=False),
        sa.Column("catedra_nombre", sa.String(length=100), nullable=False),
        sa.Column(
            "migrado_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["catedra_id"], ["catedras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Titular = el usuario de menor id entre los asignados a cada cátedra.
    op.execute(
        """
        UPDATE catedras
        SET titular_id = (
            SELECT MIN(u.id) FROM usuarios u WHERE u.catedra_id = catedras.id
        )
        """
    )

    # Todos los demás pierden el acceso: queda constancia para que el
    # administrador lo resuelva, en vez de que la persona se entere al no poder
    # entrar.
    op.execute(
        """
        INSERT INTO migracion_004_accesos_perdidos
            (usuario_id, username, catedra_id, catedra_nombre, migrado_at)
        SELECT u.id, u.username, c.id, c.nombre, CURRENT_TIMESTAMP
        FROM usuarios u
        JOIN catedras c ON c.id = u.catedra_id
        WHERE c.titular_id IS NOT NULL AND c.titular_id <> u.id
        """
    )


def downgrade() -> None:
    op.drop_table("migracion_004_accesos_perdidos")
    op.drop_constraint("fk_catedras_titular", "catedras", type_="foreignkey")
    op.drop_column("catedras", "titular_id")
