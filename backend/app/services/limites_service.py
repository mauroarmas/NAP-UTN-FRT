"""Límites por recurso individual.

Distinto de la capacidad del clúster: esto no mira cuánto hay libre, mira que un
recurso suelto no sea desproporcionado.

El tope de disco por contenedor es una regla de la constitución. Hasta ahora se
cumplía por accidente: la cuota de almacenamiento por cátedra valía 8 GB por
defecto, así que nadie podía pedir más aunque nada lo prohibiera explícitamente.
Al eliminarse las cuotas esa protección lateral desaparece, y el tope necesita
existir por sí mismo.
"""

from fastapi import HTTPException, status

DISCO_MAX_GB = 8


def validar_disco(disk_gb: int, justificacion: str | None) -> None:
    """Rechaza un disco por encima del tope si no hay justificación registrada.

    No es un tope duro: superarlo es legítimo cuando alguien se hace cargo por
    escrito. Lo que no es legítimo es que ocurra sin que quede constancia.
    """
    if disk_gb <= DISCO_MAX_GB:
        return
    if justificacion and justificacion.strip():
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"El disco de un contenedor no puede superar los {DISCO_MAX_GB} GB "
            f"sin una justificación registrada (se pidieron {disk_gb} GB)"
        ),
    )


def validar_disco_template(template) -> None:
    """Aplica el tope a un template, usando su propia justificación."""
    validar_disco(template.default_disk_gb, template.justificacion_disco)
