"""Entradas separadas: migración explícita, preflight, API o worker."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('accion',choices=['migrate','preflight','api','worker'])
    args=parser.parse_args()
    try:
        from app.services.puesta_servicio_service import exigir_configuracion
        exigir_configuracion()
        if args.accion=='migrate':
            from alembic import command
            from alembic.config import Config
            root=Path(__file__).resolve().parents[1]
            config=Config(str(root/'alembic.ini'))
            config.set_main_option('script_location',str(root/'alembic'))
            command.upgrade(config,'head')
            return 0
        if args.accion=='preflight':
            os.execv(sys.executable,[sys.executable,'-m','scripts.preflight','--datos'])
        if args.accion=='worker':
            os.execv(sys.executable,[sys.executable,'-m','app.worker'])
        from app.config import get_settings
        proxies=','.join(get_settings().trusted_proxy_networks)
        os.execv(sys.executable,[sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000',
            '--proxy-headers','--forwarded-allow-ips',proxies,'--no-access-log'])
    except RuntimeError as exc:
        # Sólo nuestros errores con códigos seguros; nunca repr de DSN/Settings.
        print(str(exc),file=sys.stderr);return 1
    except Exception:
        print('Intervención operativa fallida; revisar preflight y registros sin secretos',file=sys.stderr);return 1


if __name__=='__main__': raise SystemExit(main())
