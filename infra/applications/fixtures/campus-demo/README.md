# Aplicación de cátedra para aceptación 011

Fixture propia, sin datos institucionales ni dependencias de aplicación externas.
Puerto HTTP **8080**, probe `GET /health`, persistencia explícita **/data**.
No requiere variables o credenciales. El acceso NAP se comprueba por separado;
este servidor de ensayo no es un gestor de usuarios ni una aplicación para producción.

La imagen corre como UID/GID 10001 y conserva una nota en SQLite dentro del volumen.
Declarar `/data` al agregarla a NAP. No contiene un VOLUME anónimo, un HEALTHCHECK con
retención de salida ni credenciales de registry. La base Python está fijada por digest.

Construir y publicar es una tarea del desarrollador, fuera del portal. Con un registry
de ensayo TLS ya preparado y login mediante configuración privada:

```bash
docker build -t "${NAP011_TEST_REGISTRY:?Configurar registry de ensayo}/nap/campus-demo:acceptance" \
  infra/applications/fixtures/campus-demo
docker push "${NAP011_TEST_REGISTRY:?}/nap/campus-demo:acceptance"
```

La variable contiene sólo el host/puerto del registry, nunca usuario o contraseña.
NAP resolverá el digest de la imagen publicada; no seguirá el tag durante un pedido aprobado.
La construcción local y el reinicio Docker no acreditan Docker anidado, Proxmox ni la red universitaria.

Ensayo local opt-in, después de construir también el tag `nap011-campus-demo:acceptance`:

```bash
NAP_INFRA_INTEGRATION=1 backend/venv/bin/pytest -q -c infra/pytest.ini \
  infra/applications/tests/test_campus_demo_docker.py
```

Crea dos contenedores y volúmenes con nombres/labels únicos, prueba reinicio y separación del dato,
y retira exclusivamente esos recursos al finalizar. Los puertos se publican sólo en loopback.
