"""Helpers de baja lógica.

El filtrado es explícito en cada consulta (no hay un filtro global implícito):
la baja lógica nunca debe sorprender a quien lee el código, y las consultas de
auditoría histórica necesitan poder ver los registros dados de baja.
"""

from fastapi import HTTPException


def excluir_dados_de_baja(query, modelo):
    """Agrega el filtro de vigencia a un `select()`."""
    return query.where(modelo.deleted_at.is_(None))


def esta_vigente(obj) -> bool:
    """True si el objeto existe y no está dado de baja."""
    return obj is not None and obj.deleted_at is None


def vigente_o_404(obj, mensaje: str):
    """
    Devuelve el objeto si está vigente; si no, levanta 404.

    Un registro dado de baja es indistinguible de uno inexistente desde los
    endpoints operativos (FR-009).
    """
    if not esta_vigente(obj):
        raise HTTPException(status_code=404, detail=mensaje)
    return obj
