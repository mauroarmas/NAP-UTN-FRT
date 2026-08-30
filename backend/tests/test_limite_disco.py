"""Tope de 8 GB de disco por contenedor (Principio IV de la constitución).

Hasta esta feature el tope se cumplía de casualidad: la cuota de almacenamiento
por cátedra valía 8 GB por defecto, así que nadie podía pedir más. Al eliminarse
las cuotas esa protección lateral desaparece; estas pruebas verifican que el
tope ahora existe por sí mismo.
"""

import pytest

from app.services.limites_service import DISCO_MAX_GB, validar_disco
from fastapi import HTTPException


def test_disco_dentro_del_tope_pasa():
    validar_disco(DISCO_MAX_GB, None)


def test_disco_por_encima_del_tope_sin_justificacion_falla():
    with pytest.raises(HTTPException) as exc:
        validar_disco(16, None)
    assert exc.value.status_code == 400
    assert "8 GB" in exc.value.detail


def test_justificacion_en_blanco_no_alcanza():
    """Una justificación vacía es lo mismo que no tenerla."""
    with pytest.raises(HTTPException):
        validar_disco(16, "   ")


def test_disco_por_encima_del_tope_con_justificacion_pasa():
    validar_disco(16, "Base de datos de la cátedra, aprobado por dirección")


async def test_alta_de_template_rechaza_disco_excesivo(client, auth_admin):
    respuesta = await client.post(
        "/templates/",
        json={"nombre": "LXC Grande", "tipo": "lxc", "default_disk_gb": 16},
        headers=auth_admin,
    )
    assert respuesta.status_code == 400


async def test_alta_de_template_acepta_disco_excesivo_justificado(client, auth_admin):
    respuesta = await client.post(
        "/templates/",
        json={
            "nombre": "LXC Grande",
            "tipo": "lxc",
            "default_disk_gb": 16,
            "justificacion_disco": "Dataset de la materia, no entra en 8 GB",
        },
        headers=auth_admin,
    )
    assert respuesta.status_code == 201
    # La justificación queda consultable: sin eso el registro no sirve de nada.
    assert respuesta.json()["justificacion_disco"].startswith("Dataset")
