"""Destino de la consola nativa: nodo del contenedor, failover y cierre en falla (spec 020)."""
import pytest
from fastapi import HTTPException

from app.services.consola_destino_service import resolver_destino, validar_nodos

PERFIL = {'nodos': {'frt': {'host': 'frt.test', 'port': 8006}, 'pve91': {'host': 'pve91.test', 'port': 8443}}}


def sondeo(vivos):
    llamados = []

    async def _sondeo(host, port):
        llamados.append(host)
        return host in vivos
    _sondeo.llamados = llamados
    return _sondeo


async def test_usa_el_nodo_que_aloja_el_contenedor():
    probe = sondeo({'frt.test', 'pve91.test'})
    assert await resolver_destino(PERFIL, 'pve91', sondeo=probe) == ('pve91.test', 8443)
    assert probe.llamados == ['pve91.test']


@pytest.mark.parametrize('contenedor, vivo, esperado', [
    ('pve91', 'frt.test', ('frt.test', 8006)),
    ('frt', 'pve91.test', ('pve91.test', 8443)),
])
async def test_failover_al_otro_nodo_si_el_propio_no_responde(contenedor, vivo, esperado):
    assert await resolver_destino(PERFIL, contenedor, sondeo=sondeo({vivo})) == esperado


async def test_sin_nodos_vivos_responde_503_sin_destino():
    with pytest.raises(HTTPException) as exc:
        await resolver_destino(PERFIL, 'frt', sondeo=sondeo(set()))
    assert exc.value.status_code == 503
    assert exc.value.detail['codigo'] == 'consola_nodo_no_disponible'
    assert 'frt.test' not in str(exc.value.detail) and 'pve91.test' not in str(exc.value.detail)


@pytest.mark.parametrize('perfil', [{}, {'nodos': {}}, {'nodos': {'frt': {'host': 'frt.test'}}}])
async def test_nodo_del_contenedor_fuera_del_perfil_cierra_la_consola(perfil):
    with pytest.raises(HTTPException) as exc:
        await resolver_destino(perfil, 'pve91', sondeo=sondeo({'frt.test'}))
    assert exc.value.status_code == 409
    assert exc.value.detail['codigo'] == 'consola_no_habilitada'


async def test_el_puerto_por_omision_es_8006():
    perfil = {'nodos': {'frt': {'host': 'frt.test'}}}
    assert await resolver_destino(perfil, 'frt', sondeo=sondeo({'frt.test'})) == ('frt.test', 8006)


@pytest.mark.parametrize('nodos', [
    None, [], {'frt': 'frt.test'}, {'frt': {'port': 8006}}, {'frt': {'host': 'a b'}},
    {'frt': {'host': 'https://frt.test'}}, {'frt': {'host': 'frt.test/x'}}, {'frt': {'host': 'u@frt.test'}},
    {'frt': {'host': '999.1.1.1'}}, {'frt': {'host': 'frt.test', 'port': 0}},
    {'frt': {'host': 'frt.test', 'port': '8006'}}, {'frt': {'host': 'frt.test', 'extra': 1}},
    {'fr t': {'host': 'frt.test'}},
])
def test_validar_nodos_rechaza_perfiles_mal_formados(nodos):
    with pytest.raises(ValueError):
        validar_nodos(nodos)


def test_validar_nodos_acepta_nombres_y_direcciones():
    assert validar_nodos({'frt': {'host': 'frt.example.edu', 'port': 8006}, 'n2': {'host': '10.0.0.5'}})
    assert validar_nodos({'frt': {'host': '10.0.0.5', 'portal_host': 'frt.interno.example.edu'}})


@pytest.mark.parametrize('portal', ['a b', 'https://x', '999.1.1.1', '', 7])
def test_validar_nodos_rechaza_portal_host_mal_formado(portal):
    with pytest.raises(ValueError):
        validar_nodos({'frt': {'host': '10.0.0.5', 'portal_host': portal}})
