"""Dos tamaños compartidos; no representan reservas ni cupos por cátedra."""
from typing import Literal

Tamano = Literal['small', 'medium']
TAMANOS = {
    'small': {'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4},
    'medium': {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8},
}


def tamanos_compatibles(minimum):
    if not minimum or any(type(minimum.get(k)) is not int or minimum[k] < 1 for k in TAMANOS['small']):
        return []
    return [name for name, resources in TAMANOS.items()
            if all(resources[key] >= minimum[key] for key in resources)]


def identificar_tamano(resources):
    return next((name for name, values in TAMANOS.items()
                 if all(resources.get(key) == value for key, value in values.items())), None)


def validar_tamano(name, resources):
    if name and any(resources[key] != value for key, value in TAMANOS[name].items()):
        raise ValueError('Los recursos deben coincidir con el tamaño Small o Medium seleccionado')
