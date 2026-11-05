from sqlalchemy import text


async def test_uses_independent_connections_and_private_schema(pg_sessions):
    async with pg_sessions() as first, pg_sessions() as second:
        first_pid = await first.scalar(text('SELECT pg_backend_pid()'))
        second_pid = await second.scalar(text('SELECT pg_backend_pid()'))
        assert first_pid != second_pid
        schema = await first.scalar(text('SELECT current_schema()'))
        assert schema.startswith('nap_test_') and len(schema) == 41
        assert await second.scalar(text('SELECT current_schema()')) == schema
