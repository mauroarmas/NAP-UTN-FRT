"""SQL de la migración a titular único.

La migración corre contra el esquema **anterior** (con `usuarios.catedra_id`),
que ya no existe en los modelos, así que no se puede ejercitar con las factories
normales. Estas pruebas montan las tablas viejas a mano y ejecutan las mismas
sentencias que la revisión de Alembic.

Lo que se protege es el SQL, que es la parte más fácil de equivocar y la única
que no cubre ninguna otra prueba: se aplica una vez, sobre datos reales, y si
está mal alguien pierde acceso sin que quede registro.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Mismas sentencias que `d1e2f3a4b5c6_titular_catedra.py`. Se copian en lugar de
# importarse porque el módulo de migración depende del contexto de Alembic.
SQL_ELEGIR_TITULAR = """
    UPDATE catedras
    SET titular_id = (
        SELECT MIN(u.id) FROM usuarios u WHERE u.catedra_id = catedras.id
    )
"""

SQL_REGISTRAR_DESPLAZADOS = """
    INSERT INTO migracion_004_accesos_perdidos
        (usuario_id, username, catedra_id, catedra_nombre, migrado_at)
    SELECT u.id, u.username, c.id, c.nombre, CURRENT_TIMESTAMP
    FROM usuarios u
    JOIN catedras c ON c.id = u.catedra_id
    WHERE c.titular_id IS NOT NULL AND c.titular_id <> u.id
"""

ESQUEMA_VIEJO = [
    """CREATE TABLE catedras (
        id INTEGER PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        titular_id INTEGER
    )""",
    """CREATE TABLE usuarios (
        id INTEGER PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        catedra_id INTEGER
    )""",
    """CREATE TABLE migracion_004_accesos_perdidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        username VARCHAR(50) NOT NULL,
        catedra_id INTEGER NOT NULL,
        catedra_nombre VARCHAR(100) NOT NULL,
        migrado_at TIMESTAMP
    )""",
]


@pytest_asyncio.fixture
async def base_vieja():
    """Base con el esquema previo a la feature 004."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for ddl in ESQUEMA_VIEJO:
            await conn.execute(text(ddl))
    yield engine
    await engine.dispose()


async def _poblar(conn, catedras, usuarios):
    for cid, nombre in catedras:
        await conn.execute(
            text("INSERT INTO catedras (id, nombre) VALUES (:i, :n)"),
            {"i": cid, "n": nombre},
        )
    for uid, username, catedra_id in usuarios:
        await conn.execute(
            text(
                "INSERT INTO usuarios (id, username, catedra_id) "
                "VALUES (:i, :u, :c)"
            ),
            {"i": uid, "u": username, "c": catedra_id},
        )


async def _migrar(conn):
    await conn.execute(text(SQL_ELEGIR_TITULAR))
    await conn.execute(text(SQL_REGISTRAR_DESPLAZADOS))


async def test_elige_el_usuario_de_menor_id_como_titular(base_vieja):
    """Criterio determinista: reproducible y auditable.

    Cualquier regla "inteligente" (quien creó más pedidos, quien entró último)
    daría resultados que nadie puede verificar y que cambian según cuándo se
    corra la migración.
    """
    async with base_vieja.begin() as conn:
        await _poblar(
            conn,
            catedras=[(1, "Álgebra")],
            usuarios=[(7, "tardio", 1), (3, "temprano", 1), (9, "otro", 1)],
        )
        await _migrar(conn)

        titular = (
            await conn.execute(text("SELECT titular_id FROM catedras WHERE id = 1"))
        ).scalar_one()

    assert titular == 3


async def test_registra_a_quienes_pierden_el_acceso(base_vieja):
    async with base_vieja.begin() as conn:
        await _poblar(
            conn,
            catedras=[(1, "Álgebra")],
            usuarios=[(3, "temprano", 1), (7, "tardio", 1), (9, "otro", 1)],
        )
        await _migrar(conn)

        filas = (
            await conn.execute(
                text(
                    "SELECT username, catedra_nombre FROM "
                    "migracion_004_accesos_perdidos ORDER BY username"
                )
            )
        ).all()

    assert [f[0] for f in filas] == ["otro", "tardio"]
    assert filas[0][1] == "Álgebra", "se copia el nombre, no solo el id"
    # El titular elegido no figura como desplazado.
    assert "temprano" not in [f[0] for f in filas]


async def test_una_catedra_con_un_solo_usuario_no_genera_registros(base_vieja):
    """El caso normal no debe ensuciar la bitácora."""
    async with base_vieja.begin() as conn:
        await _poblar(
            conn,
            catedras=[(1, "Física")],
            usuarios=[(5, "unico", 1)],
        )
        await _migrar(conn)

        titular = (
            await conn.execute(text("SELECT titular_id FROM catedras WHERE id = 1"))
        ).scalar_one()
        perdidos = (
            await conn.execute(
                text("SELECT COUNT(*) FROM migracion_004_accesos_perdidos")
            )
        ).scalar_one()

    assert titular == 5
    assert perdidos == 0


async def test_una_catedra_sin_usuarios_queda_sin_titular(base_vieja):
    """Nullable existe justamente para esto; el administrador lo resuelve después."""
    async with base_vieja.begin() as conn:
        await _poblar(conn, catedras=[(1, "Huérfana")], usuarios=[])
        await _migrar(conn)

        titular = (
            await conn.execute(text("SELECT titular_id FROM catedras WHERE id = 1"))
        ).scalar_one()

    assert titular is None


async def test_un_usuario_sin_catedra_no_afecta_a_nadie(base_vieja):
    async with base_vieja.begin() as conn:
        await _poblar(
            conn,
            catedras=[(1, "Química")],
            usuarios=[(2, "con_catedra", 1), (4, "admin_suelto", None)],
        )
        await _migrar(conn)

        titular = (
            await conn.execute(text("SELECT titular_id FROM catedras WHERE id = 1"))
        ).scalar_one()
        perdidos = (
            await conn.execute(
                text("SELECT COUNT(*) FROM migracion_004_accesos_perdidos")
            )
        ).scalar_one()

    assert titular == 2
    assert perdidos == 0


async def test_varias_catedras_se_migran_independientemente(base_vieja):
    async with base_vieja.begin() as conn:
        await _poblar(
            conn,
            catedras=[(1, "Uno"), (2, "Dos")],
            usuarios=[
                (10, "a", 1),
                (11, "b", 1),
                (5, "c", 2),
            ],
        )
        await _migrar(conn)

        titulares = dict(
            (
                await conn.execute(text("SELECT id, titular_id FROM catedras"))
            ).all()
        )
        perdidos = (
            await conn.execute(
                text("SELECT username FROM migracion_004_accesos_perdidos")
            )
        ).scalars().all()

    assert titulares == {1: 10, 2: 5}
    assert perdidos == ["b"]
