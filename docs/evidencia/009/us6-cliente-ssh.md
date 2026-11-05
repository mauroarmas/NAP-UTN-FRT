# US6 — Cliente OpenSSH

T094 implementada en `backend/app/services/guest_runner_client.py`. No se conectó mediante SSH al nodo ni se instaló una clave real.

El cliente solo obtiene destino, cuenta, puerto, clave y known_hosts de `runner_nodes`, indexado por el nodo de la operación. Rechaza opciones/URLs en host, cuenta root, archivos simbólicos o con permisos inseguros. Usa OpenSSH sin shell, configuración de usuario deshabilitada, clave/hostkey fijadas y sin contraseña, agent, proxy, forwarding, PTY, multiplexación o actualización automática de hostkeys. El comando remoto es constante. El Dockerfile incorpora openssh-client; las claves se montan externamente, no se copian a la imagen.

JSON va por stdin; stdout se drena con límite de 64 KiB y stderr se descarta desde la creación. Conexión de diez segundos y deadline total máximo de 180 s. Timeout/cancelación termina el transporte local y conserva el resultado como incierto; no demuestra que el guest haya terminado. La respuesta debe corresponder a operación/acción/recurso, tener fecha con zona y resultado cerrado sin campos secretos. La configuración es vacía por defecto: no hay un destino de demostración habilitado por inferencia.

## Verificación

```bash
cd backend
./venv/bin/python -m pytest -q tests/test_guest_runner_client.py
```

**14 aprobadas en 0,13 s**, log `/tmp/nap009-us6-ssh-verified.txt`. La prueba previa dio ocho aprobadas del parser y seis fallos por cliente ausente (`/tmp/nap009-us6-ssh-red.txt`). Se comprobaron argumentos, stdin, hostkey fallida, destino/clave inseguros, deadline y respuesta ajena o con campos secretos. No hubo SSH real.

```bash
NAP_INFRA_INTEGRATION=1 backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests/test_process_limits.py infra/runner/tests/test_client_streams.py
```

**4 aprobadas en 0,40 s**, log `/tmp/nap009-us6-local-transport.txt`: Python local efímero sustituye exclusivamente el transporte, comprueba streams reales, descarte de stderr, límite de salida y deadline. No ejecuta ssh ni usa red/PVE. Estas pruebas son opt-in; la suite ordinaria mantiene su bloqueo de procesos/red.

Falta comprobar archivo known_hosts y cuenta/sudo instalados, hostkey cambiada real y conectividad worker→nodo en T101. T095 integrará el cliente con preparación durable y snapshots; el worker aún conserva su bloqueo de bootstrap anterior.

Configuración institucional por nodo: `host`, `user`, `port`, `private_key_path`, `known_hosts_path`. Montar rutas absolutas regulares de solo lectura en el worker; clave 0600/0400 y known_hosts sin escritura de grupo/otros, en directorios seguros. No introducir contenidos privados en variables/logs. Producir known_hosts por un canal institucional verificado y conservarlo en un archivo montado; una hostkey distinta falla.
