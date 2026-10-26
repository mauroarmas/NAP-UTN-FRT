# Implementación 011 — setup inicial

Fecha: 2026-10-26. Alcance: T001–T003. No habilita perfiles ni acredita Proxmox.

- Fixtures backend: 6 pruebas aprobadas (estado durable simulado, respuesta perdida,
  takeover, reboot, registry privado y dos cátedras con responsables distintos).
- Demo universitaria: 3 pruebas unitarias aprobadas y construcción Docker real.
- Ensayo Docker local opt-in: 1 prueba aprobada; salud HTTP, UID 10001, persistencia
  después de reiniciar y separación de dos volúmenes. Sólo se retiraron los recursos
  identificados de esa prueba. No se modificó Draw.io ni el portal.
- Imagen local: `sha256:59dc83fb1cbb6228d4eb6d6de0b553baf59f54f854095c5716e1ebc1750a8806`.
  Se registra la imagen construida; todavía no es un digest de una oferta publicada.
- Preflight: 8 pruebas aprobadas. Valida candidatos pendientes, rechaza rutas arbitrarias,
  hashes cambiados, permisos inseguros y claves JSON repetidas; filtra datos privados.
- VM local accesible por SSH/API. Inventario API de sólo lectura confirma el nodo
  `proxmox` online y bases Ubuntu 24.04/Debian 13. Diagnóstico root reciente guardado
  fuera del repositorio. Los hashes de bases y AppArmor necesitan el inventario 011.

El diagnóstico anterior 010 no se interpreta como una certificación 011. T004 requiere
preparación inicial; los perfiles siguen pendientes hasta los gates reales previstos.

## Comandos verificados

```bash
backend/venv/bin/pytest -q backend/tests/test_fixtures_despliegue_011.py
backend/venv/bin/pytest -q -c infra/pytest.ini infra/applications/tests/test_campus_demo.py
backend/venv/bin/pytest -q -c infra/pytest.ini infra/laboratorio/011/tests/test_preflight.py
docker build --pull=false -t nap011-campus-demo:acceptance infra/applications/fixtures/campus-demo
NAP_INFRA_INTEGRATION=1 backend/venv/bin/pytest -q -c infra/pytest.ini infra/applications/tests/test_campus_demo_docker.py
```

Los conteos pertenecen a selecciones distintas; no acreditan los futuros tests del motor,
la concurrencia PostgreSQL ni los ensayos del clúster universitario.
