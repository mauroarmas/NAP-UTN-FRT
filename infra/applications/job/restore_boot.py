"""Unidad de arranque del nodo: recrea las reglas nftables de las instancias antes de que arranque ningún invitado.

Las tablas `nap011_*` viven en el kernel y desaparecen al reiniciar. Sin esta unidad, un LXC iniciado después
(por el portal, por `onboot` o a mano) correría sin aislamiento. No inicia, detiene ni modifica invitados; sólo
reinstala tablas de recursos con recibo `applied`, de forma exclusiva, y falla cerrado ante cualquier diferencia.
"""
import json
import os
from pathlib import Path
import stat
import sys
import time


if not __package__:
    # Python -I excluye el directorio del script: se agrega sólo la raíz instalada y verificada.
    try:
        expected = Path('/opt/nap/applications/job/restore_boot.py')
        if os.geteuid() != 0 or len(sys.argv) != 1 or Path(__file__).absolute() != expected: raise ValueError()
        for path in [*reversed(expected.parents), expected]:
            info = path.lstat()
            if (info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                    or not (stat.S_ISDIR(info.st_mode) if path != expected else stat.S_ISREG(info.st_mode))): raise ValueError()
        sys.dont_write_bytecode = True
        sys.path.insert(0, '/opt/nap')
        __package__ = 'applications.job'
    except Exception:
        raise SystemExit(1) from None

from .protocol import JobError

# `pvestatd` publica los invitados poco después de que arranca `pve-cluster`, y en frío los comandos de Proxmox
# pueden tardar más que su plazo: se reintenta en lugar de fallar.
ATTEMPTS, PAUSE = 30, 3


def restore(runtime_factory=None, *, attempts=ATTEMPTS, pause=PAUSE, sleep=time.sleep):
    """Devuelve el último informe; reintenta sólo lo que falló, nunca lo ya restaurado."""
    if runtime_factory is None:
        from .runtime import build_runtime
        runtime_factory = build_runtime
    total = {'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': []}
    for attempt in range(1, attempts + 1):
        try:
            with runtime_factory() as runtime:
                report = runtime.node.restore_isolations()
        except JobError as exc:
            # En frío `pveversion` u otro comando de Proxmox puede superar su plazo y `build_runtime` lo informa como
            # UNCONFIRMED: es transitorio. Se reintenta igual que un fallo por recurso; agotados los intentos se
            # propaga y `main` lo informa (la unidad queda fallida). Un error definitivo no se reintenta.
            if exc.code != 'UNCONFIRMED' or attempt == attempts: raise
            sleep(pause); continue
        known = {item for key in ('restaurados', 'vigentes', 'obsoletos') for item in total[key]}
        for key in ('restaurados', 'vigentes', 'obsoletos'): total[key] += [i for i in report[key] if i not in known]
        total['fallidos'] = report['fallidos']
        # Sólo lo transitorio se reintenta (el clúster aún no publica los invitados); un fallo definitivo no demora el arranque.
        if not any(item['codigo'] == 'UNCONFIRMED' for item in report['fallidos']): break
        if attempt < attempts: sleep(pause)
    total['intentos'] = attempt
    return total


def main():
    try:
        report = restore()
    except (JobError, OSError, ValueError):
        print(json.dumps({'estado': 'no_confirmado'}))
        return 1
    print(json.dumps({'estado': 'ok' if not report['fallidos'] else 'con_fallos', **report}, sort_keys=True))
    return 1 if report['fallidos'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
