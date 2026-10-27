"""Reloj inyectable y conversión explícita de tiempos internos UTC."""

from datetime import datetime, timezone


class Clock:
    def now(self):
        return datetime.now(timezone.utc)


clock = Clock()


def db_utc(value):
    """SQLite pierde tzinfo; columnas legacy conocidas fueron escritas en UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
