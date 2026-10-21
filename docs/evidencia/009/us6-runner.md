# US6 — Runner cerrado del nodo

Implementación local de T093; sin instalar en PVE. Código, instalación explícita, formato del registro y límites en `infra/runner/README.md`.

El protocolo compartido de biblioteca estándar está en `backend/app/schemas/guest_runner.py`. El instalador del nodo lo copia como `protocol.py`; no requiere FastAPI, SQLAlchemy, acceso a la base del portal ni una shell del solicitante. `nap_guest_runner.py` controla registro, bundles, HMAC, flock y fases persistidas. `node_executor.py` verifica nodo/pool/UUID/nonce/digests/LXC no privilegiado antes y después de cada push/exec; contrasta además la dirección observada con el perfil institucional. Solo ejecuta comandos constantes. Los secretos van por stdin; respuesta/estado no los incluyen.

La cuenta SSH usa forced-command sin PTY/forwarding; sudo autoriza solo el wrapper sin argumentos. Archivos y directorios quedan controlados por root, con permisos mínimos. Los ejemplos no se aplicaron al equipo de desarrollo ni al nodo. La instalación real, hostkeys, sudo y ACL requieren T101.

Se conserva un intento persistido antes del envío. Misma instancia con otro UUID de operación tampoco permite cambiar sus secretos. Tras respuesta perdida se inspecciona: una preparación completa y saludable se confirma; un resultado parcial desconocido permanece incierto sin otro envío. No se adopta un guest completo si falta historia del host. Una coincidencia de hostname nunca acredita propiedad. Las lecturas inspect se reutilizan dentro de la llamada para evitar repetir su probe.

## Verificación

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests
```

**53 aprobadas en 2,29 s** antes de añadir los dos casos opt-in de procesos. Log `/tmp/nap009-us6-infra-runner-verified.txt`. Incluye identidad antes/después de cada comando, ausencia de claves en argv/estado/respuesta, rechazo de bundle alterado/simbólico, concurrencia entre operaciones y reinicio/deduplicación. La fixture del bundle usa 0444 como los artefactos reales; el ensayo de alteración cambia temporalmente el modo para simular una sustitución administrativa.

También se ejecutaron exclusivamente dos pruebas opt-in de procesos locales:

```bash
NAP_INFRA_INTEGRATION=1 backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests/test_process_limits.py
```

**2 aprobadas en 0,16 s**, log `/tmp/nap009-us6-runner-processes.txt`. Solo lanzan Python local efímero: comprueban stdin/salida acotada y timeout con terminación del grupo local. No usan red, SSH ni PVE. La suite ordinaria las omite y mantiene bloqueados los procesos externos.

Los ocho casos del parser de `backend/tests/test_guest_runner_client.py -k protocol` aprobaron. El cliente SSH queda pendiente de T094. `bash -n`/`sh -n` aprobaron instalador y wrapper. La prueba de nodo produjo inicialmente dos errores por módulo ausente; después se implementó. No se construyó una imagen ni se ejecutaron comandos contra un guest real. T095 debe añadir las marcas nuevas a la descripción PVE antes de crear recursos; el formato histórico incompleto no habilita preparación.

Fuentes: [pct oficial](https://github.com/proxmox/pve-container/blob/master/src/PVE/CLI/pct.pm), [documentación LXC](https://github.com/proxmox/pve-docs/blob/master/pct.adoc) y [restricciones authorized_keys](https://man.openbsd.org/sshd.8). La compatibilidad final se comprueba con la versión instalada, no se deduce de consultar master.
